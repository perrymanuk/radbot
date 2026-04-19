"""FunctionTool wrappers for the ai-intel wiki (read-only)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from google.adk.tools import FunctionTool

from radbot.mcp_server.tools.wiki import _do_list, _do_read, _do_search
from radbot.tools.shared.sanitize import sanitize_external_content

logger = logging.getLogger(__name__)


def _unwrap(content: Any) -> str:
    """Pull plain text out of an mcp TextContent (or anything with .text)."""
    return getattr(content, "text", str(content))


def wiki_read(path: str) -> Dict[str, Any]:
    """Read a markdown file from the ai-intel wiki.

    Args:
        path: Wiki-relative path (e.g. ``wiki/concepts/claude-code.md``).

    Returns:
        ``{"status": "success", "path": path, "content": "<markdown>"}`` on success;
        ``{"status": "error", "message": "..."}`` when the path is missing / invalid.
    """
    raw = _unwrap(_do_read(path))
    if raw.startswith("**Error:**"):
        return {"status": "error", "message": raw}
    safe = sanitize_external_content(raw, source="wiki_read", strictness="strict")
    return {"status": "success", "path": path, "content": safe}


def wiki_list(glob: str = "**/*.md") -> Dict[str, Any]:
    """List wiki files matching a glob pattern.

    Args:
        glob: Glob relative to the wiki root. Default ``**/*.md``. Capped at 500 entries.
    """
    raw = _unwrap(_do_list(glob))
    if raw.startswith("**Error:**"):
        return {"status": "error", "message": raw}
    safe = sanitize_external_content(raw, source="wiki_list", strictness="strict")
    return {"status": "success", "glob": glob, "listing": safe}


def wiki_search(query: str, glob: str = "**/*.md", limit: int = 50) -> Dict[str, Any]:
    """Case-insensitive substring search across wiki markdown files.

    Args:
        query: Substring to search for.
        glob: Restrict search to files matching this glob. Default ``**/*.md``.
        limit: Max hits. 1–500, default 50.
    """
    limit = max(1, min(int(limit), 500))
    raw = _unwrap(_do_search(query, glob, limit))
    if raw.startswith("**Error:**"):
        return {"status": "error", "message": raw}
    safe = sanitize_external_content(raw, source="wiki_search", strictness="strict")
    return {"status": "success", "query": query, "results": safe}


wiki_read_tool = FunctionTool(wiki_read)
wiki_list_tool = FunctionTool(wiki_list)
wiki_search_tool = FunctionTool(wiki_search)

WIKI_TOOLS = [wiki_list_tool, wiki_search_tool, wiki_read_tool]
