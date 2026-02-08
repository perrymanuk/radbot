"""
Database operations for the Scheduler Tool.

This module handles schema creation and CRUD operations for scheduled tasks,
reusing the existing PostgreSQL connection pool from radbot.tools.todo.db.connection.
"""

import logging
import uuid
import json
from typing import List, Dict, Any, Optional

import psycopg2
import psycopg2.extras

from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

logger = logging.getLogger(__name__)


def init_scheduler_schema() -> None:
    """Create the scheduled_tasks table if it doesn't exist."""
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'scheduled_tasks'
                    );
                """)
                table_exists = cursor.fetchone()[0]

                if not table_exists:
                    logger.info("Creating scheduled_tasks table")
                    cursor.execute("""
                        CREATE TABLE scheduled_tasks (
                            task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            name TEXT NOT NULL,
                            cron_expression TEXT NOT NULL,
                            prompt TEXT NOT NULL,
                            description TEXT,
                            session_id TEXT,
                            enabled BOOLEAN NOT NULL DEFAULT TRUE,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            last_run_at TIMESTAMPTZ,
                            last_result TEXT,
                            run_count INTEGER NOT NULL DEFAULT 0,
                            metadata JSONB
                        );
                    """)
                    cursor.execute("""
                        CREATE INDEX idx_scheduled_tasks_enabled
                        ON scheduled_tasks (enabled);
                    """)
                    logger.info("scheduled_tasks table created successfully")
                else:
                    logger.info("scheduled_tasks table already exists")
    except Exception as e:
        logger.error(f"Error creating scheduler schema: {e}")
        raise


def create_task(
    name: str,
    cron_expression: str,
    prompt: str,
    description: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert a new scheduled task and return its data."""
    sql = """
        INSERT INTO scheduled_tasks (name, cron_expression, prompt, description, session_id, metadata)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING task_id, name, cron_expression, prompt, description, session_id,
                  enabled, created_at, updated_at, last_run_at, last_result, run_count, metadata;
    """
    meta_json = json.dumps(metadata) if metadata else None
    params = (name, cron_expression, prompt, description, session_id, meta_json)

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, params)
                conn.commit()
                row = cursor.fetchone()
                return dict(row) if row else {}
    except psycopg2.Error as e:
        logger.error(f"Database error creating scheduled task: {e}")
        raise


def list_tasks(enabled_only: bool = False) -> List[Dict[str, Any]]:
    """List all scheduled tasks, optionally filtering to enabled only."""
    sql = "SELECT * FROM scheduled_tasks"
    if enabled_only:
        sql += " WHERE enabled = TRUE"
    sql += " ORDER BY created_at DESC;"

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql)
                return [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logger.error(f"Database error listing scheduled tasks: {e}")
        raise


def get_task(task_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get a single scheduled task by ID."""
    sql = "SELECT * FROM scheduled_tasks WHERE task_id = %s;"
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, (str(task_id),))
                row = cursor.fetchone()
                return dict(row) if row else None
    except psycopg2.Error as e:
        logger.error(f"Database error getting scheduled task {task_id}: {e}")
        raise


def delete_task(task_id: uuid.UUID) -> bool:
    """Delete a scheduled task. Returns True if a row was deleted."""
    sql = "DELETE FROM scheduled_tasks WHERE task_id = %s RETURNING task_id;"
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (str(task_id),))
                return cursor.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"Database error deleting scheduled task {task_id}: {e}")
        raise


def update_last_run(task_id: uuid.UUID, result: Optional[str] = None) -> None:
    """Update the last_run_at timestamp and increment run_count."""
    sql = """
        UPDATE scheduled_tasks
        SET last_run_at = CURRENT_TIMESTAMP,
            updated_at  = CURRENT_TIMESTAMP,
            run_count   = run_count + 1,
            last_result = %s
        WHERE task_id = %s;
    """
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (result, str(task_id)))
    except psycopg2.Error as e:
        logger.error(f"Database error updating last run for {task_id}: {e}")
        raise
