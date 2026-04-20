"""Tool registry for the radbot MCP server.

Each submodule (`telos`, `wiki`, `projects`, `tasks`, `memory`) exposes:

- `tools() -> list[mcp.types.Tool]` — tool definitions for ListTools
- `async call(name: str, arguments: dict) -> list[TextContent]` — dispatcher
  for tools owned by that module

Modules that are empty stubs contribute zero tools until their tools are
implemented (post-scaffold phase of PR 1).
"""

from __future__ import annotations

from typing import Any

from mcp import types as mcp_types

from . import memory, project_tasks, projects, tasks, telos, wiki

_MODULES = [telos, wiki, projects, project_tasks, tasks, memory]


def all_tools() -> list[mcp_types.Tool]:
    out: list[mcp_types.Tool] = []
    for module in _MODULES:
        out.extend(module.tools())
    return out


async def dispatch(name: str, arguments: dict[str, Any]) -> list[mcp_types.TextContent]:
    for module in _MODULES:
        for tool in module.tools():
            if tool.name == name:
                return await module.call(name, arguments)
    raise KeyError(name)
