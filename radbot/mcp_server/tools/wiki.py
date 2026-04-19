"""Wiki filesystem MCP tools.

Rooted at `$RADBOT_WIKI_PATH` (default `/mnt/ai-intel` in the Nomad
container). Strict path sanitization: the resolved absolute path must stay
under the configured root and must not traverse a symlink. No writes outside
the root, no deletes.

Return format: markdown.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp import types as mcp_types

logger = logging.getLogger(__name__)

_DEFAULT_ROOT = "/mnt/ai-intel"
_MAX_READ_BYTES = 1_000_000  # 1 MB cap — markdown files only
_MAX_WRITE_BYTES = 1_000_000
_MAX_LIST_ENTRIES = 500


def _wiki_root() -> str | None:
    """Resolved absolute wiki root, or None if unconfigured / missing."""
    root = os.environ.get("RADBOT_WIKI_PATH", _DEFAULT_ROOT).strip()
    if not root:
        return None
    abs_root = os.path.realpath(os.path.expanduser(root))
    if not os.path.isdir(abs_root):
        return None
    return abs_root


def _resolve_under_root(rel_path: str) -> tuple[str, str] | tuple[None, str]:
    """Resolve `rel_path` under the wiki root.

    Returns (absolute_path, "") on success, or (None, error_message) on failure.
    Rejects absolute paths, `..` traversal, and symlinks leading outside root.
    """
    root = _wiki_root()
    if root is None:
        return (
            None,
            "Wiki not configured: RADBOT_WIKI_PATH unset or directory missing.",
        )

    # Reject absolute paths outright — all access is relative to the wiki root
    if rel_path.startswith("/"):
        return (None, f"Absolute paths not allowed: `{rel_path}`")
    # Collapse `..`, then re-check
    candidate = os.path.normpath(os.path.join(root, rel_path))
    abs_candidate = os.path.realpath(candidate)
    if not abs_candidate.startswith(root + os.sep) and abs_candidate != root:
        return (None, f"Path escapes wiki root: `{rel_path}`")
    return (abs_candidate, "")


def tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="wiki_read",
            description=(
                "Read a markdown file from the ai-intel wiki. Path is relative "
                "to the wiki root (e.g. `wiki/concepts/claude-code.md`)."
            ),
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="wiki_list",
            description=(
                "List files in the ai-intel wiki. Optional glob pattern "
                "(e.g. `wiki/concepts/*.md`, `**/*.md`). Returns grouped "
                "markdown index, capped at 500 entries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "glob": {
                        "type": "string",
                        "description": "Glob pattern relative to wiki root. Default `**/*.md`.",
                        "default": "**/*.md",
                    }
                },
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="wiki_search",
            description=(
                "Case-insensitive substring search across wiki markdown files. "
                "Returns one bullet per match with path and surrounding line."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "glob": {
                        "type": "string",
                        "description": "Restrict search to files matching this glob. Default `**/*.md`.",
                        "default": "**/*.md",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 500,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        mcp_types.Tool(
            name="wiki_write",
            description=(
                "Write (create or overwrite) a markdown file in the ai-intel "
                "wiki. Parent directories are created if missing. Path is "
                "sanitized to stay under the wiki root."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        ),
    ]


async def call(
    name: str, arguments: dict[str, Any]
) -> list[mcp_types.TextContent]:
    if name == "wiki_read":
        return [_do_read(arguments["path"])]
    if name == "wiki_list":
        return [_do_list(arguments.get("glob", "**/*.md"))]
    if name == "wiki_search":
        return [_do_search(
            arguments["query"],
            arguments.get("glob", "**/*.md"),
            int(arguments.get("limit", 50)),
        )]
    if name == "wiki_write":
        return [_do_write(arguments["path"], arguments["content"])]
    raise KeyError(name)


def _err(msg: str) -> mcp_types.TextContent:
    return mcp_types.TextContent(type="text", text=f"**Error:** {msg}")


def _do_read(rel_path: str) -> mcp_types.TextContent:
    abs_path, err = _resolve_under_root(rel_path)
    if abs_path is None:
        return _err(err)
    if not os.path.isfile(abs_path):
        return _err(f"Not a file: `{rel_path}`")
    try:
        size = os.path.getsize(abs_path)
        if size > _MAX_READ_BYTES:
            return _err(f"File too large ({size} bytes > {_MAX_READ_BYTES})")
        with open(abs_path, "r", encoding="utf-8") as f:
            return mcp_types.TextContent(type="text", text=f.read())
    except OSError as e:
        return _err(f"Read failed: {e}")


def _do_list(glob: str) -> mcp_types.TextContent:
    import pathlib

    root = _wiki_root()
    if root is None:
        return _err("Wiki not configured.")

    root_path = pathlib.Path(root)
    try:
        matches = [p for p in root_path.glob(glob) if p.is_file()][:_MAX_LIST_ENTRIES]
    except (OSError, ValueError) as e:
        return _err(f"Bad glob `{glob}`: {e}")

    if not matches:
        return mcp_types.TextContent(
            type="text", text=f"_No files matching `{glob}`._"
        )

    # Group by parent directory for readability
    by_dir: dict[str, list[str]] = {}
    for p in matches:
        rel = p.relative_to(root_path)
        parent = str(rel.parent) if rel.parent != pathlib.Path(".") else "(root)"
        by_dir.setdefault(parent, []).append(rel.name)

    lines = [f"## Wiki files matching `{glob}` ({len(matches)})", ""]
    for parent in sorted(by_dir):
        lines.append(f"### {parent}")
        for name in sorted(by_dir[parent]):
            full = name if parent == "(root)" else f"{parent}/{name}"
            lines.append(f"- `{full}`")
        lines.append("")
    return mcp_types.TextContent(type="text", text="\n".join(lines).rstrip())


def _do_search(query: str, glob: str, limit: int) -> mcp_types.TextContent:
    import pathlib

    root = _wiki_root()
    if root is None:
        return _err("Wiki not configured.")

    root_path = pathlib.Path(root)
    q_lower = query.lower()
    hits: list[tuple[str, int, str]] = []  # (rel_path, line_no, line)
    try:
        for path in root_path.glob(glob):
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, start=1):
                        if q_lower in line.lower():
                            rel = str(path.relative_to(root_path))
                            hits.append((rel, i, line.rstrip()))
                            if len(hits) >= limit:
                                break
            except OSError:
                continue
            if len(hits) >= limit:
                break
    except ValueError as e:
        return _err(f"Bad glob `{glob}`: {e}")

    if not hits:
        return mcp_types.TextContent(
            type="text", text=f"_No matches for `{query}`._"
        )

    lines = [f"## Wiki search for `{query}` ({len(hits)} hits)", ""]
    for rel, line_no, line in hits:
        lines.append(f"- `{rel}:{line_no}` — {line.strip()}")
    return mcp_types.TextContent(type="text", text="\n".join(lines))


def _do_write(rel_path: str, content: str) -> mcp_types.TextContent:
    if len(content.encode("utf-8")) > _MAX_WRITE_BYTES:
        return _err(f"Content too large (> {_MAX_WRITE_BYTES} bytes)")

    abs_path, err = _resolve_under_root(rel_path)
    if abs_path is None:
        return _err(err)

    # Ensure parent dir exists (and also stays under root)
    parent = os.path.dirname(abs_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # Atomic write via temp + rename
    tmp_path = abs_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, abs_path)
    except OSError as e:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return _err(f"Write failed: {e}")

    size = len(content.encode("utf-8"))
    logger.info("wiki_write path=%s bytes=%d", rel_path, size)
    return mcp_types.TextContent(
        type="text", text=f"Wrote {size} bytes to `{rel_path}`"
    )
