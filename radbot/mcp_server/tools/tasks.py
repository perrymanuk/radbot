"""Task / reminder / scheduler MCP tools.

Return format: markdown. All heavy imports are lazy (DB connection, scheduler
engine, etc.) to keep module-import cost minimal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from mcp import types as mcp_types


def tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="list_tasks",
            description=(
                "List radbot todo tasks across all projects, grouped by status. "
                "Optional status filter: `backlog`, `inprogress`, or `done`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["backlog", "inprogress", "done"],
                    },
                    "project": {
                        "type": "string",
                        "description": "Filter to a specific project name.",
                    },
                },
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="list_reminders",
            description=(
                "List pending (or past) reminders. Default status=`pending`. "
                "Returns a markdown list with relative-time phrasing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "delivered", "cancelled"],
                        "default": "pending",
                    }
                },
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="list_scheduled_tasks",
            description=(
                "List APScheduler cron tasks: name, cron expression, prompt "
                "preview, enabled flag."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
    ]


async def call(
    name: str, arguments: dict[str, Any]
) -> list[mcp_types.TextContent]:
    if name == "list_tasks":
        return [_render_tasks(arguments.get("status"), arguments.get("project"))]
    if name == "list_reminders":
        return [_render_reminders(arguments.get("status", "pending"))]
    if name == "list_scheduled_tasks":
        return [_render_scheduled()]
    raise KeyError(name)


def _relative_time(dt: datetime) -> str:
    """Human-readable relative phrasing for a future (or past) UTC timestamp."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)
    delta = dt - now
    secs = int(delta.total_seconds())
    past = secs < 0
    secs = abs(secs)
    if secs < 60:
        unit = f"{secs}s"
    elif secs < 3600:
        unit = f"{secs // 60}m"
    elif secs < 86400:
        unit = f"{secs // 3600}h"
    elif secs < 86400 * 30:
        unit = f"{secs // 86400}d"
    else:
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    return f"{unit} ago" if past else f"in {unit}"


def _render_tasks(status: str | None, project: str | None) -> mcp_types.TextContent:
    from radbot.tools.todo.db.connection import get_db_connection
    from radbot.tools.todo.db.queries import list_all_tasks

    if status and status not in ("backlog", "inprogress", "done"):
        return mcp_types.TextContent(
            type="text", text=f"**Error:** invalid status `{status}`"
        )

    with get_db_connection() as conn:
        rows = list_all_tasks(conn, status_filter=status)

    if project:
        rows = [r for r in rows if r.get("project_name") == project]

    if not rows:
        filt = " · ".join(
            bit for bit in (
                f"status={status}" if status else None,
                f"project={project}" if project else None,
            ) if bit
        )
        return mcp_types.TextContent(
            type="text", text=f"_No tasks{(' (' + filt + ')') if filt else ''}._"
        )

    # Group by status for readability
    by_status: dict[str, list[dict[str, Any]]] = {
        "backlog": [], "inprogress": [], "done": [],
    }
    for r in rows:
        by_status.setdefault(r.get("status", "backlog"), []).append(r)

    lines: list[str] = []
    for st in ("inprogress", "backlog", "done"):
        bucket = by_status.get(st) or []
        if not bucket:
            continue
        lines.append(f"## {st} ({len(bucket)})")
        lines.append("")
        for r in bucket:
            title = r.get("title") or (r.get("description") or "").split("\n", 1)[0][:80]
            proj = r.get("project_name") or "—"
            lines.append(f"- **[{proj}]** {title}")
        lines.append("")
    return mcp_types.TextContent(type="text", text="\n".join(lines).rstrip())


def _render_reminders(status: str) -> mcp_types.TextContent:
    from radbot.tools.reminders import db as rem_db

    try:
        rows = rem_db.list_reminders(status=status)
    except Exception as e:
        return mcp_types.TextContent(
            type="text", text=f"**Error:** {e}"
        )

    if not rows:
        return mcp_types.TextContent(
            type="text", text=f"_No reminders with status `{status}`._"
        )

    lines = [f"## Reminders ({status}, {len(rows)})", ""]
    for r in rows:
        remind_at = r.get("remind_at")
        when = _relative_time(remind_at) if isinstance(remind_at, datetime) else str(remind_at)
        lines.append(f"- **{when}** — {r.get('message', '').strip()}")
    return mcp_types.TextContent(type="text", text="\n".join(lines))


def _render_scheduled() -> mcp_types.TextContent:
    from radbot.tools.scheduler import db as sched_db

    rows = sched_db.list_tasks()
    if not rows:
        return mcp_types.TextContent(
            type="text", text="_No scheduled tasks._"
        )

    lines = [
        "## Scheduled tasks",
        "",
        "| Name | Cron | Enabled | Prompt |",
        "|---|---|---|---|",
    ]
    for r in rows:
        name = r.get("name", "?")
        cron = r.get("cron_expression", "?")
        enabled = "✓" if r.get("enabled") else "—"
        prompt = (r.get("prompt") or "").replace("\n", " ")[:80]
        lines.append(f"| `{name}` | `{cron}` | {enabled} | {prompt} |")
    return mcp_types.TextContent(type="text", text="\n".join(lines))
