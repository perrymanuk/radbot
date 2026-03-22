"""Database operations for session worker lifecycle tracking.

Tracks which sessions have active Nomad worker jobs, used by the
SessionProxy for discovery and by the GC for cleanup.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from radbot.tools.todo.db.connection import get_db_cursor

logger = logging.getLogger(__name__)


def init_session_workers_schema() -> None:
    """Create the session_workers table if it doesn't exist."""
    from radbot.tools.shared.db_schema import init_table_schema

    init_table_schema(
        table_name="session_workers",
        create_table_sql="""
            CREATE TABLE session_workers (
                session_id UUID PRIMARY KEY,
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
            CREATE INDEX idx_session_workers_status
            ON session_workers (status);
            """,
            """
            CREATE INDEX idx_session_workers_nomad_job
            ON session_workers (nomad_job_id);
            """,
        ],
    )


def upsert_worker(
    session_id: str,
    nomad_job_id: str,
    worker_url: Optional[str] = None,
    status: str = "starting",
    image_tag: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert or update a session worker record."""
    with get_db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO session_workers
                (session_id, nomad_job_id, worker_url, status, image_tag, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                nomad_job_id = EXCLUDED.nomad_job_id,
                worker_url = COALESCE(EXCLUDED.worker_url, session_workers.worker_url),
                status = EXCLUDED.status,
                image_tag = COALESCE(EXCLUDED.image_tag, session_workers.image_tag),
                metadata = COALESCE(EXCLUDED.metadata, session_workers.metadata),
                last_active_at = CURRENT_TIMESTAMP
            RETURNING session_id, nomad_job_id, worker_url, status,
                      created_at, last_active_at, image_tag
            """,
            (
                session_id,
                nomad_job_id,
                worker_url,
                status,
                image_tag,
                json.dumps(metadata) if metadata else None,
            ),
        )
        row = cur.fetchone()
        return _row_to_dict(row, cur) if row else {}


def get_worker(session_id: str) -> Optional[Dict[str, Any]]:
    """Get a worker record by session ID."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT session_id, nomad_job_id, worker_url, status,
                   created_at, last_active_at, image_tag, metadata
            FROM session_workers
            WHERE session_id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(row, cur) if row else None


def update_worker_status(
    session_id: str,
    status: str,
    worker_url: Optional[str] = None,
) -> bool:
    """Update a worker's status and optionally its URL."""
    with get_db_cursor(commit=True) as cur:
        if worker_url:
            cur.execute(
                """
                UPDATE session_workers
                SET status = %s, worker_url = %s, last_active_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
                """,
                (status, worker_url, session_id),
            )
        else:
            cur.execute(
                """
                UPDATE session_workers
                SET status = %s, last_active_at = CURRENT_TIMESTAMP
                WHERE session_id = %s
                """,
                (status, session_id),
            )
        return cur.rowcount > 0


def touch_worker(session_id: str) -> bool:
    """Update last_active_at for a worker."""
    with get_db_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE session_workers
            SET last_active_at = CURRENT_TIMESTAMP
            WHERE session_id = %s
            """,
            (session_id,),
        )
        return cur.rowcount > 0


def list_active_workers() -> List[Dict[str, Any]]:
    """List all workers with status in (starting, healthy)."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT session_id, nomad_job_id, worker_url, status,
                   created_at, last_active_at, image_tag, metadata
            FROM session_workers
            WHERE status IN ('starting', 'healthy')
            ORDER BY created_at DESC
            """,
        )
        rows = cur.fetchall()
        return [_row_to_dict(row, cur) for row in rows]


def count_active_workers() -> int:
    """Count workers with status in (starting, healthy)."""
    with get_db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM session_workers
            WHERE status IN ('starting', 'healthy')
            """,
        )
        row = cur.fetchone()
        return row[0] if row else 0


def delete_worker(session_id: str) -> bool:
    """Delete a worker record."""
    with get_db_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM session_workers WHERE session_id = %s",
            (session_id,),
        )
        return cur.rowcount > 0


def _row_to_dict(row, cur) -> Dict[str, Any]:
    """Convert a database row to a dict using cursor column names."""
    if not row:
        return {}
    columns = [desc[0] for desc in cur.description]
    result = dict(zip(columns, row))
    # Serialize UUIDs and datetimes
    for key, val in result.items():
        if hasattr(val, "hex"):
            result[key] = str(val)
        elif isinstance(val, datetime):
            result[key] = val.isoformat()
    return result
