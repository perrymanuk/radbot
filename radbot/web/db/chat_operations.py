"""
Database operations for chat message persistence.

This module handles all operations for storing and retrieving chat messages
using the dedicated radbot_chathistory schema.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

# Use our custom connection functions
from radbot.web.db.connection import (
    CHAT_SCHEMA,
    get_chat_db_connection,
    get_chat_db_cursor,
)

logger = logging.getLogger(__name__)


def create_schema_if_not_exists() -> bool:
    """
    Create the chat history schema and tables if they don't exist.

    Returns:
        bool: True if schema was created or already exists, False on error
    """
    try:
        with get_chat_db_connection() as conn:
            with get_chat_db_cursor(conn, commit=True) as cursor:
                # Create schema if not exists
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {CHAT_SCHEMA};")

                # Set search path to our schema
                cursor.execute(f"SET search_path TO {CHAT_SCHEMA}, public;")

                # Create chat_messages table if not exists
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {CHAT_SCHEMA}.chat_messages (
                        message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        session_id UUID NOT NULL,
                        user_id TEXT,
                        role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                        content TEXT NOT NULL,
                        agent_name TEXT,
                        timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB
                    );
                """)

                # Create indexes if they don't exist
                cursor.execute(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_indexes
                            WHERE schemaname = '{CHAT_SCHEMA}'
                            AND indexname = 'idx_chat_messages_session_id'
                        ) THEN
                            CREATE INDEX idx_chat_messages_session_id
                            ON {CHAT_SCHEMA}.chat_messages(session_id);
                        END IF;

                        IF NOT EXISTS (
                            SELECT 1 FROM pg_indexes
                            WHERE schemaname = '{CHAT_SCHEMA}'
                            AND indexname = 'idx_chat_messages_timestamp'
                        ) THEN
                            CREATE INDEX idx_chat_messages_timestamp
                            ON {CHAT_SCHEMA}.chat_messages(timestamp);
                        END IF;
                    END
                    $$;
                """)

                # Create chat_sessions table if not exists
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {CHAT_SCHEMA}.chat_sessions (
                        session_id UUID PRIMARY KEY,
                        name TEXT,
                        user_id TEXT,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        last_message_at TIMESTAMP WITH TIME ZONE,
                        preview TEXT,
                        is_active BOOLEAN DEFAULT true
                    );
                """)

                logger.info(
                    f"Chat history schema and tables created or verified in schema '{CHAT_SCHEMA}'"
                )
                return True
    except Exception as e:
        logger.error(f"Error creating chat history schema: {e}")
        return False


def add_message(
    session_id: str,
    role: str,
    content: str,
    agent_name: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Optional[str]:
    """
    Insert a new message into the database.

    Args:
        session_id: Session identifier
        role: Message role ('user', 'assistant', 'system')
        content: Message content
        agent_name: Optional agent name for assistant messages
        user_id: Optional user identifier
        metadata: Optional metadata as dict

    Returns:
        message_id: UUID of the inserted message or None on error
    """
    # Convert session_id to UUID if string
    if isinstance(session_id, str):
        try:
            session_id = uuid.UUID(session_id)
        except ValueError:
            logger.error(f"Invalid session_id format: {session_id}")
            return None

    # Convert metadata to JSON if provided
    if metadata is not None:
        metadata = json.dumps(metadata)

    sql = f"""
        INSERT INTO {CHAT_SCHEMA}.chat_messages
        (session_id, role, content, agent_name, user_id, metadata)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        RETURNING message_id;
    """

    params = (session_id, role, content, agent_name, user_id, metadata)

    try:
        with get_chat_db_connection() as conn:
            with get_chat_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, params)
                message_id = cursor.fetchone()[0]

                # Update session last_message
                update_session_last_message(conn, session_id, content, role)

                return str(message_id)
    except Exception as e:
        logger.error(f"Error adding message: {e}")
        return None


def get_messages_by_session_id(
    session_id: str, limit: int = 200, offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Get messages for a specific session.

    Args:
        session_id: Session identifier
        limit: Maximum number of messages to return
        offset: Number of messages to skip

    Returns:
        List of message dictionaries
    """
    # Convert session_id to UUID if string
    if isinstance(session_id, str):
        try:
            session_id = uuid.UUID(session_id)
        except ValueError:
            logger.error(f"Invalid session_id format: {session_id}")
            return []

    sql = f"""
        SELECT message_id, session_id, role, content, agent_name,
               timestamp, user_id, metadata
        FROM {CHAT_SCHEMA}.chat_messages
        WHERE session_id = %s
        ORDER BY timestamp ASC
        LIMIT %s OFFSET %s;
    """

    params = (session_id, limit, offset)

    try:
        with get_chat_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(sql, params)
                results = cursor.fetchall()

                # Convert to standard dicts and format fields
                messages = []
                for row in results:
                    message = dict(row)
                    # Convert UUIDs to strings
                    message["message_id"] = str(message["message_id"])
                    message["session_id"] = str(message["session_id"])
                    # Convert timestamp to ISO format
                    if message["timestamp"]:
                        message["timestamp"] = message["timestamp"].isoformat()
                    messages.append(message)

                return messages
    except Exception as e:
        logger.error(f"Error getting messages for session {session_id}: {e}")
        return []


def create_or_update_session(
    session_id: str, name: Optional[str] = None, user_id: Optional[str] = None
) -> bool:
    """
    Create or update a chat session.

    Args:
        session_id: Session identifier
        name: Optional session name
        user_id: Optional user identifier

    Returns:
        bool: True if successful, False on error
    """
    # Convert session_id to UUID if string
    if isinstance(session_id, str):
        try:
            session_id = uuid.UUID(session_id)
        except ValueError:
            logger.error(f"Invalid session_id format: {session_id}")
            return False

    # Insert or update SQL
    sql = f"""
        INSERT INTO {CHAT_SCHEMA}.chat_sessions (session_id, name, user_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (session_id)
        DO UPDATE SET
            name = COALESCE(EXCLUDED.name, chat_sessions.name),
            user_id = COALESCE(EXCLUDED.user_id, chat_sessions.user_id),
            is_active = true;
    """

    params = (session_id, name, user_id)

    try:
        with get_chat_db_connection() as conn:
            with get_chat_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, params)
                return True
    except Exception as e:
        logger.error(f"Error creating/updating session {session_id}: {e}")
        return False


def update_session_last_message(
    conn, session_id: uuid.UUID, preview: str, role: str
) -> bool:
    """
    Update session last message timestamp and preview.
    Used internally by add_message.

    Args:
        conn: Database connection
        session_id: Session identifier
        preview: Preview text (truncated message content)
        role: Message role

    Returns:
        bool: True if successful, False on error
    """
    # Only update preview for user or assistant messages
    if role not in ("user", "assistant"):
        return True

    # Truncate preview text
    if preview and len(preview) > 100:
        preview = preview[:97] + "..."

    # Update session
    sql = f"""
        INSERT INTO {CHAT_SCHEMA}.chat_sessions
        (session_id, last_message_at, preview)
        VALUES (%s, CURRENT_TIMESTAMP, %s)
        ON CONFLICT (session_id)
        DO UPDATE SET
            last_message_at = CURRENT_TIMESTAMP,
            preview = %s;
    """

    params = (session_id, preview, preview)

    try:
        with get_chat_db_cursor(conn, commit=True) as cursor:
            cursor.execute(sql, params)
            return True
    except Exception as e:
        logger.error(f"Error updating session last message: {e}")
        return False


def list_sessions(
    user_id: Optional[str] = None, limit: int = 20, offset: int = 0
) -> List[Dict[str, Any]]:
    """
    List chat sessions, optionally filtered by user.

    Args:
        user_id: Optional user identifier to filter by
        limit: Maximum number of sessions to return
        offset: Number of sessions to skip

    Returns:
        List of session dictionaries
    """
    base_sql = f"""
        SELECT session_id, name, user_id, created_at, last_message_at, preview, is_active
        FROM {CHAT_SCHEMA}.chat_sessions
        WHERE is_active = true
    """

    params = []

    if user_id:
        base_sql += " AND user_id = %s"
        params.append(user_id)

    base_sql += """
        ORDER BY COALESCE(last_message_at, created_at) DESC
        LIMIT %s OFFSET %s;
    """

    params.extend([limit, offset])

    try:
        with get_chat_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(base_sql, tuple(params))
                results = cursor.fetchall()

                # Convert to standard dicts and format fields
                sessions = []
                for row in results:
                    session = dict(row)
                    # Convert UUID to string
                    session["session_id"] = str(session["session_id"])
                    # Convert timestamps to ISO format
                    if session.get("created_at"):
                        session["created_at"] = session["created_at"].isoformat()
                    if session.get("last_message_at"):
                        session["last_message_at"] = session[
                            "last_message_at"
                        ].isoformat()
                    sessions.append(session)

                return sessions
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        return []


def get_session_message_count(session_id: str) -> int:
    """
    Get count of messages in a session.

    Args:
        session_id: Session identifier

    Returns:
        int: Number of messages in the session
    """
    # Convert session_id to UUID if string
    if isinstance(session_id, str):
        try:
            session_id = uuid.UUID(session_id)
        except ValueError:
            logger.error(f"Invalid session_id format: {session_id}")
            return 0

    sql = f"""
        SELECT COUNT(*)
        FROM {CHAT_SCHEMA}.chat_messages
        WHERE session_id = %s;
    """

    try:
        with get_chat_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, (session_id,))
                result = cursor.fetchone()
                return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting message count for session {session_id}: {e}")
        return 0


def delete_session(session_id: str) -> bool:
    """
    Delete a chat session (mark as inactive).
    Note: This doesn't actually delete data, just marks the session as inactive.

    Args:
        session_id: Session identifier

    Returns:
        bool: True if successful, False on error
    """
    # Convert session_id to UUID if string
    if isinstance(session_id, str):
        try:
            session_id = uuid.UUID(session_id)
        except ValueError:
            logger.error(f"Invalid session_id format: {session_id}")
            return False

    sql = f"""
        UPDATE {CHAT_SCHEMA}.chat_sessions
        SET is_active = false
        WHERE session_id = %s;
    """

    try:
        with get_chat_db_connection() as conn:
            with get_chat_db_cursor(conn, commit=True) as cursor:
                cursor.execute(sql, (session_id,))
                return True
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        return False
