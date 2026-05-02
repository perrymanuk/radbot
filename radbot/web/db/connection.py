"""
Database connection handling for Chat History Storage.

This module creates a connection pool specifically for the chat history schema.
"""

import logging
import os
import threading
import uuid
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras
import psycopg2.pool

# Import configuration
from radbot.config import config_loader

# Setup logging
logger = logging.getLogger(__name__)

# --- Connection Pool Setup ---
#
# Credential resolution and validation are deferred to pool init (see
# initialize_connection_pool below) so simply importing this module is safe
# in environments that never connect — e.g. unit tests that import
# radbot.web.app transitively. Sibling pool in radbot/db/connection.py uses
# the same pattern.

# Schema name uses a stable default. Reading config here is cheap and
# side-effect-free.
CHAT_SCHEMA = (
    config_loader.get_config()
    .get("database", {})
    .get("chat_history", {})
    .get("schema", "radbot_chathistory")
)

# Pool sizing (overridable via environment variables)
MIN_CONN = int(os.environ.get("RADBOT_DB_POOL_MIN", "1"))
MAX_CONN = int(os.environ.get("RADBOT_DB_POOL_MAX", "10"))

# Register UUID adapter for psycopg2
psycopg2.extensions.register_adapter(
    uuid.UUID, lambda u: psycopg2.extensions.adapt(str(u))
)

# Global pool reference
chat_pool = None
_pool_lock = threading.Lock()


def _resolve_chat_db_credentials() -> dict:
    """Resolve chat-history DB credentials from config + environment."""
    database_config = config_loader.get_config().get("database", {})
    chat_db_config = database_config.get("chat_history", {})

    return {
        "db_name": (
            chat_db_config.get("db_name")
            or database_config.get("db_name")
            or os.getenv("POSTGRES_DB")
        ),
        "user": (
            chat_db_config.get("user")
            or database_config.get("user")
            or os.getenv("POSTGRES_USER")
        ),
        "password": (
            chat_db_config.get("password")
            or database_config.get("password")
            or os.getenv("POSTGRES_PASSWORD")
        ),
        "host": (
            chat_db_config.get("host")
            or database_config.get("host")
            or os.getenv("POSTGRES_HOST", "localhost")
        ),
        "port": (
            chat_db_config.get("port")
            or database_config.get("port")
            or os.getenv("POSTGRES_PORT", "5432")
        ),
    }


def initialize_connection_pool():
    """Initialize the connection pool for chat history database."""
    global chat_pool

    creds = _resolve_chat_db_credentials()
    if not all([creds["db_name"], creds["user"], creds["password"]]):
        error_msg = "Database credentials (database.chat_history.db_name, database.chat_history.user, database.chat_history.password) must be set in config.yaml or as environment variables"  # noqa: E501
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        chat_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=MIN_CONN,
            maxconn=MAX_CONN,
            database=creds["db_name"],
            user=creds["user"],
            password=creds["password"],
            host=creds["host"],
            port=creds["port"],
        )
        logger.info(
            f"Chat history database connection pool initialized (Min: {MIN_CONN}, Max: {MAX_CONN})"
        )
        logger.info(
            "Connected to PostgreSQL database '%s' using schema '%s' at %s:%s",
            creds["db_name"],
            CHAT_SCHEMA,
            creds["host"],
            creds["port"],
        )
        return True
    except psycopg2.OperationalError as e:
        logger.error(f"FATAL: Could not connect to database: {e}")
        # Handle fatal error gracefully - return False instead of raising
        return False


@contextmanager
def get_chat_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Provides a database connection from the pool, managing cleanup."""
    # Initialize pool if not already initialized (thread-safe)
    if chat_pool is None:
        with _pool_lock:
            if chat_pool is None:
                if not initialize_connection_pool():
                    raise RuntimeError("Could not initialize database connection pool")

    conn = None
    try:
        conn = chat_pool.getconn()
        # Set the search path to use our schema
        with conn.cursor() as cursor:
            cursor.execute(f"SET search_path TO {CHAT_SCHEMA}, public;")
        yield conn
    except psycopg2.Error as e:
        # Log or handle pool errors if necessary
        logger.error(f"Error getting connection from pool: {e}")
        raise  # Re-raise the original psycopg2 error
    finally:
        if conn:
            chat_pool.putconn(conn)  # Return connection to the pool


@contextmanager
def get_chat_db_cursor(
    conn: psycopg2.extensions.connection, commit: bool = False
) -> Generator[psycopg2.extensions.cursor, None, None]:
    """Provides a cursor from a connection, handling commit/rollback."""
    with conn.cursor() as cursor:
        try:
            yield cursor
            if commit:
                conn.commit()
        except psycopg2.Error as e:
            logger.error(
                f"Database operation failed. Rolling back transaction. Error: {e}"
            )
            conn.rollback()
            raise  # Re-raise the original psycopg2 error
        # No finally block needed for cursor, 'with' handles closing
