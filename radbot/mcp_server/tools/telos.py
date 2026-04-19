"""Telos MCP tools — expose radbot's user-context store to external clients.

All tools return markdown `TextContent`. Heavy imports are lazy to keep
module-import cost minimal.
"""

from __future__ import annotations

from typing import Any

from mcp import types as mcp_types


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
                "Return all entries in one Telos section as markdown. "
                "Sections: identity, history, problems, mission, narratives, "
                "goals, challenges, strategies, projects, wisdom, ideas, "
                "predictions, wrong_about, best_books, best_movies, best_music, "
                "taste, traumas, metrics, journal."
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
                        "description": "Include completed/archived entries. Default false.",
                        "default": False,
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
                "ref_code is 'ME'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "ref_code": {"type": "string"},
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
            )
        ]
    if name == "telos_get_entry":
        return [_render_entry(arguments["section"], arguments["ref_code"])]
    if name == "telos_search_journal":
        return [
            _render_journal_search(
                arguments["query"],
                int(arguments.get("limit", 20)),
            )
        ]
    raise KeyError(name)


def _render_full() -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.markdown_io import render_telos_markdown

    entries = telos_db.list_all()
    if not entries:
        md = "_No Telos entries yet._"
    else:
        md = render_telos_markdown(entries)
    return mcp_types.TextContent(type="text", text=md)


def _render_section(section: str, include_inactive: bool) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section, SECTION_HEADERS

    try:
        sec = Section(section.lower())
    except ValueError:
        valid = ", ".join(s.value for s in Section)
        return mcp_types.TextContent(
            type="text",
            text=f"**Error:** unknown section `{section}`. Valid: {valid}",
        )

    status_filter = None if include_inactive else "active"
    order = "created_at_desc" if sec == Section.JOURNAL else "sort_order_asc"
    entries = telos_db.list_section(sec, status=status_filter, order_by=order)

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


def _render_entry(section: str, ref_code: str) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    try:
        sec = Section(section.lower())
    except ValueError:
        return mcp_types.TextContent(
            type="text", text=f"**Error:** unknown section `{section}`"
        )

    entry = telos_db.get_entry(sec, ref_code)
    if not entry:
        return mcp_types.TextContent(
            type="text",
            text=f"**Not found:** no entry `{ref_code}` in section `{sec.value}`",
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
