"""Shared database connection pool for radbot.

Historically this lived under `radbot.tools.todo.db.connection` because todo
was the first module to need persistent storage. The pool is system-wide
(used by scheduler, reminders, webhooks, telos, alerts, credentials, etc.),
so it now lives here and the todo module has been retired.
"""

from radbot.db.connection import get_db_connection, get_db_cursor, get_db_pool

__all__ = ["get_db_connection", "get_db_cursor", "get_db_pool"]
