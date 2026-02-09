"""Shared schema initialization for tool DB tables."""

import logging
from typing import List

from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

logger = logging.getLogger(__name__)


def init_table_schema(
    table_name: str,
    create_table_sql: str,
    create_index_sqls: List[str] | None = None,
) -> None:
    """Check-and-create a table plus optional indexes.

    This is idempotent — safe to call on every startup.
    """
    create_index_sqls = create_index_sqls or []
    try:
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cursor:
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = %s
                    );
                    """,
                    (table_name,),
                )
                table_exists = cursor.fetchone()[0]

                if not table_exists:
                    logger.info("Creating %s table", table_name)
                    cursor.execute(create_table_sql)
                    for idx_sql in create_index_sqls:
                        cursor.execute(idx_sql)
                    logger.info("%s table created successfully", table_name)
                else:
                    logger.info("%s table already exists", table_name)
    except Exception as e:
        logger.error("Error creating %s schema: %s", table_name, e)
        raise
