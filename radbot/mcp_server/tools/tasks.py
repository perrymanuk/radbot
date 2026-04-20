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
                "List radbot project tasks (Telos-backed), grouped by kanban "
                "status. Optional filters: `status` (backlog/inprogress/done) "
                "and `project` (ref_code like `PRJ1` or a substring of the "
                "project name)."
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
                        "description": "Filter to a project by ref_code or name substring.",
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


async def call(name: str, arguments: dict[str, Any]) -> list[mcp_types.TextContent]:
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
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    if status and status not in ("backlog", "inprogress", "done"):
        return mcp_types.TextContent(
            type="text", text=f"**Error:** invalid status `{status}`"
        )

    # Resolve project filter to a ref_code (exact or substring match).
    project_filter_ref: str | None = None
    project_names: dict[str, str] = {}
    for p in telos_db.list_section(Section.PROJECTS, status="active"):
        if p.ref_code:
            project_names[p.ref_code] = (p.content or "").splitlines()[
                0
            ].strip() or p.ref_code
    if project:
        needle = project.strip().lower()
        if project in project_names:
            project_filter_ref = project
        else:
            for ref, name in project_names.items():
                if needle == name.lower() or needle in name.lower():
                    project_filter_ref = ref
                    break
        if project_filter_ref is None:
            return mcp_types.TextContent(
                type="text", text=f"_No project matching `{project}`._"
            )

    rows = telos_db.list_section(
        Section.PROJECT_TASKS, status="active", order_by="sort_order_asc"
    )
    by_status: dict[str, list[tuple[str, str, str]]] = {
        "backlog": [],
        "inprogress": [],
        "done": [],
    }
    for r in rows:
        meta = r.metadata or {}
        st = meta.get("task_status") or "backlog"
        if status and st != status:
            continue
        parent_ref = meta.get("parent_project") or ""
        if project_filter_ref and parent_ref != project_filter_ref:
            continue
        proj_name = project_names.get(parent_ref, parent_ref or "—")
        title = meta.get("title") or (r.content or "").split("\n", 1)[0][:80]
        by_status.setdefault(st, []).append((r.ref_code or "?", proj_name, title))

    if not any(by_status.values()):
        filt = " · ".join(
            bit
            for bit in (
                f"status={status}" if status else None,
                f"project={project}" if project else None,
            )
            if bit
        )
        return mcp_types.TextContent(
            type="text", text=f"_No tasks{(' (' + filt + ')') if filt else ''}._"
        )

    lines: list[str] = []
    for st in ("inprogress", "backlog", "done"):
        bucket = by_status.get(st) or []
        if not bucket:
            continue
        lines.append(f"## {st} ({len(bucket)})")
        lines.append("")
        for ref_code, proj_name, title in bucket:
            lines.append(f"- `{ref_code}` **[{proj_name}]** {title}")
        lines.append("")
    return mcp_types.TextContent(type="text", text="\n".join(lines).rstrip())


def _render_reminders(status: str) -> mcp_types.TextContent:
    from radbot.tools.reminders import db as rem_db

    try:
        rows = rem_db.list_reminders(status=status)
    except Exception as e:
        return mcp_types.TextContent(type="text", text=f"**Error:** {e}")

    if not rows:
        return mcp_types.TextContent(
            type="text", text=f"_No reminders with status `{status}`._"
        )

    lines = [f"## Reminders ({status}, {len(rows)})", ""]
    for r in rows:
        remind_at = r.get("remind_at")
        when = (
            _relative_time(remind_at)
            if isinstance(remind_at, datetime)
            else str(remind_at)
        )
        lines.append(f"- **{when}** — {r.get('message', '').strip()}")
    return mcp_types.TextContent(type="text", text="\n".join(lines))


def _render_scheduled() -> mcp_types.TextContent:
    from radbot.tools.scheduler import db as sched_db

    rows = sched_db.list_tasks()
    if not rows:
        return mcp_types.TextContent(type="text", text="_No scheduled tasks._")

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
