"""Telos MCP tools — expose radbot's user-context store to external clients.

Read-only tools. Two return formats per Item 0.c of the council-loop-polish
EX:
  - `format="markdown"` (default, back-compat) — rendered for human/LLM eyes.
  - `format="json"` — `TextContent.text = json.dumps(payload)` parseable via
    `json.loads(response.text)`. Timestamps are ISO 8601 with literal `Z`
    suffix (UTC); `metadata` is the decoded JSONB dict; UUIDs render as
    strings; `Section` enums render as their `.value`. The single source of
    truth is `_entry_to_json_dict` + `_iso_default` below.

Heavy imports are lazy to keep module-import cost minimal.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from mcp import types as mcp_types

if TYPE_CHECKING:
    from radbot.tools.telos.models import Entry


_FORMAT_MARKDOWN = "markdown"
_FORMAT_JSON = "json"
_VALID_FORMATS = (_FORMAT_MARKDOWN, _FORMAT_JSON)


def tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="telos_get_full",
            description=(
                "Return the full Telos user context as canonical markdown "
                "(identity, mission, goals, projects, wisdom, recent journal, "
                "etc.). Use sparingly — this can be large. Prefer "
                "`telos_get_section` when only one area is relevant."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="telos_get_section",
            description=(
                "Return all entries in one Telos section. Default format is "
                "markdown; pass `format='json'` for `{\"entries\": [...]}` "
                "parseable via `json.loads(response.text)`. "
                "`metadata_filter` (JSONB `@>`) restricts to rows whose "
                "`metadata` contains the supplied object. Default "
                "`include_inactive=false` excludes completed/archived/"
                "superseded — but lifecycle states (proposed/in_review/"
                "approved/executing) are included by default. "
                "Sections: identity, history, problems, mission, narratives, "
                "goals, challenges, strategies, projects, milestones, "
                "project_tasks, explorations, wisdom, ideas, predictions, "
                "wrong_about, best_books, best_movies, best_music, taste, "
                "traumas, metrics, journal."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "description": "Lowercase section name.",
                    },
                    "include_inactive": {
                        "type": "boolean",
                        "description": (
                            "Include completed/archived/superseded entries. "
                            "Default false (active + lifecycle states)."
                        ),
                        "default": False,
                    },
                    "metadata_filter": {
                        "type": "object",
                        "description": (
                            "JSONB containment filter — entries whose "
                            "`metadata` `@>` this object are returned."
                        ),
                        "additionalProperties": True,
                    },
                    "format": {
                        "type": "string",
                        "enum": list(_VALID_FORMATS),
                        "description": (
                            "Response format. `markdown` (default) for "
                            "human-rendered; `json` for machine-parseable."
                        ),
                        "default": _FORMAT_MARKDOWN,
                    },
                },
                "required": ["section"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="telos_get_entry",
            description=(
                "Fetch one Telos entry by (section, ref_code). Use when you "
                "know the ref_code (e.g. 'G1', 'P2', 'PRED3'). Identity's "
                "ref_code is 'ME'. Default format is markdown; pass "
                "`format='json'` for `{\"entry\": {...}}` parseable via "
                "`json.loads(response.text)`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "ref_code": {"type": "string"},
                    "format": {
                        "type": "string",
                        "enum": list(_VALID_FORMATS),
                        "default": _FORMAT_MARKDOWN,
                    },
                },
                "required": ["section", "ref_code"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="telos_search_journal",
            description=(
                "Case-insensitive substring search over Telos journal entries. "
                "Returns newest matches first. Use for 'have I ever mentioned X?' "
                "questions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
    ]


async def call(name: str, arguments: dict[str, Any]) -> list[mcp_types.TextContent]:
    if name == "telos_get_full":
        return [_render_full()]
    if name == "telos_get_section":
        return [
            _render_section(
                arguments["section"],
                bool(arguments.get("include_inactive", False)),
                arguments.get("metadata_filter") or None,
                arguments.get("format", _FORMAT_MARKDOWN),
            )
        ]
    if name == "telos_get_entry":
        return [
            _render_entry(
                arguments["section"],
                arguments["ref_code"],
                arguments.get("format", _FORMAT_MARKDOWN),
            )
        ]
    if name == "telos_search_journal":
        return [
            _render_journal_search(
                arguments["query"],
                int(arguments.get("limit", 20)),
            )
        ]
    raise KeyError(name)


# ---------------------------------------------------------------------------
# JSON transport contract — single source of truth for `format="json"`.
# Pinned by Item 0.c of the council-loop-polish EX: literal-Z timestamps,
# explicit UUID + Section enum rendering, decoded JSONB metadata.
# ---------------------------------------------------------------------------


def _iso_default(obj: Any) -> str:
    """JSON serializer for `datetime` → ISO 8601 with literal `Z` suffix;
    `UUID` → `str`.

    psycopg2 returns timezone-aware datetimes whose `.isoformat()` emits
    `+00:00`, not the literal `Z` consumers parse against. Force UTC +
    literal Z. psycopg2 also returns `uuid.UUID` for UUID columns;
    `json.dumps` would crash without explicit handling — `entry_id` is in
    every payload shape.
    """
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _entry_to_json_dict(entry: "Entry") -> dict:
    """Convert a `telos_db.Entry` to a JSON-native dict for MCP transport.

    Explicitly converts UUIDs and `Section` enums; leaves datetimes for
    `_iso_default` to handle at `json.dumps` time. Used by both
    `telos_get_entry` and `telos_get_section` to guarantee an identical
    payload shape across the JSON contract.
    """
    return {
        "ref_code": entry.ref_code,
        "entry_id": str(entry.entry_id) if entry.entry_id else None,
        "section": entry.section.value,
        "status": entry.status,
        "content": entry.content,
        "metadata": entry.metadata or {},
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def _err_text(msg: str) -> mcp_types.TextContent:
    return mcp_types.TextContent(type="text", text=f"**Error:** {msg}")


def _render_full() -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.markdown_io import render_telos_markdown

    entries = telos_db.list_all()
    if not entries:
        md = "_No Telos entries yet._"
    else:
        md = render_telos_markdown(entries)
    return mcp_types.TextContent(type="text", text=md)


def _render_section(
    section: str,
    include_inactive: bool,
    metadata_filter: dict[str, Any] | None,
    fmt: str,
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import SECTION_HEADERS, Section

    if fmt not in _VALID_FORMATS:
        return _err_text(f"unknown format `{fmt}`. Valid: {', '.join(_VALID_FORMATS)}")

    try:
        sec = Section(section.lower())
    except ValueError:
        valid = ", ".join(s.value for s in Section)
        return _err_text(f"unknown section `{section}`. Valid: {valid}")

    order = "created_at_desc" if sec == Section.JOURNAL else "sort_order_asc"
    list_kwargs: dict[str, Any] = {"order_by": order}
    if include_inactive:
        list_kwargs["status_in"] = None
    if metadata_filter:
        list_kwargs["metadata_filter"] = metadata_filter

    entries = telos_db.list_section(sec, **list_kwargs)

    if fmt == _FORMAT_JSON:
        payload = {"entries": [_entry_to_json_dict(e) for e in entries]}
        return mcp_types.TextContent(
            type="text", text=json.dumps(payload, default=_iso_default)
        )

    header = SECTION_HEADERS.get(sec, sec.value.title())
    if not entries:
        return mcp_types.TextContent(type="text", text=f"## {header}\n\n_No entries._")

    lines = [f"## {header}", ""]
    for e in entries:
        ref = f"**{e.ref_code}** — " if e.ref_code else ""
        status_tag = f" _({e.status})_" if e.status != "active" else ""
        lines.append(f"- {ref}{e.content}{status_tag}")
        if e.metadata:
            meta_bits = [
                f"{k}: {v}"
                for k, v in e.metadata.items()
                if v not in (None, "", [], {})
            ]
            if meta_bits:
                lines.append(f"  - {' · '.join(meta_bits)}")
    return mcp_types.TextContent(type="text", text="\n".join(lines))


def _render_entry(section: str, ref_code: str, fmt: str) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    if fmt not in _VALID_FORMATS:
        return _err_text(f"unknown format `{fmt}`. Valid: {', '.join(_VALID_FORMATS)}")

    try:
        sec = Section(section.lower())
    except ValueError:
        return _err_text(f"unknown section `{section}`")

    entry = telos_db.get_entry(sec, ref_code)
    if not entry:
        return mcp_types.TextContent(
            type="text",
            text=f"**Not found:** no entry `{ref_code}` in section `{sec.value}`",
        )

    if fmt == _FORMAT_JSON:
        payload = {"entry": _entry_to_json_dict(entry)}
        return mcp_types.TextContent(
            type="text", text=json.dumps(payload, default=_iso_default)
        )

    lines = [
        f"### {sec.value}: {entry.ref_code or '(no ref)'}",
        f"**Status:** {entry.status}",
        "",
        entry.content,
    ]
    if entry.metadata:
        lines.append("")
        lines.append("**Metadata:**")
        for k, v in entry.metadata.items():
            lines.append(f"- {k}: {v}")
    return mcp_types.TextContent(type="text", text="\n".join(lines))


def _render_journal_search(query: str, limit: int) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db

    rows = telos_db.search_journal(query, limit=limit)
    if not rows:
        return mcp_types.TextContent(
            type="text", text=f"_No journal matches for `{query}`._"
        )

    lines = [f"## Journal matches for `{query}` ({len(rows)})", ""]
    for e in rows:
        date = e.created_at.strftime("%Y-%m-%d") if e.created_at else ""
        lines.append(f"- **{date}** — {e.content}")
        refs = (e.metadata or {}).get("related_refs")
        if refs:
            lines.append(f"  - related: {', '.join(refs)}")
    return mcp_types.TextContent(type="text", text="\n".join(lines))
