"""
Database connection handling for the Todo Tool.

This module encapsulates database connection management
using the psycopg2 library with connection pooling.
Connection pool is initialized lazily on first use.
"""

import atexit
import logging
import os
import threading
import uuid
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras  # For RealDictCursor
import psycopg2.pool

# Import configuration
from radbot.config import config_loader

# Setup logging
logger = logging.getLogger(__name__)

# Register UUID adapter for psycopg2
psycopg2.extensions.register_adapter(
    uuid.UUID, lambda u: psycopg2.extensions.adapt(str(u))
)

# --- Lazy Connection Pool ---

# Connection pool (initialized on first use)
_pool = None
_pool_lock = threading.Lock()

# Configure pool size
MIN_CONN = 1
MAX_CONN = 5


def _close_pool() -> None:
    """Close the connection pool on interpreter shutdown."""
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
            logger.debug("Todo DB connection pool closed")
        except Exception:
            pass
        _pool = None


atexit.register(_close_pool)


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Get or initialize the database connection pool.

    Raises:
        ValueError: If database credentials are not configured.
        psycopg2.OperationalError: If the database connection fails.
    """
    global _pool
    if _pool is not None:
        return _pool

    with _pool_lock:
        # Double-check after acquiring lock
        if _pool is not None:
            return _pool

        return _init_pool_locked()


def _init_pool_locked() -> psycopg2.pool.ThreadedConnectionPool:
    """Actually create the pool. Must be called while holding _pool_lock."""
    global _pool

    # Get database configuration from config.yaml
    database_config = config_loader.get_config().get("database", {})

    # Load from config.yaml or fall back to environment variables
    db_name = database_config.get("db_name") or os.getenv("POSTGRES_DB")
    db_user = database_config.get("user") or os.getenv("POSTGRES_USER")
    db_password = database_config.get("password") or os.getenv("POSTGRES_PASSWORD")
    db_host = database_config.get("host") or os.getenv("POSTGRES_HOST", "localhost")
    db_port = database_config.get("port") or os.getenv("POSTGRES_PORT", "5432")

    # Basic validation
    if not all([db_name, db_user, db_password]):
        error_msg = (
            "Database credentials (database.db_name, database.user, database.password) "
            "must be set in config.yaml or as environment variables "
            "(POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=MIN_CONN,
        maxconn=MAX_CONN,
        database=db_name,
        user=db_user,
        password=db_password,
        host=db_host,
        port=db_port,
    )
    logger.info(
        f"Database connection pool initialized (Min: {MIN_CONN}, Max: {MAX_CONN})"
    )
    logger.info(f"Connected to PostgreSQL database '{db_name}' at {db_host}:{db_port}")
    return _pool


@contextmanager
def get_db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Provides a database connection from the pool, managing cleanup."""
    pool = _get_pool()
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    except psycopg2.Error as e:
        # Log or handle pool errors if necessary
        logger.error(f"Error getting connection from pool: {e}")
        raise  # Re-raise the original psycopg2 error
    finally:
        if conn:
            pool.putconn(conn)  # Return connection to the pool


@contextmanager
def get_db_cursor(
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
