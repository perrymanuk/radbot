"""
Database operations for the Webhook Tool.

Handles schema creation and CRUD operations for webhook definitions,
reusing the existing PostgreSQL connection pool.
"""

import logging
import uuid
import json
from typing import List, Dict, Any, Optional

import psycopg2
import psycopg2.extras

from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

logger = logging.getLogger(__name__)


def init_webhook_schema() -> None:
    """Create the webhook_definitions table if it doesn't exist."""
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'webhook_definitions'
                    );
                """)
                table_exists = cursor.fetchone()[0]

                if not table_exists:
                    logger.info("Creating webhook_definitions table")
                    cursor.execute("""
                        CREATE TABLE webhook_definitions (
                            webhook_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            name TEXT NOT NULL UNIQUE,
                            path_suffix TEXT NOT NULL UNIQUE,
                            prompt_template TEXT NOT NULL,
                            secret TEXT,
                            enabled BOOLEAN NOT NULL DEFAULT TRUE,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            last_triggered_at TIMESTAMPTZ,
                            trigger_count INTEGER NOT NULL DEFAULT 0,
                            metadata JSONB
                        );
                    """)
                    cursor.execute("""
                        CREATE INDEX idx_webhook_definitions_path
                        ON webhook_definitions (path_suffix);
                    """)
                    logger.info("webhook_definitions table created successfully")
                else:
                    logger.info("webhook_definitions table already exists")
    except Exception as e:
        logger.error(f"Error creating webhook schema: {e}")
        raise


def create_webhook(
    name: str,
    path_suffix: str,
    prompt_template: str,
    secret: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert a new webhook definition and return its data."""
    sql = """
        INSERT INTO webhook_definitions (name, path_suffix, prompt_template, secret, metadata)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING webhook_id, name, path_suffix, prompt_template, secret, enabled,
                  created_at, last_triggered_at, trigger_count, metadata;
    """
    meta_json = json.dumps(metadata) if metadata else None
    params = (name, path_suffix, prompt_template, secret, meta_json)

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, params)
                conn.commit()
                row = cursor.fetchone()
                return dict(row) if row else {}
    except psycopg2.IntegrityError as e:
        logger.error(f"Integrity error creating webhook (duplicate name or path?): {e}")
        raise
    except psycopg2.Error as e:
        logger.error(f"Database error creating webhook: {e}")
        raise


def list_webhooks(enabled_only: bool = False) -> List[Dict[str, Any]]:
    """List all webhook definitions."""
    sql = "SELECT * FROM webhook_definitions"
    if enabled_only:
        sql += " WHERE enabled = TRUE"
    sql += " ORDER BY created_at DESC;"

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql)
                return [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logger.error(f"Database error listing webhooks: {e}")
        raise


def get_webhook_by_path(path_suffix: str) -> Optional[Dict[str, Any]]:
    """Look up a webhook by its path_suffix."""
    sql = "SELECT * FROM webhook_definitions WHERE path_suffix = %s AND enabled = TRUE;"
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, (path_suffix,))
                row = cursor.fetchone()
                return dict(row) if row else None
    except psycopg2.Error as e:
        logger.error(f"Database error looking up webhook by path '{path_suffix}': {e}")
        raise


def delete_webhook(webhook_id: uuid.UUID) -> bool:
    """Delete a webhook definition. Returns True if a row was deleted."""
    sql = "DELETE FROM webhook_definitions WHERE webhook_id = %s RETURNING webhook_id;"
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (str(webhook_id),))
                return cursor.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"Database error deleting webhook {webhook_id}: {e}")
        raise


def record_trigger(webhook_id: uuid.UUID) -> None:
    """Increment trigger_count and set last_triggered_at."""
    sql = """
        UPDATE webhook_definitions
        SET last_triggered_at = CURRENT_TIMESTAMP,
            trigger_count = trigger_count + 1
        WHERE webhook_id = %s;
    """
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (str(webhook_id),))
    except psycopg2.Error as e:
        logger.error(f"Database error recording trigger for webhook {webhook_id}: {e}")
        raise
