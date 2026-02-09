"""
Database operations for the Reminder Tool.

This module handles schema creation and CRUD operations for one-shot reminders,
reusing the existing PostgreSQL connection pool from radbot.tools.todo.db.connection.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

import psycopg2
import psycopg2.extras

from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

logger = logging.getLogger(__name__)


def init_reminder_schema() -> None:
    """Create the reminders table if it doesn't exist."""
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = 'reminders'
                    );
                """)
                table_exists = cursor.fetchone()[0]

                if not table_exists:
                    logger.info("Creating reminders table")
                    cursor.execute("""
                        CREATE TABLE reminders (
                            reminder_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            message TEXT NOT NULL,
                            remind_at TIMESTAMPTZ NOT NULL,
                            status TEXT NOT NULL DEFAULT 'pending',
                            delivered BOOLEAN NOT NULL DEFAULT FALSE,
                            session_id TEXT,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            completed_at TIMESTAMPTZ,
                            delivery_result TEXT
                        );
                    """)
                    cursor.execute("""
                        CREATE INDEX idx_reminders_status
                        ON reminders (status);
                    """)
                    cursor.execute("""
                        CREATE INDEX idx_reminders_pending_at
                        ON reminders (remind_at) WHERE status = 'pending';
                    """)
                    cursor.execute("""
                        CREATE INDEX idx_reminders_undelivered
                        ON reminders (delivered) WHERE status = 'completed' AND delivered = FALSE;
                    """)
                    logger.info("reminders table created successfully")
                else:
                    logger.info("reminders table already exists")
    except Exception as e:
        logger.error(f"Error creating reminder schema: {e}")
        raise


def create_reminder(
    message: str,
    remind_at: datetime,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert a new reminder and return its data."""
    sql = """
        INSERT INTO reminders (message, remind_at, session_id)
        VALUES (%s, %s, %s)
        RETURNING reminder_id, message, remind_at, status, delivered,
                  session_id, created_at, completed_at, delivery_result;
    """
    params = (message, remind_at, session_id)

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, params)
                conn.commit()
                row = cursor.fetchone()
                return dict(row) if row else {}
    except psycopg2.Error as e:
        logger.error(f"Database error creating reminder: {e}")
        raise


def list_reminders(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List reminders, optionally filtered by status."""
    if status and status != "all":
        sql = "SELECT * FROM reminders WHERE status = %s ORDER BY remind_at ASC;"
        params: tuple = (status,)
    else:
        sql = "SELECT * FROM reminders ORDER BY remind_at ASC;"
        params = ()

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logger.error(f"Database error listing reminders: {e}")
        raise


def get_reminder(reminder_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get a single reminder by ID."""
    sql = "SELECT * FROM reminders WHERE reminder_id = %s;"
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, (str(reminder_id),))
                row = cursor.fetchone()
                return dict(row) if row else None
    except psycopg2.Error as e:
        logger.error(f"Database error getting reminder {reminder_id}: {e}")
        raise


def delete_reminder(reminder_id: uuid.UUID) -> bool:
    """Delete a reminder. Returns True if a row was deleted."""
    sql = "DELETE FROM reminders WHERE reminder_id = %s RETURNING reminder_id;"
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (str(reminder_id),))
                return cursor.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"Database error deleting reminder {reminder_id}: {e}")
        raise


def mark_completed(reminder_id: uuid.UUID) -> None:
    """Mark a reminder as completed."""
    sql = """
        UPDATE reminders
        SET status = 'completed',
            completed_at = CURRENT_TIMESTAMP
        WHERE reminder_id = %s;
    """
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (str(reminder_id),))
    except psycopg2.Error as e:
        logger.error(f"Database error marking reminder {reminder_id} completed: {e}")
        raise


def mark_delivered(reminder_id: uuid.UUID, result: Optional[str] = None) -> None:
    """Mark a completed reminder as delivered."""
    sql = """
        UPDATE reminders
        SET delivered = TRUE,
            delivery_result = %s
        WHERE reminder_id = %s;
    """
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (result, str(reminder_id)))
    except psycopg2.Error as e:
        logger.error(f"Database error marking reminder {reminder_id} delivered: {e}")
        raise


def get_undelivered_completed() -> List[Dict[str, Any]]:
    """Get all completed but undelivered reminders."""
    sql = """
        SELECT * FROM reminders
        WHERE status = 'completed' AND delivered = FALSE
        ORDER BY completed_at ASC;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql)
                return [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logger.error(f"Database error getting undelivered reminders: {e}")
        raise
