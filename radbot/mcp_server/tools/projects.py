"""Project registry MCP tools — backed by Telos.

Projects are the entries in `telos_entries` with `section='projects'`.
Each project gets its `path_patterns` (list of cwd substrings) and
optional `wiki_path` stored in its `metadata` JSONB — both are consumed
by the Claude Code `SessionStart` hook to auto-load context when a user
`cd`s into a matching repo.

Tools in this module never *create* telos projects — that goes through
the confirm-required `telos_add_project` agent tool. These only read
projects and attach MCP-bridge metadata to existing ones.

PR-1 previously backed these tools against the unrelated `projects`
table in `tools/todo/db/schema.py` (todo-list projects, not telos
identity projects). That layer became dead after this PR.
"""

from __future__ import annotations

from typing import Any

from mcp import types as mcp_types


def tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="project_match",
            description=(
                "Return the ref_code of the Telos project whose "
                "`metadata.path_patterns` matches the given cwd (any "
                "pattern must appear as a substring of cwd). Returns empty "
                "if no match. Used by Claude Code's SessionStart hook."
            ),
            inputSchema={
                "type": "object",
                "properties": {"cwd": {"type": "string"}},
                "required": ["cwd"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="project_list",
            description=(
                "Return a markdown table of all active Telos projects — "
                "ref_code, name, path_patterns, wiki_path."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="project_set_path_patterns",
            description=(
                "Attach MCP-bridge metadata to an existing Telos project "
                "(`metadata.path_patterns` + optional `metadata.wiki_path`). "
                "Does not create new projects — use the confirm-required "
                "`telos_add_project` agent tool for that. The ref_code "
                "argument is the project's Telos ref (e.g. `P1`)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "path_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "wiki_path": {
                        "type": "string",
                        "description": "Optional — relative path under wiki root.",
                    },
                },
                "required": ["ref_code", "path_patterns"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="project_get_context",
            description=(
                "Return markdown for a Telos project — its current content "
                "plus recent journal entries whose `metadata.related_refs` "
                "contain this project's ref_code. Accepts either a ref_code "
                "(`P1`) or the project name (matched against Telos entry "
                "content). PR-2 will replace this with the full hierarchy "
                "render (milestones / explorations / project_tasks)."
            ),
            inputSchema={
                "type": "object",
                "properties": {"ref_or_name": {"type": "string"}},
                "required": ["ref_or_name"],
                "additionalProperties": False,
            },
        ),
    ]


async def call(
    name: str, arguments: dict[str, Any]
) -> list[mcp_types.TextContent]:
    if name == "project_match":
        return [_do_match(arguments["cwd"])]
    if name == "project_list":
        return [_do_list()]
    if name == "project_set_path_patterns":
        return [_do_set_path_patterns(
            arguments["ref_code"],
            list(arguments.get("path_patterns") or []),
            arguments.get("wiki_path"),
        )]
    if name == "project_get_context":
        return [_do_get_context(arguments["ref_or_name"])]
    raise KeyError(name)


# ---------------------------------------------------------------------------
# Helpers (lazy imports inside to keep module-import cost minimal)
# ---------------------------------------------------------------------------


def _err(msg: str) -> mcp_types.TextContent:
    return mcp_types.TextContent(type="text", text=f"**Error:** {msg}")


def _active_projects():
    """Yield active Telos projects with parsed metadata."""
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    return telos_db.list_section(Section.PROJECTS, status="active")


def _do_match(cwd: str) -> mcp_types.TextContent:
    """Return the ref_code of the project whose path_patterns matches cwd."""
    # Longest-pattern-first so more specific patterns win on overlap
    best: tuple[int, str] | None = None
    for project in _active_projects():
        patterns = (project.metadata or {}).get("path_patterns") or []
        for pattern in patterns:
            if not isinstance(pattern, str) or not pattern:
                continue
            if pattern in cwd:
                score = len(pattern)
                if best is None or score > best[0]:
                    best = (score, project.ref_code or "")
    if best is None or not best[1]:
        return mcp_types.TextContent(type="text", text="")
    return mcp_types.TextContent(type="text", text=best[1])


def _do_list() -> mcp_types.TextContent:
    projects = list(_active_projects())
    if not projects:
        return mcp_types.TextContent(
            type="text", text="_No active Telos projects._"
        )
    lines = [
        "## Telos projects (active)",
        "",
        "| ref | Name | Path patterns | Wiki page |",
        "|---|---|---|---|",
    ]
    for p in projects:
        meta = p.metadata or {}
        patterns = meta.get("path_patterns") or []
        wiki_path = meta.get("wiki_path")
        patterns_str = ", ".join(f"`{pat}`" for pat in patterns) or "—"
        wiki_str = f"`{wiki_path}`" if wiki_path else "—"
        name = (p.content or "").splitlines()[0][:80]
        lines.append(
            f"| `{p.ref_code or '?'}` | {name} | {patterns_str} | {wiki_str} |"
        )
    return mcp_types.TextContent(type="text", text="\n".join(lines))


def _do_set_path_patterns(
    ref_code: str, path_patterns: list[str], wiki_path: str | None
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    clean_patterns = [p.strip() for p in path_patterns if p and p.strip()]
    metadata_merge: dict[str, Any] = {"path_patterns": clean_patterns}
    if wiki_path is not None:
        metadata_merge["wiki_path"] = wiki_path.strip() or None

    entry = telos_db.update_entry(
        Section.PROJECTS, ref_code, metadata_merge=metadata_merge
    )
    if entry is None:
        return _err(
            f"No Telos project with ref_code `{ref_code}` — create it via "
            "`telos_add_project` first."
        )
    name = (entry.content or "").splitlines()[0][:80]
    bits = [f"patterns={clean_patterns}"]
    if wiki_path is not None:
        bits.append(f"wiki_path={wiki_path!r}")
    return mcp_types.TextContent(
        type="text",
        text=f"Set MCP bridge metadata on `{ref_code}` ({name}) — {' · '.join(bits)}",
    )


def _find_project(ref_or_name: str):
    """Locate a project by ref_code (exact) or by name (case-insensitive).

    Name match order: exact first-line match → case-insensitive first-line
    match → substring match against the first line. This is lenient enough
    that "radbot" matches a project whose content is
    "radbot https://github.com/perrymanuk/radbot".
    """
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    needle = ref_or_name.strip()
    direct = telos_db.get_entry(Section.PROJECTS, needle)
    if direct is not None:
        return direct

    needle_low = needle.lower()
    projects = list(_active_projects())

    def _first_line(e) -> str:
        return (e.content or "").splitlines()[0].strip()

    for p in projects:
        if _first_line(p) == needle:
            return p
    for p in projects:
        if _first_line(p).lower() == needle_low:
            return p
    for p in projects:
        if needle_low in _first_line(p).lower():
            return p
    return None


def _do_get_context(ref_or_name: str) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    project = _find_project(ref_or_name)
    if project is None:
        return _err(f"Unknown project: `{ref_or_name}`")

    meta = project.metadata or {}
    name = (project.content or "").splitlines()[0][:80] or project.ref_code or "?"
    lines = [f"# Project: {name} ({project.ref_code})", ""]

    if project.content and "\n" in (project.content or ""):
        lines.append(project.content.strip())
        lines.append("")

    if meta.get("wiki_path"):
        lines.append(f"**Wiki page:** `{meta['wiki_path']}`")
        lines.append("")

    # Journal entries tagged with this project's ref_code
    journal_entries = telos_db.list_section(
        Section.JOURNAL, status=None, limit=50, order_by="created_at_desc"
    )
    related = [
        e for e in journal_entries
        if project.ref_code
        and project.ref_code in (e.metadata or {}).get("related_refs", [])
    ][:10]
    if related:
        lines.append("## Recent activity")
        lines.append("")
        for e in related:
            date = e.created_at.strftime("%Y-%m-%d") if e.created_at else ""
            content = (e.content or "").splitlines()[0][:200]
            lines.append(f"- **{date}** — {content}")

    if len(lines) <= 2:
        lines.append("_No recent activity recorded for this project._")

    return mcp_types.TextContent(type="text", text="\n".join(lines).rstrip())
