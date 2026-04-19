"""MCP Server factory and tool dispatch.

Creates a `mcp.server.lowlevel.Server` and wires `list_tools` / `call_tool`
handlers to the modules in `radbot.mcp_server.tools`.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp import types as mcp_types
from mcp.server.lowlevel import Server

from . import tools as tool_registry

logger = logging.getLogger(__name__)

SERVER_NAME = "radbot-mcp"
SERVER_VERSION = "0.1.0"


def create_server() -> Server:
    """Build and return an MCP Server with all radbot tools registered."""
    server: Server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:  # noqa: D401
        return tool_registry.all_tools()

    @server.call_tool()
    async def _call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> list[mcp_types.TextContent]:
        args = arguments or {}
        logger.info("mcp_call_tool name=%s", name)
        try:
            return await tool_registry.dispatch(name, args)
        except KeyError:
            return [
                mcp_types.TextContent(
                    type="text",
                    text=f"Unknown tool: `{name}`. "
                    "Call `ListTools` to see available tools.",
                )
            ]
        except Exception as exc:  # surfaced to the model as a tool result
            logger.exception("mcp_call_tool failed name=%s", name)
            return [
                mcp_types.TextContent(
                    type="text",
                    text=f"Tool `{name}` failed: {exc}",
                )
            ]

    return server
