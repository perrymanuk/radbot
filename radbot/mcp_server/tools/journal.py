"""Journal-write MCP tools — direct wrappers around `telos_db.add_entry` /
`telos_db.update_entry` for `Section.JOURNAL`.

Item 0.a of the council-loop-polish EX. The MCP `journal_add` does NOT
delegate to the agent-side `telos_add_journal` (which has a narrower
signature — `entry: str`, `event_type: str = ""`, `related_refs: list[str]`
— and no return-shape contract). Going straight to `telos_db.add_entry`
gets us:

  - Arbitrary `metadata` dict (Scout's postmortem flow needs richer
    metadata than `event_type` + `related_refs`).
  - The structured-return contract (Item 0.b.iv) — `TextContent.text` is
    JSON: `{"status": "success", "ref_code": "<JR<N>>", "entry_id":
    "<uuid>", "section": "journal"}`.
  - The shared-layer postmortem invariant (Item 3) — when
    `metadata.type == "postmortem"`, `metadata.processed_at` MUST be set
    (initially `null`); the invariant is enforced inside `db.add_entry`,
    so it covers this caller automatically.

`journal_update` supports `metadata_merge` and a journal-meaningful
`status` enum (`active`, `completed`, `archived`, `superseded` — the
lifecycle states like `proposed/in_review/approved/executing` are nonsense
for journal rows and excluded by the JSON-schema enum).
"""

from __future__ import annotations

import json
from typing import Any

from mcp import types as mcp_types

# Lifecycle states are nonsense for journal rows; restrict the allowed set.
_JOURNAL_STATUSES = ["active", "completed", "archived", "superseded"]


def tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="journal_add",
            description=(
                "Append a Telos journal entry. Auto-assigns a `JR<N>` "
                "ref_code. `metadata` is an arbitrary JSONB dict. "
                "Postmortem entries (`metadata.type == 'postmortem'`) "
                "MUST include `metadata.processed_at` (initially `null`) "
                "or the call fails — this enables the unprocessed-postmortem "
                "query Scout's processing pass depends on. Returns JSON: "
                "`{status, ref_code, entry_id, section}`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entry": {"type": "string"},
                    "metadata": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
                "required": ["entry"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="journal_update",
            description=(
                "Update a Telos journal entry by `ref_code`. Supports "
                "`metadata_merge` (shallow JSONB merge) and a "
                "journal-meaningful `status` (active/completed/archived/"
                "superseded — lifecycle states are not valid here). Returns "
                "JSON: `{status, ref_code}` on success; `_err` envelope on "
                "failure."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "metadata_merge": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "status": {
                        "type": "string",
                        "enum": _JOURNAL_STATUSES,
                    },
                },
                "required": ["ref_code"],
                "additionalProperties": False,
            },
        ),
    ]


async def call(name: str, arguments: dict[str, Any]) -> list[mcp_types.TextContent]:
    if name == "journal_add":
        return [_do_journal_add(arguments)]
    if name == "journal_update":
        return [_do_journal_update(arguments)]
    raise KeyError(name)


def _json_err(msg: str) -> mcp_types.TextContent:
    return mcp_types.TextContent(
        type="text", text=json.dumps({"status": "error", "message": msg})
    )


def _json_ok_add(row: Any) -> mcp_types.TextContent:
    payload = {
        "status": "success",
        "ref_code": row.ref_code,
        "entry_id": str(row.entry_id) if row.entry_id else None,
        "section": row.section.value,
    }
    return mcp_types.TextContent(type="text", text=json.dumps(payload))


def _json_ok_update(ref_code: str, **extras: Any) -> mcp_types.TextContent:
    payload: dict[str, Any] = {"status": "success", "ref_code": ref_code}
    if "status" in extras:
        extras["entry_status"] = extras.pop("status")
    payload.update(extras)
    return mcp_types.TextContent(type="text", text=json.dumps(payload))


def _do_journal_add(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    entry = (arguments.get("entry") or "").strip()
    if not entry:
        return _json_err("`entry` is required and must not be whitespace.")
    metadata = arguments.get("metadata") or {}

    try:
        row = telos_db.add_entry(Section.JOURNAL, entry, metadata=metadata)
    except ValueError as exc:
        return _json_err(str(exc))
    return _json_ok_add(row)


def _do_journal_update(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ref_code = arguments["ref_code"]
    metadata_merge = arguments.get("metadata_merge") or None
    status = arguments.get("status")

    if status is not None and status not in _JOURNAL_STATUSES:
        return _json_err(
            f"invalid journal status {status!r}. valid: {_JOURNAL_STATUSES}."
        )

    update_kwargs: dict[str, Any] = {"metadata_merge": metadata_merge}
    if status is not None:
        update_kwargs["status"] = status

    row = telos_db.update_entry(Section.JOURNAL, ref_code, **update_kwargs)
    if row is None:
        return _json_err(f"No journal entry with ref_code `{ref_code}`.")
    return _json_ok_update(ref_code, status=status, metadata_merge=metadata_merge)
