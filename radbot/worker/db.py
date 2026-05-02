"""Database operations for workspace worker lifecycle tracking.

Tracks which workspaces have active Nomad worker jobs (terminal PTY
sessions), used by the terminal proxy for discovery.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from radbot.db.connection import get_db_connection, get_db_cursor

logger = logging.getLogger(__name__)


def init_workspace_workers_schema() -> None:
    """Create the workspace_workers table if it doesn't exist."""
    from radbot.tools.shared.db_schema import init_table_schema

    init_table_schema(
        table_name="workspace_workers",
        create_table_sql="""
            CREATE TABLE workspace_workers (
                workspace_id UUID PRIMARY KEY,
                nomad_job_id TEXT NOT NULL,
                worker_url TEXT,
                status TEXT NOT NULL DEFAULT 'starting',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                last_active_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                image_tag TEXT,
                metadata JSONB
            );
        """,
        create_index_sqls=[
            """
            CREATE INDEX idx_workspace_workers_status
            ON workspace_workers (status);
            """,
        ],
    )


def upsert_workspace_worker(
    workspace_id: str,
    nomad_job_id: str,
    worker_url: Optional[str] = None,
    status: str = "starting",
    image_tag: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert or update a workspace worker record."""
    with get_db_connection() as conn:
        with get_db_cursor(conn, commit=True) as cur:
            cur.execute(
                """
                INSERT INTO workspace_workers
                    (workspace_id, nomad_job_id, worker_url, status, image_tag, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (workspace_id) DO UPDATE SET
                    nomad_job_id = EXCLUDED.nomad_job_id,
                    worker_url = COALESCE(EXCLUDED.worker_url, workspace_workers.worker_url),
                    status = EXCLUDED.status,
                    image_tag = COALESCE(EXCLUDED.image_tag, workspace_workers.image_tag),
                    metadata = COALESCE(EXCLUDED.metadata, workspace_workers.metadata),
                    last_active_at = CURRENT_TIMESTAMP
                RETURNING workspace_id, nomad_job_id, worker_url, status,
                          created_at, last_active_at, image_tag
                """,
                (
                    workspace_id,
                    nomad_job_id,
                    worker_url,
                    status,
                    image_tag,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            row = cur.fetchone()
            return _row_to_dict(row, cur) if row else {}


def get_workspace_worker(workspace_id: str) -> Optional[Dict[str, Any]]:
    """Get a workspace worker record."""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cur:
            cur.execute(
                """
                SELECT workspace_id, nomad_job_id, worker_url, status,
                       created_at, last_active_at, image_tag, metadata
                FROM workspace_workers
                WHERE workspace_id = %s
                """,
                (workspace_id,),
            )
            row = cur.fetchone()
            return _row_to_dict(row, cur) if row else None


def update_workspace_worker_status(
    workspace_id: str,
    status: str,
    worker_url: Optional[str] = None,
) -> bool:
    """Update a workspace worker's status."""
    with get_db_connection() as conn:
        with get_db_cursor(conn, commit=True) as cur:
            if worker_url:
                cur.execute(
                    """
                    UPDATE workspace_workers
                    SET status = %s, worker_url = %s, last_active_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s
                    """,
                    (status, worker_url, workspace_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE workspace_workers
                    SET status = %s, last_active_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s
                    """,
                    (status, workspace_id),
                )
            return cur.rowcount > 0


def count_active_workspace_workers() -> int:
    """Count workspace workers with status in (starting, healthy)."""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM workspace_workers
                WHERE status IN ('starting', 'healthy')
                """,
            )
            row = cur.fetchone()
            return row[0] if row else 0


def list_active_workspace_workers() -> List[Dict[str, Any]]:
    """List all workspace workers with status in (starting, healthy)."""
    with get_db_connection() as conn:
        with get_db_cursor(conn) as cur:
            cur.execute(
                """
                SELECT workspace_id, nomad_job_id, worker_url, status,
                       created_at, last_active_at, image_tag, metadata
                FROM workspace_workers
                WHERE status IN ('starting', 'healthy')
                ORDER BY created_at DESC
                """,
            )
            rows = cur.fetchall()
            return [_row_to_dict(row, cur) for row in rows]


def delete_workspace_worker(workspace_id: str) -> bool:
    """Delete a workspace worker record."""
    with get_db_connection() as conn:
        with get_db_cursor(conn, commit=True) as cur:
            cur.execute(
                "DELETE FROM workspace_workers WHERE workspace_id = %s",
                (workspace_id,),
            )
            return cur.rowcount > 0


def _row_to_dict(row, cur) -> Dict[str, Any]:
    """Convert a database row to a dict using cursor column names."""
    if not row:
        return {}
    columns = [desc[0] for desc in cur.description]
    result = dict(zip(columns, row))
    for key, val in result.items():
        if hasattr(val, "hex"):
            result[key] = str(val)
        elif isinstance(val, datetime):
            result[key] = val.isoformat()
    return result
