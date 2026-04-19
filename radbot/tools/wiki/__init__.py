"""Wiki read tools for scout.

Wraps the filesystem-rooted helpers in ``radbot.mcp_server.tools.wiki``
as FunctionTools. Read-only by design — wiki curation stays with beto
(which calls the MCP server directly).
"""

from radbot.tools.wiki.wiki_tools import (
    WIKI_TOOLS,
    wiki_list_tool,
    wiki_read_tool,
    wiki_search_tool,
)

__all__ = [
    "WIKI_TOOLS",
    "wiki_list_tool",
    "wiki_read_tool",
    "wiki_search_tool",
]
