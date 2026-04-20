"""Project-hierarchy MCP tools — milestones, project_tasks, explorations.

Parallel surface to beto's confirm-required `telos_add_milestone`,
`telos_add_task`, `telos_complete_milestone`, `telos_complete_task`,
`telos_archive_task`, and `telos_add_exploration` tools. These call the
same `radbot.tools.telos.db` primitives directly; user confirmation is
expected at the MCP client UI layer (e.g. Claude Code approval) rather
than enforced here.

Children all live in the single `telos_entries` table in sections
`milestones`, `project_tasks`, `explorations`. Their ownership is stored
as `metadata.parent_project` (+ optional `metadata.parent_milestone`
for tasks). Never hard-deletes — archive only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from mcp import types as mcp_types


_VALID_TASK_STATUSES = {"backlog", "inprogress", "done"}


def tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="milestone_add",
            description=(
                "Add a milestone under a project. Auto-assigns an `MS<N>` "
                "ref_code. `deadline` is optional ISO date. `details` is "
                "appended below the title in content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_project": {
                        "type": "string",
                        "description": "Project ref_code (e.g. `PRJ1`).",
                    },
                    "title": {"type": "string"},
                    "deadline": {"type": "string"},
                    "details": {"type": "string"},
                },
                "required": ["parent_project", "title"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="milestone_complete",
            description=(
                "Mark a milestone completed. Sets status='completed' and "
                "stamps `metadata.completed_at`. Optional `resolution` "
                "string is merged into metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "resolution": {"type": "string"},
                },
                "required": ["ref_code"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="task_add",
            description=(
                "Create a project task under an existing project (and "
                "optionally a milestone). Auto-assigns a `PT<N>` ref_code. "
                "`task_status` ∈ backlog / inprogress / done, default "
                "backlog."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_project": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_milestone": {"type": "string"},
                    "title": {"type": "string"},
                    "category": {"type": "string"},
                    "task_status": {
                        "type": "string",
                        "enum": ["backlog", "inprogress", "done"],
                    },
                },
                "required": ["parent_project", "description"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="task_update",
            description=(
                "Update a project task in place. `description` replaces "
                "content; other fields shallow-merge into metadata. Pass "
                "an empty string to clear an optional field."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "description": {"type": "string"},
                    "title": {"type": "string"},
                    "category": {"type": "string"},
                    "task_status": {
                        "type": "string",
                        "enum": ["backlog", "inprogress", "done"],
                    },
                    "parent_milestone": {"type": "string"},
                },
                "required": ["ref_code"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="task_complete",
            description=(
                "Mark a project task done. Sets "
                "`metadata.task_status='done'` and stamps "
                "`metadata.completed_at`."
            ),
            inputSchema={
                "type": "object",
                "properties": {"ref_code": {"type": "string"}},
                "required": ["ref_code"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="task_archive",
            description=(
                "Archive (soft-delete) a project task. Stashes `reason` "
                "into `metadata.archived_reason`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["ref_code"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="exploration_add",
            description=(
                "Record an open exploration / research thread under a "
                "project. Auto-assigns an `EX<N>` ref_code. `notes` is "
                "appended below the topic in content."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_project": {"type": "string"},
                    "topic": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["parent_project", "topic"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="exploration_update",
            description=(
                "Update an exploration in place. `content` (required) "
                "replaces the exploration's body — typically the full "
                "5-role plan markdown, often with a `## Council Review` "
                "trailer. Other fields shallow-merge into metadata. Pass "
                "empty string to clear an optional field."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "content": {"type": "string"},
                    "parent_project": {"type": "string"},
                    "parent_milestone": {"type": "string"},
                },
                "required": ["ref_code", "content"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="exploration_archive",
            description=(
                "Archive (soft-delete) an exploration. Used when a research "
                "thread is closed — either because the plan it captured has "
                "been implemented or because the question is no longer "
                "relevant. Stashes `reason` into `metadata.archived_reason`. "
                "Never hard-deletes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["ref_code"],
                "additionalProperties": False,
            },
        ),
    ]


async def call(
    name: str, arguments: dict[str, Any]
) -> list[mcp_types.TextContent]:
    if name == "milestone_add":
        return [_do_milestone_add(
            arguments["parent_project"],
            arguments["title"],
            arguments.get("deadline"),
            arguments.get("details"),
        )]
    if name == "milestone_complete":
        return [_do_milestone_complete(
            arguments["ref_code"],
            arguments.get("resolution"),
        )]
    if name == "task_add":
        return [_do_task_add(arguments)]
    if name == "task_update":
        return [_do_task_update(arguments)]
    if name == "task_complete":
        return [_do_task_complete(arguments["ref_code"])]
    if name == "task_archive":
        return [_do_task_archive(
            arguments["ref_code"],
            arguments.get("reason"),
        )]
    if name == "exploration_add":
        return [_do_exploration_add(
            arguments["parent_project"],
            arguments["topic"],
            arguments.get("notes"),
        )]
    if name == "exploration_update":
        return [_do_exploration_update(arguments)]
    if name == "exploration_archive":
        return [_do_exploration_archive(
            arguments["ref_code"],
            arguments.get("reason"),
        )]
    raise KeyError(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _err(msg: str) -> mcp_types.TextContent:
    return mcp_types.TextContent(type="text", text=f"**Error:** {msg}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_project(ref_code: str):
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    project = telos_db.get_entry(Section.PROJECTS, ref_code)
    if project is None:
        return None, _err(f"No Telos project with ref_code `{ref_code}`.")
    return project, None


def _require_milestone(ref_code: str):
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    row = telos_db.get_entry(Section.MILESTONES, ref_code)
    if row is None:
        return None, _err(f"No milestone with ref_code `{ref_code}`.")
    return row, None


def _do_milestone_add(
    parent_project: str, title: str, deadline: str | None, details: str | None
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    clean_title = (title or "").strip()
    if not clean_title:
        return _err("`title` is required and must not be whitespace.")
    _p, err = _require_project(parent_project)
    if err is not None:
        return err

    content = clean_title if not details else f"{clean_title}\n\n{details}"
    metadata: dict[str, Any] = {"parent_project": parent_project}
    if deadline:
        metadata["deadline"] = deadline
    row = telos_db.add_entry(Section.MILESTONES, content, metadata=metadata)
    return mcp_types.TextContent(
        type="text",
        text=(
            f"Added milestone `{row.ref_code}` under `{parent_project}` — "
            f"{clean_title!r}"
        ),
    )


def _do_milestone_complete(
    ref_code: str, resolution: str | None
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    meta: dict[str, Any] = {"completed_at": _now_iso()}
    if resolution:
        meta["resolution"] = resolution
    row = telos_db.update_entry(
        Section.MILESTONES, ref_code, status="completed", metadata_merge=meta,
    )
    if row is None:
        return _err(f"No milestone with ref_code `{ref_code}`.")
    bits = [f"completed_at={meta['completed_at']}"]
    if resolution:
        bits.append(f"resolution={resolution!r}")
    return mcp_types.TextContent(
        type="text",
        text=f"Completed milestone `{ref_code}` — {' · '.join(bits)}",
    )


def _do_task_add(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    description = (arguments.get("description") or "").strip()
    parent_project = arguments["parent_project"]
    if not description:
        return _err("`description` is required and must not be whitespace.")
    _p, err = _require_project(parent_project)
    if err is not None:
        return err

    parent_milestone = arguments.get("parent_milestone") or ""
    if parent_milestone:
        _ms, err = _require_milestone(parent_milestone)
        if err is not None:
            return err

    task_status = arguments.get("task_status") or "backlog"
    if task_status not in _VALID_TASK_STATUSES:
        return _err(
            f"invalid task_status {task_status!r}. "
            f"valid: {sorted(_VALID_TASK_STATUSES)}."
        )

    metadata: dict[str, Any] = {
        "parent_project": parent_project,
        "task_status": task_status,
    }
    if parent_milestone:
        metadata["parent_milestone"] = parent_milestone
    if arguments.get("title"):
        metadata["title"] = arguments["title"]
    if arguments.get("category"):
        metadata["category"] = arguments["category"]

    row = telos_db.add_entry(Section.PROJECT_TASKS, description, metadata=metadata)
    return mcp_types.TextContent(
        type="text",
        text=(
            f"Added task `{row.ref_code}` under `{parent_project}`"
            + (f" / `{parent_milestone}`" if parent_milestone else "")
            + f" — status={task_status}"
        ),
    )


def _do_task_update(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ref_code = arguments["ref_code"]
    content: str | None = None
    description = arguments.get("description")
    if description is not None:
        clean = description.strip()
        if not clean:
            return _err("`description` must not be whitespace if provided.")
        content = clean

    meta: dict[str, Any] = {}
    for key in ("title", "category", "task_status", "parent_milestone"):
        if key in arguments and arguments[key] is not None:
            value = arguments[key]
            if key == "task_status" and value and value not in _VALID_TASK_STATUSES:
                return _err(
                    f"invalid task_status {value!r}. "
                    f"valid: {sorted(_VALID_TASK_STATUSES)}."
                )
            # Empty string → remove key via shallow JSONB merge with null.
            meta[key] = value if value != "" else None

    if meta.get("parent_milestone"):
        _ms, err = _require_milestone(meta["parent_milestone"])
        if err is not None:
            return err

    row = telos_db.update_entry(
        Section.PROJECT_TASKS,
        ref_code,
        content=content,
        metadata_merge=meta or None,
    )
    if row is None:
        return _err(f"No task with ref_code `{ref_code}`.")
    bits: list[str] = []
    if content is not None:
        bits.append("description updated")
    if meta:
        bits.append(f"metadata_merge={meta}")
    if not bits:
        bits.append("no-op")
    return mcp_types.TextContent(
        type="text",
        text=f"Updated task `{ref_code}` — {' · '.join(bits)}",
    )


def _do_task_complete(ref_code: str) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    row = telos_db.update_entry(
        Section.PROJECT_TASKS,
        ref_code,
        metadata_merge={"task_status": "done", "completed_at": _now_iso()},
    )
    if row is None:
        return _err(f"No task with ref_code `{ref_code}`.")
    return mcp_types.TextContent(
        type="text", text=f"Completed task `{ref_code}`."
    )


def _do_task_archive(ref_code: str, reason: str | None) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ok = telos_db.archive_entry(
        Section.PROJECT_TASKS, ref_code, reason=reason or None
    )
    if not ok:
        return _err(f"No task with ref_code `{ref_code}`.")
    tail = f" (reason: {reason})" if reason else ""
    return mcp_types.TextContent(
        type="text", text=f"Archived task `{ref_code}`.{tail}"
    )


def _do_exploration_add(
    parent_project: str, topic: str, notes: str | None
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    clean_topic = (topic or "").strip()
    if not clean_topic:
        return _err("`topic` is required and must not be whitespace.")
    _p, err = _require_project(parent_project)
    if err is not None:
        return err

    content = clean_topic if not notes else f"{clean_topic}\n\n{notes}"
    row = telos_db.add_entry(
        Section.EXPLORATIONS, content, metadata={"parent_project": parent_project}
    )
    return mcp_types.TextContent(
        type="text",
        text=(
            f"Added exploration `{row.ref_code}` under `{parent_project}` — "
            f"{clean_topic!r}"
        ),
    )


def _do_exploration_update(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ref_code = arguments["ref_code"]
    content = (arguments.get("content") or "").strip()
    if not content:
        return _err("`content` is required and must not be whitespace.")

    meta: dict[str, Any] = {}
    for key in ("parent_project", "parent_milestone"):
        if key in arguments and arguments[key] is not None:
            # Empty string → remove key via shallow JSONB merge with null.
            meta[key] = arguments[key] if arguments[key] != "" else None

    # Validate parent refs if being set (non-empty)
    if meta.get("parent_project"):
        _p, err = _require_project(meta["parent_project"])
        if err is not None:
            return err
    if meta.get("parent_milestone"):
        _ms, err = _require_milestone(meta["parent_milestone"])
        if err is not None:
            return err

    row = telos_db.update_entry(
        Section.EXPLORATIONS,
        ref_code,
        content=content,
        metadata_merge=meta or None,
    )
    if row is None:
        return _err(f"No exploration with ref_code `{ref_code}`.")
    bits = ["content updated"]
    if meta:
        bits.append(f"metadata_merge={meta}")
    return mcp_types.TextContent(
        type="text",
        text=f"Updated exploration `{ref_code}` — {' · '.join(bits)}",
    )


def _do_exploration_archive(
    ref_code: str, reason: str | None
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ok = telos_db.archive_entry(
        Section.EXPLORATIONS, ref_code, reason=reason or None
    )
    if not ok:
        return _err(f"No exploration with ref_code `{ref_code}`.")
    tail = f" (reason: {reason})" if reason else ""
    return mcp_types.TextContent(
        type="text", text=f"Archived exploration `{ref_code}`.{tail}"
    )
