"""Database schema and CRUD operations for alert events and remediation policies.

Uses the shared DB pool from ``radbot.tools.todo.db.connection`` via
the ``get_db_connection`` context manager.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

logger = logging.getLogger(__name__)


# ── Schema ────────────────────────────────────────────────────


def init_alert_schema() -> None:
    """Create alert tables if they don't exist (idempotent)."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS alert_events (
                        alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        fingerprint TEXT NOT NULL,
                        alertname TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'received',
                        severity TEXT,
                        instance TEXT,
                        job_label TEXT,
                        summary TEXT,
                        description TEXT,
                        raw_payload JSONB NOT NULL,
                        remediation_action TEXT,
                        remediation_result TEXT,
                        remediation_session_id TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        resolved_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alert_events_fingerprint
                    ON alert_events (fingerprint)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alert_events_status
                    ON alert_events (status)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alert_events_created
                    ON alert_events (created_at DESC)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_alert_events_alertname
                    ON alert_events (alertname)
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS alert_remediation_policies (
                        policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        alertname_pattern TEXT NOT NULL,
                        severity TEXT,
                        action TEXT NOT NULL DEFAULT 'auto',
                        max_auto_remediations INTEGER DEFAULT 3,
                        window_minutes INTEGER DEFAULT 60,
                        timeout_seconds INTEGER DEFAULT 120,
                        max_llm_calls INTEGER DEFAULT 30,
                        enabled BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB
                    )
                """)
                # Migrate existing tables that lack the new columns
                for col, default in [
                    ("timeout_seconds", 120),
                    ("max_llm_calls", 30),
                ]:
                    cur.execute(f"""
                        DO $$ BEGIN
                            ALTER TABLE alert_remediation_policies
                                ADD COLUMN {col} INTEGER DEFAULT {default};
                        EXCEPTION WHEN duplicate_column THEN NULL;
                        END $$
                    """)
            conn.commit()
            logger.debug("Alert database schema initialized")
    except Exception as e:
        logger.error(f"Failed to init alert schema: {e}", exc_info=True)


# ── Alert Events CRUD ─────────────────────────────────────────


def create_alert_event(
    fingerprint: str,
    alertname: str,
    raw_payload: dict,
    severity: Optional[str] = None,
    instance: Optional[str] = None,
    job_label: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert a new alert event. Returns the created row."""
    alert_id = uuid.uuid4()
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO alert_events
                    (alert_id, fingerprint, alertname, severity, instance,
                     job_label, summary, description, raw_payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING alert_id, fingerprint, alertname, status, created_at
                """,
                (
                    str(alert_id),
                    fingerprint,
                    alertname,
                    severity,
                    instance,
                    job_label,
                    summary,
                    description,
                    json.dumps(raw_payload),
                ),
            )
            conn.commit()
            row = cur.fetchone()
            result = dict(row)
            result["alert_id"] = str(result["alert_id"])
            if result.get("created_at"):
                result["created_at"] = result["created_at"].isoformat()
            return result


def update_alert_status(
    alert_id: str,
    status: str,
    remediation_action: Optional[str] = None,
    remediation_result: Optional[str] = None,
    remediation_session_id: Optional[str] = None,
) -> bool:
    """Update an alert event's status and optional remediation fields."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            sets = ["status = %s", "updated_at = CURRENT_TIMESTAMP"]
            params: list = [status]

            if status == "resolved":
                sets.append("resolved_at = CURRENT_TIMESTAMP")
            if remediation_action is not None:
                sets.append("remediation_action = %s")
                params.append(remediation_action)
            if remediation_result is not None:
                sets.append("remediation_result = %s")
                params.append(remediation_result)
            if remediation_session_id is not None:
                sets.append("remediation_session_id = %s")
                params.append(remediation_session_id)

            params.append(alert_id)
            cur.execute(
                f"UPDATE alert_events SET {', '.join(sets)} WHERE alert_id = %s",
                params,
            )
            conn.commit()
            return cur.rowcount > 0


def get_unresolved_by_fingerprint(fingerprint: str) -> Optional[Dict[str, Any]]:
    """Find an unresolved alert event with the given fingerprint."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT alert_id, fingerprint, alertname, status, severity,
                       instance, summary, remediation_action, created_at
                FROM alert_events
                WHERE fingerprint = %s
                  AND status NOT IN ('resolved', 'ignored', 'failed')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (fingerprint,),
            )
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row)
            result["alert_id"] = str(result["alert_id"])
            if result.get("created_at"):
                result["created_at"] = result["created_at"].isoformat()
            return result


def list_alerts(
    status: Optional[str] = None,
    alertname: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List recent alert events, optionally filtered, with pagination."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            where = []
            params: list = []
            if status:
                where.append("status = %s")
                params.append(status)
            if alertname:
                where.append("alertname = %s")
                params.append(alertname)

            where_clause = f"WHERE {' AND '.join(where)}" if where else ""
            params.extend([limit, offset])

            cur.execute(
                f"""
                SELECT alert_id, fingerprint, alertname, status, severity,
                       instance, summary, remediation_action, remediation_result,
                       created_at, resolved_at, updated_at
                FROM alert_events
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params,
            )
            results = []
            for row in cur.fetchall():
                r = dict(row)
                r["alert_id"] = str(r["alert_id"])
                for ts_field in ("created_at", "resolved_at", "updated_at"):
                    if r.get(ts_field):
                        r[ts_field] = r[ts_field].isoformat()
                results.append(r)
            return results


def count_alerts(
    status: Optional[str] = None,
    alertname: Optional[str] = None,
) -> int:
    """Count alert events, optionally filtered."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            where = []
            params: list = []
            if status:
                where.append("status = %s")
                params.append(status)
            if alertname:
                where.append("alertname = %s")
                params.append(alertname)

            where_clause = f"WHERE {' AND '.join(where)}" if where else ""
            cur.execute(
                f"SELECT COUNT(*) FROM alert_events {where_clause}",
                params,
            )
            return cur.fetchone()[0]


def get_alert(alert_id: str) -> Optional[Dict[str, Any]]:
    """Get a single alert event by ID."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT alert_id, fingerprint, alertname, status, severity,
                       instance, job_label, summary, description,
                       raw_payload, remediation_action, remediation_result,
                       remediation_session_id, created_at, resolved_at, updated_at
                FROM alert_events
                WHERE alert_id = %s
                """,
                (alert_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            r = dict(row)
            r["alert_id"] = str(r["alert_id"])
            # raw_payload is already a dict from JSONB
            if isinstance(r.get("raw_payload"), str):
                r["raw_payload"] = json.loads(r["raw_payload"])
            for ts_field in ("created_at", "resolved_at", "updated_at"):
                if r.get(ts_field):
                    r[ts_field] = r[ts_field].isoformat()
            return r


# ── Remediation Policies CRUD ─────────────────────────────────


def create_policy(
    alertname_pattern: str,
    action: str = "auto",
    severity: Optional[str] = None,
    max_auto_remediations: int = 3,
    window_minutes: int = 60,
    timeout_seconds: int = 120,
    max_llm_calls: int = 30,
    metadata: Optional[dict] = None,
) -> Dict[str, Any]:
    """Create a remediation policy."""
    policy_id = uuid.uuid4()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO alert_remediation_policies
                    (policy_id, alertname_pattern, severity, action,
                     max_auto_remediations, window_minutes,
                     timeout_seconds, max_llm_calls, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING policy_id
                """,
                (
                    str(policy_id),
                    alertname_pattern,
                    severity,
                    action,
                    max_auto_remediations,
                    window_minutes,
                    timeout_seconds,
                    max_llm_calls,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            conn.commit()
            return {"policy_id": str(policy_id), "alertname_pattern": alertname_pattern}


def list_policies() -> List[Dict[str, Any]]:
    """List all remediation policies."""
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT policy_id, alertname_pattern, severity, action,
                       max_auto_remediations, window_minutes,
                       timeout_seconds, max_llm_calls, enabled, metadata
                FROM alert_remediation_policies
                ORDER BY created_at
                """
            )
            results = []
            for row in cur.fetchall():
                r = dict(row)
                r["policy_id"] = str(r["policy_id"])
                results.append(r)
            return results


def update_policy(policy_id: str, **fields) -> bool:
    """Update a policy's fields."""
    allowed = {
        "alertname_pattern", "severity", "action",
        "max_auto_remediations", "window_minutes",
        "timeout_seconds", "max_llm_calls",
        "enabled", "metadata",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            sets = []
            params = []
            for k, v in updates.items():
                sets.append(f"{k} = %s")
                if k == "metadata" and isinstance(v, dict):
                    params.append(json.dumps(v))
                else:
                    params.append(v)
            params.append(policy_id)
            cur.execute(
                f"UPDATE alert_remediation_policies SET {', '.join(sets)} WHERE policy_id = %s",
                params,
            )
            conn.commit()
            return cur.rowcount > 0


def delete_policy(policy_id: str) -> bool:
    """Delete a remediation policy."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM alert_remediation_policies WHERE policy_id = %s",
                (policy_id,),
            )
            conn.commit()
            return cur.rowcount > 0


def get_matching_policy(alertname: str, severity: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find the first enabled policy matching the alertname (regex) and optional severity."""
    policies = list_policies()
    for p in policies:
        if not p["enabled"]:
            continue
        # Check severity filter
        if p["severity"] and severity and p["severity"] != severity:
            continue
        # Check alertname pattern (regex match)
        try:
            if re.match(p["alertname_pattern"], alertname):
                return p
        except re.error:
            # Fall back to exact match on bad regex
            if p["alertname_pattern"] == alertname:
                return p
    return None


def count_recent_remediations(alertname: str, window_minutes: int) -> int:
    """Count remediations for an alertname within the time window."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
            cur.execute(
                """
                SELECT COUNT(*) FROM alert_events
                WHERE alertname = %s
                  AND status IN ('remediating', 'remediated')
                  AND created_at >= %s
                """,
                (alertname, cutoff),
            )
            return cur.fetchone()[0]
