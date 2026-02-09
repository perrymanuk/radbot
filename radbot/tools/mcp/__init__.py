"""
MCP tools package.

This package provides the functionality for interacting with Model Context Protocol servers.
"""

# Import Event from ADK 0.3.0
from google.adk.events import Event

# Use the new adapter instead of the original MCP fileserver client
from radbot.tools.mcp.filesystem_adapter import create_fileserver_toolset
from radbot.tools.mcp.mcp_fileserver_server import FileServerMCP
from radbot.tools.mcp.mcp_tools import get_available_mcp_tools
from radbot.tools.mcp.mcp_utils import convert_to_adk_tool

__all__ = [
    "Event",
    "create_fileserver_toolset",
    "FileServerMCP",
    "get_available_mcp_tools",
    "convert_to_adk_tool",
]
