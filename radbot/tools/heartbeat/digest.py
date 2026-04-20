"""Heartbeat digest assembly — markdown brief from the day's proactive sources.

Content assembly is intentionally decoupled from transport (see
`delivery.py`). Each section is optional and degrades silently if its
data source is unavailable (e.g. calendar unauth, DB down).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _fetch_tasks(horizon: datetime) -> List[Dict[str, Any]]:
    try:
        from radbot.tools.telos.db import list_section
        from radbot.tools.telos.models import Section

        entries = list_section(Section.PROJECT_TASKS, status="active")
    except Exception as e:
        logger.debug("Heartbeat: telos unavailable: %s", e)
        return []

    out: List[Dict[str, Any]] = []
    today = date.today()
    for e in entries:
        meta = getattr(e, "metadata", None) or {}
        if not isinstance(meta, dict):
            meta = {}
        due_raw = meta.get("due_date")
        due: Optional[date] = None
        if due_raw:
            parsed = _parse_ts(due_raw)
            if parsed:
                due = parsed.date()
            else:
                try:
                    due = date.fromisoformat(str(due_raw)[:10])
                except Exception:
                    due = None
        task_status = str(meta.get("task_status", "")).lower()
        if task_status in {"done", "completed"}:
            continue
        if due is None or due <= today:
            out.append(
                {
                    "ref_code": getattr(e, "ref_code", ""),
                    "content": getattr(e, "content", ""),
                    "due": due.isoformat() if due else None,
                    "overdue": bool(due and due < today),
                }
            )
    return out


def _fetch_calendar(horizon: datetime) -> List[Dict[str, Any]]:
    try:
        from radbot.tools.calendar.calendar_tools import get_calendar_manager

        mgr = get_calendar_manager()
        now = datetime.utcnow()
        events = mgr.list_upcoming_events(
            time_min=now, time_max=horizon.replace(tzinfo=None), max_results=20
        )
        if isinstance(events, dict) and events.get("error"):
            return []
        return list(events or [])
    except Exception as e:
        logger.debug("Heartbeat: calendar unavailable: %s", e)
        return []


def _fetch_reminders(horizon: datetime) -> List[Dict[str, Any]]:
    try:
        from radbot.tools.reminders.db import list_reminders

        pending = list_reminders(status="pending") or []
    except Exception as e:
        logger.debug("Heartbeat: reminders unavailable: %s", e)
        return []
    out: List[Dict[str, Any]] = []
    for r in pending:
        remind_at = _parse_ts(r.get("remind_at"))
        if remind_at and remind_at <= horizon:
            out.append({"message": r.get("message", ""), "remind_at": remind_at})
    return out


def _fetch_alerts() -> List[Dict[str, Any]]:
    try:
        from radbot.tools.alertmanager.db import list_alerts

        received = list_alerts(status="received", limit=20) or []
    except Exception as e:
        logger.debug("Heartbeat: alerts unavailable: %s", e)
        return []
    return received


def _fetch_overnight_scheduler() -> List[Dict[str, Any]]:
    try:
        from radbot.tools.scheduler.db import get_undelivered_results

        return get_undelivered_results() or []
    except Exception as e:
        logger.debug("Heartbeat: scheduler results unavailable: %s", e)
        return []


def _render_tasks(tasks: List[Dict[str, Any]]) -> str:
    if not tasks:
        return "## Tasks\n_No items_\n"
    lines = ["## Tasks"]
    for t in tasks[:15]:
        tag = (
            " ⚠ overdue"
            if t.get("overdue")
            else (f" (due {t['due']})" if t.get("due") else "")
        )
        lines.append(f"- **{t.get('ref_code', '')}**{tag} — {t.get('content', '')}")
    return "\n".join(lines) + "\n"


def _render_calendar(events: List[Dict[str, Any]]) -> str:
    if not events:
        return "## Calendar\n_No items_\n"
    lines = ["## Calendar"]
    for ev in events[:10]:
        summary = ev.get("summary", "(no title)")
        start = ev.get("start") or {}
        when = start.get("dateTime") or start.get("date") or "?"
        lines.append(f"- {when} — {summary}")
    return "\n".join(lines) + "\n"


def _render_reminders(rems: List[Dict[str, Any]]) -> str:
    if not rems:
        return "## Reminders\n_No items_\n"
    lines = ["## Reminders"]
    for r in rems[:10]:
        at = (
            r["remind_at"].strftime("%H:%M")
            if isinstance(r.get("remind_at"), datetime)
            else "?"
        )
        lines.append(f"- {at} — {r.get('message', '')}")
    return "\n".join(lines) + "\n"


def _render_alerts(alerts: List[Dict[str, Any]]) -> str:
    if not alerts:
        return "## Alerts\n_No items_\n"
    lines = ["## Alerts"]
    for a in alerts[:10]:
        lines.append(
            f"- [{a.get('severity', '?')}] {a.get('alertname', '?')} @ {a.get('instance', '?')}"
        )
    return "\n".join(lines) + "\n"


def _render_overnight(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "## Overnight Activity\n_No items_\n"
    lines = ["## Overnight Activity"]
    for row in rows[:10]:
        name = row.get("task_name", "?")
        resp = (row.get("response") or "")[:120].replace("\n", " ")
        lines.append(f"- **{name}** — {resp}")
    return "\n".join(lines) + "\n"


async def assemble_digest(*, horizon_hours: int = 24) -> str:
    """Assemble the morning brief as markdown.

    Returns an empty string if every section is empty (nothing worth
    bothering the user with — the "should I bother the user" decision).
    """
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=horizon_hours)

    tasks = _fetch_tasks(horizon)
    events = _fetch_calendar(horizon)
    reminders = _fetch_reminders(horizon)
    alerts = _fetch_alerts()
    overnight = _fetch_overnight_scheduler()

    if not (tasks or events or reminders or alerts or overnight):
        return ""

    header = f"# Heartbeat — {now.strftime('%a %Y-%m-%d')}\n\n"
    body = "\n".join(
        [
            _render_tasks(tasks),
            _render_calendar(events),
            _render_reminders(reminders),
            _render_alerts(alerts),
            _render_overnight(overnight),
        ]
    )
    return header + body
