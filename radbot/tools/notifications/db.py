"""
Database operations for the Notifications system.

Stores all notification types (scheduled tasks, reminders, alerts, ntfy)
in a unified table with read/unread tracking and type filtering.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

logger = logging.getLogger(__name__)


def init_notification_schema() -> None:
    """Create the notifications table if it doesn't exist."""
    from radbot.tools.shared.db_schema import init_table_schema

    init_table_schema(
        table_name="notifications",
        create_table_sql="""
            CREATE TABLE notifications (
                notification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                source_id TEXT,
                session_id TEXT,
                priority TEXT DEFAULT 'default',
                read BOOLEAN NOT NULL DEFAULT FALSE,
                metadata JSONB,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        """,
        create_index_sqls=[
            """
            CREATE INDEX idx_notifications_type
            ON notifications (type);
            """,
            """
            CREATE INDEX idx_notifications_unread
            ON notifications (read) WHERE read = FALSE;
            """,
            """
            CREATE INDEX idx_notifications_created
            ON notifications (created_at DESC);
            """,
        ],
    )


def create_notification(
    type: str,
    title: str,
    message: str,
    source_id: Optional[str] = None,
    session_id: Optional[str] = None,
    priority: str = "default",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert a new notification and return its data."""
    sql = """
        INSERT INTO notifications (type, title, message, source_id, session_id, priority, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING notification_id, type, title, message, source_id, session_id,
                  priority, read, metadata, created_at;
    """
    meta_json = json.dumps(metadata) if metadata else None
    params = (type, title, message, source_id, session_id, priority, meta_json)

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, params)
                conn.commit()
                row = cursor.fetchone()
                return dict(row) if row else {}
    except psycopg2.Error as e:
        logger.error(f"Database error creating notification: {e}")
        raise


def list_notifications(
    type_filter: Optional[str] = None,
    read_filter: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List notifications with optional filters, newest first."""
    conditions = []
    params: list = []

    if type_filter:
        conditions.append("type = %s")
        params.append(type_filter)
    if read_filter is not None:
        conditions.append("read = %s")
        params.append(read_filter)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT * FROM notifications
        {where}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
    """
    params.extend([limit, offset])

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logger.error(f"Database error listing notifications: {e}")
        raise


def count_notifications(
    type_filter: Optional[str] = None,
    read_filter: Optional[bool] = None,
) -> int:
    """Count notifications with optional filters."""
    conditions = []
    params: list = []

    if type_filter:
        conditions.append("type = %s")
        params.append(type_filter)
    if read_filter is not None:
        conditions.append("read = %s")
        params.append(read_filter)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT COUNT(*) FROM notifications {where};"

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                return row[0] if row else 0
    except psycopg2.Error as e:
        logger.error(f"Database error counting notifications: {e}")
        raise


def get_notification(notification_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """Get a single notification by ID."""
    sql = "SELECT * FROM notifications WHERE notification_id = %s;"
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, (str(notification_id),))
                row = cursor.fetchone()
                return dict(row) if row else None
    except psycopg2.Error as e:
        logger.error(f"Database error getting notification {notification_id}: {e}")
        raise


def mark_read(notification_id: uuid.UUID) -> bool:
    """Mark a notification as read. Returns True if updated."""
    sql = "UPDATE notifications SET read = TRUE WHERE notification_id = %s AND read = FALSE;"
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (str(notification_id),))
                return cursor.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"Database error marking notification read: {e}")
        raise


def mark_all_read(type_filter: Optional[str] = None) -> int:
    """Mark all notifications as read. Returns count updated."""
    if type_filter:
        sql = "UPDATE notifications SET read = TRUE WHERE read = FALSE AND type = %s;"
        params: tuple = (type_filter,)
    else:
        sql = "UPDATE notifications SET read = TRUE WHERE read = FALSE;"
        params = ()

    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, params)
                return cursor.rowcount
    except psycopg2.Error as e:
        logger.error(f"Database error marking all notifications read: {e}")
        raise


def delete_notification(notification_id: uuid.UUID) -> bool:
    """Delete a notification. Returns True if deleted."""
    sql = "DELETE FROM notifications WHERE notification_id = %s RETURNING notification_id;"
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (str(notification_id),))
                return cursor.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"Database error deleting notification: {e}")
        raise
