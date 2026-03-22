"""Database persistence and aggregation queries for LLM usage cost tracking.

Uses the shared DB pool from ``radbot.tools.todo.db.connection`` via
the ``get_db_connection`` context manager.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from radbot.tools.todo.db.connection import get_db_connection

logger = logging.getLogger(__name__)


# ── Schema ────────────────────────────────────────────────────


def init_usage_schema() -> None:
    """Create the llm_usage_log table if it doesn't exist (idempotent)."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS llm_usage_log (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        agent_name TEXT NOT NULL DEFAULT 'unknown',
                        model TEXT NOT NULL DEFAULT '',
                        prompt_tokens INTEGER NOT NULL DEFAULT 0,
                        cached_tokens INTEGER NOT NULL DEFAULT 0,
                        output_tokens INTEGER NOT NULL DEFAULT 0,
                        cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                        cost_without_cache_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                        session_id TEXT,
                        run_label TEXT NOT NULL DEFAULT 'production'
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_llm_usage_log_created
                    ON llm_usage_log (created_at DESC)
                """)
                # Note: expression index on date_trunc('month', timestamptz)
                # is not IMMUTABLE in PostgreSQL, so we rely on the
                # idx_llm_usage_log_created index for month queries.
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_llm_usage_log_label
                    ON llm_usage_log (run_label)
                """)
            conn.commit()
        logger.debug("llm_usage_log schema initialized")
    except Exception as e:
        logger.error("Failed to initialize llm_usage_log schema: %s", e)
        raise


# ── Insert ────────────────────────────────────────────────────


def record_usage(
    agent_name: str = "unknown",
    model: str = "",
    prompt_tokens: int = 0,
    cached_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    cost_without_cache_usd: float = 0.0,
    session_id: Optional[str] = None,
    run_label: Optional[str] = None,
) -> None:
    """Persist a single LLM invocation's usage to the database."""
    if run_label is None:
        run_label = os.environ.get("RADBOT_RUN_LABEL", "production")
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO llm_usage_log
                        (agent_name, model, prompt_tokens, cached_tokens,
                         output_tokens, cost_usd, cost_without_cache_usd,
                         session_id, run_label)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        agent_name,
                        model,
                        prompt_tokens,
                        cached_tokens,
                        output_tokens,
                        cost_usd,
                        cost_without_cache_usd,
                        session_id,
                        run_label,
                    ),
                )
            conn.commit()
    except Exception as e:
        logger.debug("Failed to persist usage record: %s", e)


# ── Query helpers ─────────────────────────────────────────────


def _label_clause(run_label: Optional[str]) -> tuple:
    """Return (sql_fragment, params) for optional run_label filtering."""
    if run_label:
        return " AND run_label = %s", [run_label]
    return "", []


def _month_start(year: int, month: int) -> datetime:
    """Return the first instant of the given month in UTC."""
    return datetime(year, month, 1, tzinfo=timezone.utc)


# ── Aggregation queries ──────────────────────────────────────


def get_monthly_summary(
    year: int, month: int, run_label: Optional[str] = None
) -> Dict[str, Any]:
    """Return aggregate token/cost totals for a given month."""
    label_sql, label_params = _label_clause(run_label)
    month_start = _month_start(year, month)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total_requests,
                        COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens,
                        COALESCE(SUM(cached_tokens), 0) AS total_cached_tokens,
                        COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
                        COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                        COALESCE(SUM(cost_without_cache_usd), 0) AS total_cost_without_cache_usd
                    FROM llm_usage_log
                    WHERE date_trunc('month', created_at) = %s
                    {label_sql}
                    """,
                    [month_start] + label_params,
                )
                row = cur.fetchone()
                if not row:
                    return {
                        "total_requests": 0,
                        "total_prompt_tokens": 0,
                        "total_cached_tokens": 0,
                        "total_output_tokens": 0,
                        "total_cost_usd": 0.0,
                        "total_cost_without_cache_usd": 0.0,
                    }
                return {
                    "total_requests": row[0],
                    "total_prompt_tokens": row[1],
                    "total_cached_tokens": row[2],
                    "total_output_tokens": row[3],
                    "total_cost_usd": round(float(row[4]), 6),
                    "total_cost_without_cache_usd": round(float(row[5]), 6),
                }
    except Exception as e:
        logger.error("Failed to get monthly summary: %s", e)
        return {
            "total_requests": 0,
            "total_prompt_tokens": 0,
            "total_cached_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "total_cost_without_cache_usd": 0.0,
        }


def get_daily_breakdown(
    year: int, month: int, run_label: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return per-day aggregates for a given month, ordered ascending."""
    label_sql, label_params = _label_clause(run_label)
    month_start = _month_start(year, month)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        date_trunc('day', created_at)::date AS day,
                        COUNT(*) AS requests,
                        COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(cost_usd), 0) AS cost_usd
                    FROM llm_usage_log
                    WHERE date_trunc('month', created_at) = %s
                    {label_sql}
                    GROUP BY day
                    ORDER BY day
                    """,
                    [month_start] + label_params,
                )
                return [
                    {
                        "day": str(row[0]),
                        "requests": row[1],
                        "prompt_tokens": row[2],
                        "output_tokens": row[3],
                        "cost_usd": round(float(row[4]), 6),
                    }
                    for row in cur.fetchall()
                ]
    except Exception as e:
        logger.error("Failed to get daily breakdown: %s", e)
        return []


def get_agent_breakdown(
    year: int, month: int, run_label: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return per-agent aggregates for a given month, sorted by cost DESC."""
    label_sql, label_params = _label_clause(run_label)
    month_start = _month_start(year, month)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        agent_name,
                        COUNT(*) AS requests,
                        COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                        COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(cost_usd), 0) AS cost_usd
                    FROM llm_usage_log
                    WHERE date_trunc('month', created_at) = %s
                    {label_sql}
                    GROUP BY agent_name
                    ORDER BY cost_usd DESC
                    """,
                    [month_start] + label_params,
                )
                return [
                    {
                        "agent_name": row[0],
                        "requests": row[1],
                        "prompt_tokens": row[2],
                        "cached_tokens": row[3],
                        "output_tokens": row[4],
                        "cost_usd": round(float(row[5]), 6),
                    }
                    for row in cur.fetchall()
                ]
    except Exception as e:
        logger.error("Failed to get agent breakdown: %s", e)
        return []


def get_model_breakdown(
    year: int, month: int, run_label: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Return per-model aggregates for a given month, sorted by cost DESC."""
    label_sql, label_params = _label_clause(run_label)
    month_start = _month_start(year, month)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        model,
                        COUNT(*) AS requests,
                        COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                        COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(cost_usd), 0) AS cost_usd
                    FROM llm_usage_log
                    WHERE date_trunc('month', created_at) = %s
                    {label_sql}
                    GROUP BY model
                    ORDER BY cost_usd DESC
                    """,
                    [month_start] + label_params,
                )
                return [
                    {
                        "model": row[0],
                        "requests": row[1],
                        "prompt_tokens": row[2],
                        "cached_tokens": row[3],
                        "output_tokens": row[4],
                        "cost_usd": round(float(row[5]), 6),
                    }
                    for row in cur.fetchall()
                ]
    except Exception as e:
        logger.error("Failed to get model breakdown: %s", e)
        return []


def get_available_months(
    run_label: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return distinct months with data, most recent first."""
    label_sql, label_params = _label_clause(run_label)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        date_trunc('month', created_at) AS month,
                        COUNT(*) AS requests,
                        COALESCE(SUM(cost_usd), 0) AS cost_usd
                    FROM llm_usage_log
                    WHERE 1=1
                    {label_sql}
                    GROUP BY month
                    ORDER BY month DESC
                    """,
                    label_params or None,
                )
                return [
                    {
                        "month": row[0].strftime("%Y-%m"),
                        "requests": row[1],
                        "cost_usd": round(float(row[2]), 6),
                    }
                    for row in cur.fetchall()
                ]
    except Exception as e:
        logger.error("Failed to get available months: %s", e)
        return []
