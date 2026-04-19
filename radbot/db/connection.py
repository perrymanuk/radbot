"""Shared PostgreSQL connection pool for radbot.

Lazy-initialised `psycopg2.pool.ThreadedConnectionPool` used by every module
that touches the main database (scheduler, reminders, webhooks, telos,
notifications, alerts, credentials, claude_code, worker, telemetry, MCP
bridge, web health).
"""

import atexit
import logging
import os
import threading
import uuid
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras
import psycopg2.pool

from radbot.config import config_loader

logger = logging.getLogger(__name__)

psycopg2.extensions.register_adapter(
    uuid.UUID, lambda u: psycopg2.extensions.adapt(str(u))
)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

MIN_CONN = int(os.environ.get("RADBOT_DB_POOL_MIN", "1"))
MAX_CONN = int(os.environ.get("RADBOT_DB_POOL_MAX", "10"))


def _close_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
            logger.debug("radbot DB connection pool closed")
        except Exception:
            pass
        _pool = None


atexit.register(_close_pool)


def get_db_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the process-wide connection pool, initialising on first call."""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        return _init_pool_locked()


# Backwards-compatible alias used throughout the codebase.
_get_pool = get_db_pool


def _init_pool_locked() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool

    database_config = config_loader.get_config().get("database", {})
    db_name = database_config.get("db_name") or os.getenv("POSTGRES_DB")
    db_user = database_config.get("user") or os.getenv("POSTGRES_USER")
    db_password = database_config.get("password") or os.getenv("POSTGRES_PASSWORD")
    db_host = database_config.get("host") or os.getenv("POSTGRES_HOST", "localhost")
    db_port = database_config.get("port") or os.getenv("POSTGRES_PORT", "5432")

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
    """Provide a pooled connection, returning it on exit."""
    pool = get_db_pool()
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    except psycopg2.Error as e:
        logger.error(f"Error getting connection from pool: {e}")
        raise
    finally:
        if conn:
            pool.putconn(conn)


@contextmanager
def get_db_cursor(
    conn: psycopg2.extensions.connection, commit: bool = False
) -> Generator[psycopg2.extensions.cursor, None, None]:
    """Yield a cursor, committing on success or rolling back on error."""
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
            raise
