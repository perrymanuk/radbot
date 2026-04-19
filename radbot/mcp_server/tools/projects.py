"""Project registry MCP tools — backed by Telos.

Projects are the entries in `telos_entries` with `section='projects'`.
Each project gets its `path_patterns` (list of cwd substrings) and
optional `wiki_path` stored in its `metadata` JSONB — both are consumed
by the Claude Code `SessionStart` hook to auto-load context when a user
`cd`s into a matching repo.

Read tools (`project_list`, `project_get_context`, `project_match`) and
the metadata setter (`project_set_path_patterns`) are always safe.

Mutation tools (`project_create`, `project_update`, `project_archive`,
`project_merge`, `project_list_children`) are a parallel surface to
beto's confirm-required `telos_*` tools. They call the same
`radbot.tools.telos.db` primitives directly; user confirmation is
expected at the MCP client UI (e.g. Claude Code's per-tool approval)
rather than enforced here. Never hard-deletes — archive only.
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
        mcp_types.Tool(
            name="project_create",
            description=(
                "Create a new Telos project. Auto-assigns a `PRJ<N>` "
                "ref_code. Optional metadata: `priority`, `parent_goal` "
                "(Goal ref_code like `G1`), `path_patterns` (list of cwd "
                "substrings for the SessionStart hook), and `wiki_path`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Project name / title (first line of content).",
                    },
                    "priority": {"type": "string"},
                    "parent_goal": {
                        "type": "string",
                        "description": "Optional Goal ref_code (e.g. `G1`).",
                    },
                    "path_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "wiki_path": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="project_update",
            description=(
                "Update an existing Telos project. `name` replaces "
                "`content`; other fields shallow-merge into metadata. "
                "`path_patterns` fully replaces the existing list (not "
                "appended). Pass `status` to reactivate an archived "
                "project. To remove a metadata key set it to empty string "
                "or `null`."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "name": {"type": "string"},
                    "priority": {"type": "string"},
                    "parent_goal": {"type": "string"},
                    "path_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "wiki_path": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["active", "completed", "archived", "superseded"],
                    },
                },
                "required": ["ref_code"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="project_archive",
            description=(
                "Archive (soft-delete) a Telos project. Stamps "
                "`metadata.archived_reason` if provided. With "
                "`cascade_children=true`, also archives every active "
                "milestone / project_task / exploration whose "
                "`metadata.parent_project` matches. Without cascade, active "
                "children are left alone and listed in the response."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "ref_code": {"type": "string"},
                    "reason": {"type": "string"},
                    "cascade_children": {"type": "boolean", "default": False},
                },
                "required": ["ref_code"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="project_merge",
            description=(
                "Merge one Telos project into another. Rebinds every "
                "active child (milestones, project_tasks, explorations) so "
                "their `metadata.parent_project` points at `into_ref`, "
                "then archives `from_ref` with an optional reason. "
                "Both refs must exist and differ."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "from_ref": {"type": "string"},
                    "into_ref": {"type": "string"},
                    "archive_reason": {"type": "string"},
                },
                "required": ["from_ref", "into_ref"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="project_list_children",
            description=(
                "Return a markdown rollup of active milestones, "
                "project_tasks, and explorations whose "
                "`metadata.parent_project` matches the given project "
                "ref_code. Useful to preview what `project_archive "
                "--cascade` or `project_merge` would touch."
            ),
            inputSchema={
                "type": "object",
                "properties": {"ref_code": {"type": "string"}},
                "required": ["ref_code"],
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
    if name == "project_create":
        return [_do_create(
            arguments["name"],
            arguments.get("priority"),
            arguments.get("parent_goal"),
            arguments.get("path_patterns"),
            arguments.get("wiki_path"),
        )]
    if name == "project_update":
        return [_do_update(arguments)]
    if name == "project_archive":
        return [_do_archive(
            arguments["ref_code"],
            arguments.get("reason"),
            bool(arguments.get("cascade_children", False)),
        )]
    if name == "project_merge":
        return [_do_merge(
            arguments["from_ref"],
            arguments["into_ref"],
            arguments.get("archive_reason"),
        )]
    if name == "project_list_children":
        return [_do_list_children(arguments["ref_code"])]
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


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


_CHILD_SECTIONS = ("MILESTONES", "PROJECT_TASKS", "EXPLORATIONS")


def _clean_patterns(patterns: list[str] | None) -> list[str] | None:
    if patterns is None:
        return None
    return [p.strip() for p in patterns if p and p.strip()]


def _project_meta_from(
    priority: str | None,
    parent_goal: str | None,
    path_patterns: list[str] | None,
    wiki_path: str | None,
) -> dict[str, Any]:
    """Build a project metadata dict. Empty-string / None values are
    interpreted as "remove this key" (stored as JSON null so the shallow
    JSONB merge clears them)."""
    meta: dict[str, Any] = {}
    if priority is not None:
        meta["priority"] = priority.strip() or None
    if parent_goal is not None:
        meta["parent_goal"] = parent_goal.strip() or None
    if path_patterns is not None:
        meta["path_patterns"] = _clean_patterns(path_patterns) or []
    if wiki_path is not None:
        meta["wiki_path"] = wiki_path.strip() or None
    return meta


def _active_children(ref_code: str) -> dict[str, list]:
    """Return active children of a project keyed by section name."""
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    out: dict[str, list] = {}
    for sec_name in _CHILD_SECTIONS:
        sec = getattr(Section, sec_name)
        rows = telos_db.list_section(sec, status="active")
        out[sec_name] = [
            r for r in rows
            if (r.metadata or {}).get("parent_project") == ref_code
        ]
    return out


def _do_create(
    name: str,
    priority: str | None,
    parent_goal: str | None,
    path_patterns: list[str] | None,
    wiki_path: str | None,
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    clean_name = (name or "").strip()
    if not clean_name:
        return _err("`name` is required and must not be whitespace.")

    raw = _project_meta_from(priority, parent_goal, path_patterns, wiki_path)
    metadata = {k: v for k, v in raw.items() if v is not None and v != []}

    entry = telos_db.add_entry(Section.PROJECTS, clean_name, metadata=metadata)
    bits = [f"ref=`{entry.ref_code}`", f"name={clean_name!r}"]
    if metadata:
        bits.append(f"metadata={metadata}")
    return mcp_types.TextContent(
        type="text", text=f"Created project — {' · '.join(bits)}"
    )


def _do_update(arguments: dict[str, Any]) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    ref_code = arguments["ref_code"]
    new_name = arguments.get("name")
    status = arguments.get("status")

    metadata_merge = _project_meta_from(
        arguments.get("priority"),
        arguments.get("parent_goal"),
        arguments.get("path_patterns"),
        arguments.get("wiki_path"),
    )

    content: str | None = None
    if new_name is not None:
        clean_name = new_name.strip()
        if not clean_name:
            return _err("`name` must not be whitespace if provided.")
        content = clean_name

    entry = telos_db.update_entry(
        Section.PROJECTS,
        ref_code,
        content=content,
        metadata_merge=metadata_merge or None,
        status=status,
    )
    if entry is None:
        return _err(f"No Telos project with ref_code `{ref_code}`.")

    bits: list[str] = []
    if content is not None:
        bits.append(f"name={content!r}")
    if metadata_merge:
        bits.append(f"metadata_merge={metadata_merge}")
    if status is not None:
        bits.append(f"status={status}")
    if not bits:
        bits.append("no-op")
    return mcp_types.TextContent(
        type="text",
        text=f"Updated project `{ref_code}` — {' · '.join(bits)}",
    )


def _do_archive(
    ref_code: str, reason: str | None, cascade_children: bool
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    existing = telos_db.get_entry(Section.PROJECTS, ref_code)
    if existing is None:
        return _err(f"No Telos project with ref_code `{ref_code}`.")

    children = _active_children(ref_code)
    archived_counts: dict[str, int] = {}
    cascade_reason = reason or f"parent {ref_code} archived"

    if cascade_children:
        for sec_name, rows in children.items():
            sec = getattr(Section, sec_name)
            count = 0
            for row in rows:
                if telos_db.archive_entry(sec, row.ref_code, reason=cascade_reason):
                    count += 1
            archived_counts[sec_name] = count

    ok = telos_db.archive_entry(Section.PROJECTS, ref_code, reason=reason or None)
    if not ok:
        return _err(f"Failed to archive project `{ref_code}`.")

    lines = [f"Archived project `{ref_code}`."]
    if reason:
        lines.append(f"Reason: {reason}")
    if cascade_children and archived_counts:
        summary = ", ".join(
            f"{sec_name.lower()}={n}" for sec_name, n in archived_counts.items() if n
        )
        lines.append(f"Cascaded: {summary or 'none'}.")
    elif not cascade_children:
        orphan = {k: len(v) for k, v in children.items() if v}
        if orphan:
            summary = ", ".join(f"{k.lower()}={n}" for k, n in orphan.items())
            lines.append(
                f"**Warning:** left active children unbound ({summary}). "
                f"Re-run with `cascade_children=true` to archive them."
            )
    return mcp_types.TextContent(type="text", text="\n".join(lines))


def _do_merge(
    from_ref: str, into_ref: str, archive_reason: str | None
) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    if from_ref == into_ref:
        return _err("`from_ref` and `into_ref` must differ.")
    src = telos_db.get_entry(Section.PROJECTS, from_ref)
    if src is None:
        return _err(f"No Telos project with ref_code `{from_ref}`.")
    dst = telos_db.get_entry(Section.PROJECTS, into_ref)
    if dst is None:
        return _err(f"No Telos project with ref_code `{into_ref}`.")

    children = _active_children(from_ref)
    rebound: dict[str, int] = {}
    for sec_name, rows in children.items():
        sec = getattr(Section, sec_name)
        count = 0
        for row in rows:
            updated = telos_db.update_entry(
                sec, row.ref_code,
                metadata_merge={"parent_project": into_ref},
            )
            if updated is not None:
                count += 1
        rebound[sec_name] = count

    reason = archive_reason or f"merged into {into_ref}"
    telos_db.archive_entry(Section.PROJECTS, from_ref, reason=reason)

    lines = [f"Merged `{from_ref}` → `{into_ref}`."]
    summary = ", ".join(
        f"{sec_name.lower()}={n}" for sec_name, n in rebound.items() if n
    )
    lines.append(f"Rebound children: {summary or 'none'}.")
    lines.append(f"Archived `{from_ref}` (reason: {reason}).")
    return mcp_types.TextContent(type="text", text="\n".join(lines))


def _do_list_children(ref_code: str) -> mcp_types.TextContent:
    from radbot.tools.telos import db as telos_db
    from radbot.tools.telos.models import Section

    if telos_db.get_entry(Section.PROJECTS, ref_code) is None:
        return _err(f"No Telos project with ref_code `{ref_code}`.")

    children = _active_children(ref_code)
    lines = [f"# Active children of `{ref_code}`", ""]
    any_rows = False
    labels = {
        "MILESTONES": "## Milestones",
        "PROJECT_TASKS": "## Project tasks",
        "EXPLORATIONS": "## Explorations",
    }
    for sec_name, rows in children.items():
        if not rows:
            continue
        any_rows = True
        lines.append(labels[sec_name])
        lines.append("")
        for r in rows:
            first = (r.content or "").splitlines()[0][:120]
            meta = r.metadata or {}
            extra = []
            if meta.get("task_status"):
                extra.append(f"status={meta['task_status']}")
            if meta.get("parent_milestone"):
                extra.append(f"ms={meta['parent_milestone']}")
            tail = f" ({', '.join(extra)})" if extra else ""
            lines.append(f"- `{r.ref_code}` — {first}{tail}")
        lines.append("")
    if not any_rows:
        lines.append("_No active children._")
    return mcp_types.TextContent(type="text", text="\n".join(lines).rstrip())
