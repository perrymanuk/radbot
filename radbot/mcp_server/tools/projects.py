"""Project registry MCP tools.

Projects are radbot's existing `projects` table rows extended with two
columns added in PR 1: `wiki_path` (markdown file under the wiki root)
and `path_patterns` (TEXT[] of cwd substrings that identify this project).

`project_match(cwd)` is the key tool: the Claude Code SessionStart hook
calls it to decide whether to inject project context.
"""

from __future__ import annotations

from typing import Any

from mcp import types as mcp_types


def tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="project_match",
            description=(
                "Return the name of the project whose `path_patterns` match "
                "the given cwd (any element of path_patterns must appear as a "
                "substring of cwd). Returns empty if no match."
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
            description="Return a markdown table of all registered projects.",
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="project_register",
            description=(
                "Create or update a project entry. `name` is the canonical "
                "identifier. `path_patterns` is a list of cwd substrings "
                "(e.g. ['/git/perrymanuk/radbot']). `wiki_path` is optional, "
                "relative to the wiki root."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "path_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "wiki_path": {"type": "string"},
                },
                "required": ["name", "path_patterns"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="project_get_context",
            description=(
                "Return the project's context as markdown. Phase 1: reads the "
                "registered `wiki_path` file. Phase 2 (PR 2): will render the "
                "live Telos project hierarchy (milestones, tasks, explorations)."
            ),
            inputSchema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
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
    if name == "project_register":
        return [_do_register(
            arguments["name"],
            list(arguments.get("path_patterns") or []),
            arguments.get("wiki_path"),
        )]
    if name == "project_get_context":
        return [_do_get_context(arguments["name"])]
    raise KeyError(name)


def _err(msg: str) -> mcp_types.TextContent:
    return mcp_types.TextContent(type="text", text=f"**Error:** {msg}")


def _do_match(cwd: str) -> mcp_types.TextContent:
    from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

    with get_db_connection() as conn, get_db_cursor(conn) as c:
        c.execute(
            "SELECT name FROM projects "
            "WHERE EXISTS (SELECT 1 FROM unnest(path_patterns) p WHERE %s LIKE '%%' || p || '%%') "
            "ORDER BY length(name) DESC LIMIT 1",
            (cwd,),
        )
        row = c.fetchone()

    if not row:
        return mcp_types.TextContent(type="text", text="")
    return mcp_types.TextContent(type="text", text=row[0])


def _do_list() -> mcp_types.TextContent:
    from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

    with get_db_connection() as conn, get_db_cursor(conn) as c:
        c.execute(
            "SELECT name, path_patterns, wiki_path FROM projects ORDER BY name"
        )
        rows = c.fetchall()

    if not rows:
        return mcp_types.TextContent(
            type="text", text="_No projects registered._"
        )

    lines = [
        "## Registered projects",
        "",
        "| Name | Path patterns | Wiki page |",
        "|---|---|---|",
    ]
    for name, patterns, wiki_path in rows:
        patterns_str = ", ".join(f"`{p}`" for p in (patterns or [])) or "—"
        wiki_str = f"`{wiki_path}`" if wiki_path else "—"
        lines.append(f"| `{name}` | {patterns_str} | {wiki_str} |")
    return mcp_types.TextContent(type="text", text="\n".join(lines))


def _do_register(
    name: str, path_patterns: list[str], wiki_path: str | None
) -> mcp_types.TextContent:
    from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

    clean_patterns = [p.strip() for p in path_patterns if p and p.strip()]
    if not clean_patterns:
        return _err("At least one non-empty path_pattern is required.")

    with get_db_connection() as conn, get_db_cursor(conn, commit=True) as c:
        c.execute(
            """
            INSERT INTO projects (name, path_patterns, wiki_path)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE
              SET path_patterns = EXCLUDED.path_patterns,
                  wiki_path = EXCLUDED.wiki_path
            RETURNING (xmax = 0) AS inserted
            """,
            (name, clean_patterns, wiki_path),
        )
        inserted = c.fetchone()[0]

    verb = "Registered" if inserted else "Updated"
    wiki_note = f" · wiki_path=`{wiki_path}`" if wiki_path else ""
    return mcp_types.TextContent(
        type="text",
        text=f"{verb} project `{name}` · patterns={clean_patterns}{wiki_note}",
    )


def _do_get_context(name: str) -> mcp_types.TextContent:
    from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

    # Import here to reuse the same root + sanitization logic
    from .wiki import _resolve_under_root, _wiki_root

    with get_db_connection() as conn, get_db_cursor(conn) as c:
        c.execute("SELECT wiki_path FROM projects WHERE name = %s", (name,))
        row = c.fetchone()

    if not row:
        return _err(f"Unknown project: `{name}`")
    wiki_path = row[0]
    if not wiki_path:
        return mcp_types.TextContent(
            type="text",
            text=(
                f"## Project: {name}\n\n"
                "_No wiki page registered for this project. "
                "Set `wiki_path` via `project_register` to surface context here._"
            ),
        )

    if _wiki_root() is None:
        return _err("Wiki not configured: RADBOT_WIKI_PATH unset or missing.")

    abs_path, err = _resolve_under_root(wiki_path)
    if abs_path is None:
        return _err(err)

    import os as _os
    if not _os.path.isfile(abs_path):
        return _err(
            f"Project `{name}` references missing wiki file: `{wiki_path}`"
        )

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            return mcp_types.TextContent(type="text", text=f.read())
    except OSError as e:
        return _err(f"Failed to read wiki page: {e}")
