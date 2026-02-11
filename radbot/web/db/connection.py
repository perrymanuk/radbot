"""
Database connection handling for Chat History Storage.

This module creates a connection pool specifically for the chat history schema.
"""

import logging
import os
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

# Get database configuration from config.yaml
database_config = config_loader.get_config().get("database", {})
chat_db_config = database_config.get("chat_history", {})

# Load schema name with a default fallback
CHAT_SCHEMA = chat_db_config.get("schema", "radbot_chathistory")

# Load connection details from config or environment
DB_NAME = (
    chat_db_config.get("db_name")
    or database_config.get("db_name")
    or os.getenv("POSTGRES_DB")
)
DB_USER = (
    chat_db_config.get("user")
    or database_config.get("user")
    or os.getenv("POSTGRES_USER")
)
DB_PASSWORD = (
    chat_db_config.get("password")
    or database_config.get("password")
    or os.getenv("POSTGRES_PASSWORD")
)
DB_HOST = (
    chat_db_config.get("host")
    or database_config.get("host")
    or os.getenv("POSTGRES_HOST", "localhost")
)
DB_PORT = (
    chat_db_config.get("port")
    or database_config.get("port")
    or os.getenv("POSTGRES_PORT", "5432")
)

# Basic validation
if not all([DB_NAME, DB_USER, DB_PASSWORD]):
    error_msg = "Database credentials (database.chat_history.db_name, database.chat_history.user, database.chat_history.password) must be set in config.yaml or as environment variables"
    logger.error(error_msg)
    raise ValueError(error_msg)

# Register UUID adapter for psycopg2
psycopg2.extensions.register_adapter(
    uuid.UUID, lambda u: psycopg2.extensions.adapt(str(u))
)

# Configure and initialize the connection pool
# Adjust minconn and maxconn based on expected load
MIN_CONN = 1
MAX_CONN = 5  # Start conservatively

# Global pool reference
chat_pool = None


def initialize_connection_pool():
    """Initialize the connection pool for chat history database."""
    global chat_pool

    try:
        chat_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=MIN_CONN,
            maxconn=MAX_CONN,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
        )
        logger.info(
            f"Chat history database connection pool initialized (Min: {MIN_CONN}, Max: {MAX_CONN})"
        )
        logger.info(
            f"Connected to PostgreSQL database '{DB_NAME}' using schema '{CHAT_SCHEMA}' at {DB_HOST}:{DB_PORT}"
        )
        return True
    except psycopg2.OperationalError as e:
        logger.error(f"FATAL: Could not connect to database: {e}")
        # Handle fatal error gracefully - return False instead of raising
        return False


@contextmanager
def get_chat_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Provides a database connection from the pool, managing cleanup."""
    global chat_pool

    # Initialize pool if not already initialized
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
