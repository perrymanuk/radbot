"""
Database operations for the Claude Code / Coder Workspaces module.

Handles schema creation and CRUD for the ``coder_workspaces`` table,
reusing the shared PostgreSQL pool from ``radbot.db.connection``.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from radbot.db.connection import get_db_connection, get_db_cursor

logger = logging.getLogger(__name__)


def init_coder_schema() -> None:
    """Create the coder_workspaces table if it doesn't exist."""
    from radbot.tools.shared.db_schema import init_table_schema

    init_table_schema(
        table_name="coder_workspaces",
        create_table_sql="""
            CREATE TABLE coder_workspaces (
                workspace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                owner TEXT NOT NULL,
                repo TEXT NOT NULL,
                branch TEXT NOT NULL DEFAULT 'main',
                local_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                last_session_id TEXT,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(owner, repo, branch)
            );
        """,
        create_index_sqls=[
            """
            CREATE INDEX idx_coder_workspaces_active
            ON coder_workspaces (status) WHERE status = 'active';
            """,
        ],
    )

    # Migrations for existing tables
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Add name/description columns
                cursor.execute("""
                    ALTER TABLE coder_workspaces
                    ADD COLUMN IF NOT EXISTS name TEXT;
                """)
                cursor.execute("""
                    ALTER TABLE coder_workspaces
                    ADD COLUMN IF NOT EXISTS description TEXT;
                """)
                # Drop the UNIQUE constraint to allow multiple workspaces per repo/branch
                cursor.execute("""
                    ALTER TABLE coder_workspaces
                    DROP CONSTRAINT IF EXISTS coder_workspaces_owner_repo_branch_key;
                """)
                conn.commit()
    except Exception as e:
        logger.debug("Migration for coder_workspaces columns: %s", e)


def upsert_workspace(
    owner: str,
    repo: str,
    branch: str,
    local_path: str,
) -> Dict[str, Any]:
    """Insert or update a workspace by owner/repo/branch.

    Used by the axel agent's ``clone_repository`` tool where we want to
    reuse existing workspaces for the same repo.
    """
    # Try to find an existing active workspace for this repo/branch
    find_sql = """
        SELECT workspace_id FROM coder_workspaces
        WHERE owner = %s AND repo = %s AND branch = %s AND status = 'active'
        ORDER BY last_used_at DESC
        LIMIT 1;
    """
    upsert_sql = """
        UPDATE coder_workspaces
        SET local_path = %s, status = 'active', last_used_at = CURRENT_TIMESTAMP
        WHERE workspace_id = %s
        RETURNING workspace_id, owner, repo, branch, local_path, status,
                  last_session_id, created_at, last_used_at, name, description;
    """
    insert_sql = """
        INSERT INTO coder_workspaces (owner, repo, branch, local_path)
        VALUES (%s, %s, %s, %s)
        RETURNING workspace_id, owner, repo, branch, local_path, status,
                  last_session_id, created_at, last_used_at, name, description;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(find_sql, (owner, repo, branch))
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(upsert_sql, (local_path, existing["workspace_id"]))
                else:
                    cursor.execute(insert_sql, (owner, repo, branch, local_path))
                conn.commit()
                row = cursor.fetchone()
                return dict(row) if row else {}
    except psycopg2.Error as e:
        logger.error(f"Database error upserting workspace: {e}")
        raise


def create_workspace(
    owner: str,
    repo: str,
    branch: str,
    local_path: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Always insert a new workspace record (allows multiple per repo/branch)."""
    sql = """
        INSERT INTO coder_workspaces (owner, repo, branch, local_path, name, description)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING workspace_id, owner, repo, branch, local_path, status,
                  last_session_id, created_at, last_used_at, name, description;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, (owner, repo, branch, local_path, name, description))
                conn.commit()
                row = cursor.fetchone()
                return dict(row) if row else {}
    except psycopg2.Error as e:
        logger.error(f"Database error creating workspace: {e}")
        raise


def get_workspace(
    owner: str,
    repo: str,
    branch: str = "main",
) -> Optional[Dict[str, Any]]:
    """Get a workspace by owner/repo/branch."""
    sql = """
        SELECT * FROM coder_workspaces
        WHERE owner = %s AND repo = %s AND branch = %s;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, (owner, repo, branch))
                row = cursor.fetchone()
                return dict(row) if row else None
    except psycopg2.Error as e:
        logger.error(f"Database error getting workspace: {e}")
        raise


def update_session_id(
    owner: str,
    repo: str,
    branch: str,
    session_id: str,
) -> None:
    """Update the Claude Code session ID for a workspace."""
    sql = """
        UPDATE coder_workspaces
        SET last_session_id = %s,
            last_used_at = CURRENT_TIMESTAMP
        WHERE owner = %s AND repo = %s AND branch = %s;
    """
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (session_id, owner, repo, branch))
    except psycopg2.Error as e:
        logger.error(f"Database error updating session ID: {e}")
        raise


def list_active_workspaces() -> List[Dict[str, Any]]:
    """List all active workspaces."""
    sql = """
        SELECT * FROM coder_workspaces
        WHERE status = 'active'
        ORDER BY last_used_at DESC;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql)
                return [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logger.error(f"Database error listing workspaces: {e}")
        raise


def delete_workspace(workspace_id: str) -> bool:
    """Mark a workspace as deleted (soft delete)."""
    sql = """
        UPDATE coder_workspaces
        SET status = 'deleted'
        WHERE workspace_id = %s AND status = 'active';
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (uuid.UUID(workspace_id),))
                conn.commit()
                return cursor.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"Database error deleting workspace: {e}")
        raise


def update_workspace(
    workspace_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> bool:
    """Update workspace name and/or description."""
    updates = []
    params: list = []
    if name is not None:
        updates.append("name = %s")
        params.append(name)
    if description is not None:
        updates.append("description = %s")
        params.append(description)
    if not updates:
        return False

    sql = f"""
        UPDATE coder_workspaces
        SET {', '.join(updates)}, last_used_at = CURRENT_TIMESTAMP
        WHERE workspace_id = %s AND status = 'active';
    """
    params.append(uuid.UUID(workspace_id))
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                conn.commit()
                return cursor.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"Database error updating workspace: {e}")
        raise


def create_scratch_workspace(
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a scratch workspace (no repo) with a temporary directory."""
    import tempfile

    scratch_dir = tempfile.mkdtemp(prefix="claude-scratch-")
    workspace_name = name or "scratch"
    sql = """
        INSERT INTO coder_workspaces (owner, repo, branch, local_path, name, description)
        VALUES ('_scratch', %s, 'main', %s, %s, %s)
        RETURNING workspace_id, owner, repo, branch, local_path, status,
                  last_session_id, created_at, last_used_at, name, description;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # Use a unique repo name to avoid UNIQUE constraint
                repo_name = f"scratch-{uuid.uuid4().hex[:8]}"
                cursor.execute(sql, (repo_name, scratch_dir, workspace_name, description))
                conn.commit()
                row = cursor.fetchone()
                return dict(row) if row else {}
    except psycopg2.Error as e:
        logger.error(f"Database error creating scratch workspace: {e}")
        raise
