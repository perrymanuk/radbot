"""
Tools package for Radbot.

This package provides various tools for the Radbot agent.
"""

# Re-export tools from subpackages
from radbot.tools.basic import get_current_time
from radbot.tools.homeassistant import (
    HomeAssistantRESTClient,
    get_ha_client,
    get_ha_entity_state,
    list_ha_entities,
    search_ha_entities,
    toggle_ha_entity,
    turn_off_ha_entity,
    turn_on_ha_entity,
)
from radbot.tools.mcp import (
    FileServerMCP,
    convert_to_adk_tool,
    create_fileserver_toolset,
    get_available_mcp_tools,
)
from radbot.tools.memory import search_past_conversations, store_important_information
from radbot.tools.shell import ALLOWED_COMMANDS, execute_shell_command, get_shell_tool

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
