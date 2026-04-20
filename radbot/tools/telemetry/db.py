"""Schema for the ``telemetry_events`` table.

Single append-only table; payloads are integers + bools only (Pydantic
strips text upstream). Retention is intentionally unbounded — data is
small and useful for longitudinal baseline tracking.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_telemetry_schema() -> None:
    """Create the ``telemetry_events`` table if it doesn't exist."""
    from radbot.tools.shared.db_schema import init_table_schema

    init_table_schema(
        table_name="telemetry_events",
        create_table_sql="""
            CREATE TABLE telemetry_events (
                event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                event_type TEXT NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """,
        create_index_sqls=[
            "CREATE INDEX idx_telemetry_events_type_created "
            "ON telemetry_events (event_type, created_at DESC);",
        ],
    )
