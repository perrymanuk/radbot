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

Return contract (Item 0.b.iv of the council-loop-polish EX). The four
creation handlers — `_do_task_add`, `_do_exploration_add`,
`_do_milestone_add`, and the new `_do_journal_add` (in `journal.py`) —
return JSON `TextContent`:

    {"status": "success", "ref_code": "<NEW>", "entry_id": "<uuid>",
     "section": "<section>"}

Errors return JSON too:

    {"status": "error", "message": "<reason>"}

The four `*_update` handlers + `journal_update` use the same JSON `_err`
envelope so chained callers can branch on `payload["status"]` after
`json.loads(response.text)` without try/except + heuristic detection.
The terminal operations (`*_complete`, `*_archive`) keep human-readable
text returns — callers there already know the ref_code.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from mcp import types as mcp_types

_VALID_TASK_STATUSES = {"backlog", "inprogress", "done"}

# Whitelist keys the typed schema fields drive — they overlay any
# `metadata_merge` value supplied by the caller (silent collision; council
# 3-of-3 consensus to keep silent rather than error, for LLM tool-call
# ergonomics).
_TASK_WHITELIST_KEYS = ("title", "category", "task_status", "parent_milestone")


def tools() -> list[mcp_types.Tool]:
    from radbot.tools.telos.models import STATUS_VALUES

    sorted_status = sorted(STATUS_VALUES)
    return [
        mcp_types.Tool(
            name="milestone_add",
            description=(
                "Add a milestone under a project. Auto-assigns an `MS<N>` "
                "ref_code. `deadline` is optional ISO date. `details` is "
                "appended below the title in content. Returns JSON: "
                "`{status, ref_code, entry_id, section}`."
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
                    "metadata_merge": {
                        "type": "object",
                        "description": (
                            "Extra keys to attach to `metadata` at creation. "
                            "Whitelist keys (parent_project, deadline) win on "
                            "collision."
                        ),
                        "additionalProperties": True,
                    },
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
                "backlog. `metadata_merge` attaches arbitrary metadata "
                "atomically at creation (whitelist keys win on collision). "
                "Returns JSON: `{status, ref_code, entry_id, section}`."
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
                    "metadata_merge": {
                        "type": "object",
                        "description": (
                            "Extra keys to attach to `metadata` at creation. "
                            "Whitelist keys (title, category, task_status, "
                            "parent_milestone, parent_project) win on collision."
                        ),
                        "additionalProperties": True,
                    },
                },
                "required": ["parent_project", "description"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="task_update",
            description=(
                "Update a project task in place. `description` (optional) "
                "replaces content when present and non-whitespace; absent "
                "= leave body unchanged. Whitelisted fields shallow-merge "
                "into metadata; whitelist keys win on collision with "
                "`metadata_merge`."
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
                    "metadata_merge": {
                        "type": "object",
                        "description": (
                            "Extra keys to merge into `metadata`. "
                            "Whitelist keys (title, category, task_status, "
                            "parent_milestone) win on collision."
                        ),
                        "additionalProperties": True,
                    },
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
                "appended below the topic in content. Optional `status` "
                "lets Scout create the row directly in a lifecycle state "
                "(e.g. `proposed`); defaults to `active` for back-compat. "
                "`metadata_merge` attaches arbitrary metadata atomically "
                "(whitelist key `parent_project` wins on collision). "
                "Returns JSON: `{status, ref_code, entry_id, section}`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "parent_project": {"type": "string"},
                    "topic": {"type": "string"},
                    "notes": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": sorted_status,
                    },
                    "metadata_merge": {
                        "type": "object",
                        "description": (
                            "Extra keys to attach to `metadata` at creation. "
                            "Whitelist key `parent_project` wins on collision."
                        ),
                        "additionalProperties": True,
                    },
                },
                "required": ["parent_project", "topic"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="exploration_update",
            description=(
                "Update an exploration in place. `content` (optional) "
                "replaces the body when present and non-whitespace; absent "
                "= leave body unchanged; empty/whitespace = error. "
                "`status` flips lifecycle state (validated against the "
                "extended STATUS_VALUES set). Whitelisted fields shallow-"
                "merge into metadata; whitelist keys win on collision with "
                "`metadata_merge`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "content": {"type": "string"},
                    "parent_project": {"type": "string"},
                    "parent_milestone": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": sorted_status,
                    },
                    "metadata_merge": {
                        "type": "object",
                        "description": (
                            "Extra keys to merge into `metadata`. "
                            "Whitelist keys (parent_project, "
                            "parent_milestone) win on collision."
                        ),
                        "additionalProperties": True,
                    },
                },
                "required": ["ref_code"],
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


async def call(name: str, arguments: dict[str, Any]) -> list[mcp_types.TextContent]:
    if name == "milestone_add":
        return [_do_milestone_add(arguments)]
    if name == "milestone_complete":
        return [
            _do_milestone_complete(
                arguments["ref_code"],
                arguments.get("resolution"),
            )
        ]
    if name == "task_add":
        return [_do_task_add(arguments)]
    if name == "task_update":
        return [_do_task_update(arguments)]
    if name == "task_complete":
        return [_do_task_complete(arguments["ref_code"])]
    if name == "task_archive":
        return [
            _do_task_archive(
                arguments["ref_code"],
                arguments.get("reason"),
            )
        ]
    if name == "exploration_add":
        return [_do_exploration_add(arguments)]
    if name == "exploration_update":
        return [_do_exploration_update(arguments)]
    if name == "exploration_archive":
        return [
            _do_exploration_archive(
                arguments["ref_code"],
                arguments.get("reason"),
            )
        ]
    raise KeyError(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_err(msg: str) -> mcp_types.TextContent:
    """Plain-text error for terminal operations whose callers already know
    the ref_code (`*_complete`, `*_archive`, `milestone_complete`)."""
    return mcp_types.TextContent(type="text", text=f"**Error:** {msg}")


def _json_err(msg: str) -> mcp_types.TextContent:
    """JSON error envelope for `*_add` and `*_update` handlers — uniform
    with the success contract so chained callers can branch on
    `json.loads(response.text)["status"]` without try/except."""
    return mcp_types.TextContent(
        type="text", text=json.dumps({"status": "error", "message": msg})
    )


def _json_ok_add(row: Any) -> mcp_types.TextContent:
    """Structured success envelope for the four `*_add` handlers
    (Item 0.b.iv contract)."""
    payload = {
        "status": "success",
        "ref_code": row.ref_code,
        "entry_id": str(row.entry_id) if row.entry_id else None,
        "section": row.section.value,
    }
    return mcp_types.TextContent(type="text", text=json.dumps(payload))


def _json_ok_update(ref_code: str, **extras: Any) -> mcp_types.TextContent:
    """Structured success envelope for `*_update` handlers.

    Envelope key is `status: "success"` — same shape as the *_add contract
    (Item 0.b.iv) so consumers can branch on `payload["status"]` uniformly
    across every write tool. Any `status` key in extras is renamed to
    `entry_status` so the echoed lifecycle value never collides with the
    envelope discriminator.
    """
    payload: dict[str, Any] = {"status": "success", "ref_code": ref_code}
    if "status" in extras:
        extras["entry_status"] = extras.pop("status")
    payload.update(extras)
    return mcp_types.TextContent(type="text", text=json.dumps(payload))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_project(ref_code: str):
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    project = telos_db.get_entry(Section.PROJECTS, ref_code)
    if project is None:
        return None, _json_err(f"No Telos project with ref_code `{ref_code}`.")
    return project, None


def _require_milestone(ref_code: str):
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    row = telos_db.get_entry(Section.MILESTONES, ref_code)
    if row is None:
        return None, _json_err(f"No milestone with ref_code `{ref_code}`.")
    return row, None


def _validate_status(value: str | None):
    """Validate a `status` argument against the extended `STATUS_VALUES`
    set. Returns `(value, None)` on pass, `(None, error_TextContent)` on
    fail."""
    from radbot.tools.telos.models import STATUS_VALUES

    if value is None:
        return None, None
    if value not in STATUS_VALUES:
        return None, _json_err(
            f"invalid status {value!r}. valid: {sorted(STATUS_VALUES)}."
        )
    return value, None


def _merge_with_whitelist(
    caller_metadata: dict[str, Any] | None,
    whitelist_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Combine caller-supplied `metadata_merge` with the typed-field-derived
    whitelist dict. Per the load-bearing precedence rule (Item 0.b.iii), the
    whitelist keys WIN on collision — silently. Tests cover both no-collision
    survival and silent-collision paths."""
    combined: dict[str, Any] = {}
    if caller_metadata:
        combined.update(caller_metadata)
    combined.update(whitelist_metadata)
    return combined


def _do_milestone_add(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    parent_project = arguments["parent_project"]
    title = arguments.get("title")
    deadline = arguments.get("deadline")
    details = arguments.get("details")
    caller_meta = arguments.get("metadata_merge")

    clean_title = (title or "").strip()
    if not clean_title:
        return _json_err("`title` is required and must not be whitespace.")
    _p, err = _require_project(parent_project)
    if err is not None:
        return err

    content = clean_title if not details else f"{clean_title}\n\n{details}"
    whitelist: dict[str, Any] = {"parent_project": parent_project}
    if deadline:
        whitelist["deadline"] = deadline
    metadata = _merge_with_whitelist(caller_meta, whitelist)

    row = telos_db.add_entry(Section.MILESTONES, content, metadata=metadata)
    return _json_ok_add(row)


def _do_milestone_complete(
    ref_code: str, resolution: str | None
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    meta: dict[str, Any] = {"completed_at": _now_iso()}
    if resolution:
        meta["resolution"] = resolution
    row = telos_db.update_entry(
        Section.MILESTONES,
        ref_code,
        status="completed",
        metadata_merge=meta,
    )
    if row is None:
        return _text_err(f"No milestone with ref_code `{ref_code}`.")
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
        return _json_err("`description` is required and must not be whitespace.")
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
        return _json_err(
            f"invalid task_status {task_status!r}. "
            f"valid: {sorted(_VALID_TASK_STATUSES)}."
        )

    whitelist: dict[str, Any] = {
        "parent_project": parent_project,
        "task_status": task_status,
    }
    if parent_milestone:
        whitelist["parent_milestone"] = parent_milestone
    if arguments.get("title"):
        whitelist["title"] = arguments["title"]
    if arguments.get("category"):
        whitelist["category"] = arguments["category"]

    metadata = _merge_with_whitelist(arguments.get("metadata_merge"), whitelist)

    row = telos_db.add_entry(Section.PROJECT_TASKS, description, metadata=metadata)
    return _json_ok_add(row)


def _do_task_update(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ref_code = arguments["ref_code"]
    content: str | None = None
    if "description" in arguments:
        description = arguments["description"]
        if description is None or (
            isinstance(description, str) and not description.strip()
        ):
            return _json_err(
                "description must not be whitespace if supplied; "
                "omit the key to leave body unchanged."
            )
        content = description.strip()

    whitelist: dict[str, Any] = {}
    for key in _TASK_WHITELIST_KEYS:
        if key in arguments and arguments[key] is not None:
            value = arguments[key]
            if key == "task_status" and value and value not in _VALID_TASK_STATUSES:
                return _json_err(
                    f"invalid task_status {value!r}. "
                    f"valid: {sorted(_VALID_TASK_STATUSES)}."
                )
            whitelist[key] = value if value != "" else None

    if whitelist.get("parent_milestone"):
        _ms, err = _require_milestone(whitelist["parent_milestone"])
        if err is not None:
            return err

    meta = _merge_with_whitelist(arguments.get("metadata_merge"), whitelist)

    row = telos_db.update_entry(
        Section.PROJECT_TASKS,
        ref_code,
        content=content,
        metadata_merge=meta or None,
    )
    if row is None:
        return _json_err(f"No task with ref_code `{ref_code}`.")
    return _json_ok_update(
        ref_code, content_updated=content is not None, metadata_merge=meta
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
        return _text_err(f"No task with ref_code `{ref_code}`.")
    return mcp_types.TextContent(type="text", text=f"Completed task `{ref_code}`.")


def _do_task_archive(ref_code: str, reason: str | None) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ok = telos_db.archive_entry(Section.PROJECT_TASKS, ref_code, reason=reason or None)
    if not ok:
        return _text_err(f"No task with ref_code `{ref_code}`.")
    tail = f" (reason: {reason})" if reason else ""
    return mcp_types.TextContent(type="text", text=f"Archived task `{ref_code}`.{tail}")


def _do_exploration_add(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    parent_project = arguments["parent_project"]
    topic = arguments.get("topic")
    notes = arguments.get("notes")

    clean_topic = (topic or "").strip()
    if not clean_topic:
        return _json_err("`topic` is required and must not be whitespace.")
    _p, err = _require_project(parent_project)
    if err is not None:
        return err

    status, err = _validate_status(arguments.get("status"))
    if err is not None:
        return err

    content = clean_topic if not notes else f"{clean_topic}\n\n{notes}"
    whitelist: dict[str, Any] = {"parent_project": parent_project}
    metadata = _merge_with_whitelist(arguments.get("metadata_merge"), whitelist)

    add_kwargs: dict[str, Any] = {"metadata": metadata}
    if status is not None:
        add_kwargs["status"] = status

    row = telos_db.add_entry(Section.EXPLORATIONS, content, **add_kwargs)
    return _json_ok_add(row)


def _do_exploration_update(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ref_code = arguments["ref_code"]

    content: str | None = None
    if "content" in arguments:
        raw = arguments["content"]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return _json_err(
                "content must not be whitespace if supplied; "
                "omit the key to leave body unchanged."
            )
        content = raw.strip()

    status, err = _validate_status(arguments.get("status"))
    if err is not None:
        return err

    whitelist: dict[str, Any] = {}
    for key in ("parent_project", "parent_milestone"):
        if key in arguments and arguments[key] is not None:
            whitelist[key] = arguments[key] if arguments[key] != "" else None

    if whitelist.get("parent_project"):
        _p, err = _require_project(whitelist["parent_project"])
        if err is not None:
            return err
    if whitelist.get("parent_milestone"):
        _ms, err = _require_milestone(whitelist["parent_milestone"])
        if err is not None:
            return err

    meta = _merge_with_whitelist(arguments.get("metadata_merge"), whitelist)

    update_kwargs: dict[str, Any] = {
        "content": content,
        "metadata_merge": meta or None,
    }
    if status is not None:
        update_kwargs["status"] = status

    row = telos_db.update_entry(Section.EXPLORATIONS, ref_code, **update_kwargs)
    if row is None:
        return _json_err(f"No exploration with ref_code `{ref_code}`.")
    return _json_ok_update(
        ref_code,
        content_updated=content is not None,
        metadata_merge=meta,
        status=status,
    )


def _do_exploration_archive(ref_code: str, reason: str | None) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ok = telos_db.archive_entry(Section.EXPLORATIONS, ref_code, reason=reason or None)
    if not ok:
        return _text_err(f"No exploration with ref_code `{ref_code}`.")
    tail = f" (reason: {reason})" if reason else ""
    return mcp_types.TextContent(
        type="text", text=f"Archived exploration `{ref_code}`.{tail}"
    )
