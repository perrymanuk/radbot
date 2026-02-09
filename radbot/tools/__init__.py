"""
Tools package for Radbot.

This package provides various tools for the Radbot agent.
"""

# Re-export tools from subpackages
from radbot.tools.basic import get_current_time
from radbot.tools.homeassistant import (
    get_ha_client,
    HomeAssistantRESTClient,
    search_ha_entities,
    list_ha_entities,
    get_ha_entity_state,
    turn_on_ha_entity,
    turn_off_ha_entity,
    toggle_ha_entity,
)
from radbot.tools.memory import search_past_conversations, store_important_information
from radbot.tools.mcp import (
    create_fileserver_toolset,
    FileServerMCP,
    get_available_mcp_tools,
    convert_to_adk_tool,
)
from radbot.tools.shell import execute_shell_command, ALLOWED_COMMANDS, get_shell_tool

# Keep todo tools as-is since they're already in a directory

__all__ = [
    # Basic tools
    "get_current_time",

    # Home Assistant tools
    "get_ha_client",
    "HomeAssistantRESTClient",
    "search_ha_entities",
    "list_ha_entities",
    "get_ha_entity_state",
    "turn_on_ha_entity",
    "turn_off_ha_entity",
    "toggle_ha_entity",

    # Memory tools
    "search_past_conversations",
    "store_important_information",

    # MCP tools
    "create_fileserver_toolset",
    "FileServerMCP",
    "get_available_mcp_tools",
    "convert_to_adk_tool",

    # Shell tools
    "execute_shell_command",
    "ALLOWED_COMMANDS",
    "get_shell_tool",
]
