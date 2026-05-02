"""Task / reminder / scheduler MCP tools.

Return format: markdown. All heavy imports are lazy (DB connection, scheduler
engine, etc.) to keep module-import cost minimal.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from mcp import types as mcp_types

# Strip URLs (and surrounding whitespace) from project names so labels stay
# compact when used as the per-row prefix in `_render_tasks` (EX46 / PT115).
_URL_RE = re.compile(r"\s*https?://\S+")


def tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="list_tasks",
            description=(
                "List radbot project tasks (Telos-backed), grouped by kanban "
                "status. Active tasks (backlog + inprogress) only by default — "
                "pass `include_done=true` (or `status=done`) for completed "
                "history. Optional filters: `status` "
                "(backlog/inprogress/done), `project` (ref_code like `PRJ1` "
                "or a substring of the project name), and `include_done`."
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
                    "include_done": {
                        "type": "boolean",
                        "description": (
                            "Include the `done` bucket. Default false to "
                            "keep response size bounded as completed work "
                            "accumulates. Use `list_archived_tasks` for "
                            "deeper historical queries."
                        ),
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
        return [
            _render_tasks(
                arguments.get("status"),
                arguments.get("project"),
                bool(arguments.get("include_done", False)),
            )
        ]
    if name == "list_reminders":
        return [_render_reminders(arguments.get("status", "pending"))]
    if name == "list_scheduled_tasks":
        return [_render_scheduled()]
    raise KeyError(name)


def _shorten_project_name(name: str) -> str:
    """Trim URLs out of a project name and collapse whitespace for the
    `[proj_name]` label used in `_render_tasks`. PRJ1's content is e.g.
    `"radbot https://github.com/perrymanuk/radbot"` — the URL adds ~30+ chars
    of duplication on every row (EX46 / PT115)."""
    cleaned = _URL_RE.sub("", name or "").strip()
    return cleaned or name


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


def _render_tasks(
    status: str | None,
    project: str | None,
    include_done: bool = False,
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    if status and status not in ("backlog", "inprogress", "done"):
        return mcp_types.TextContent(
            type="text", text=f"**Error:** invalid status `{status}`"
        )

    # Done is always included when the caller explicitly filters to status=done,
    # regardless of include_done. Otherwise default-hide it to keep the
    # response bounded as completed work piles up (EX46 / PT115).
    show_done = include_done or status == "done"

    # Resolve project filter to a ref_code (exact or substring match).
    project_filter_ref: str | None = None
    project_names: dict[str, str] = {}
    for p in telos_db.list_section(Section.PROJECTS, status="active"):
        if p.ref_code:
            raw = (p.content or "").splitlines()[0].strip() or p.ref_code
            project_names[p.ref_code] = _shorten_project_name(raw)
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
        if not show_done and st == "done":
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
                "include_done=false" if not show_done else None,
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
