"""
MCP integration tools for connecting to various servers.

This module provides utilities for connecting to external services via the Model Context Protocol (MCP).
"""

# Import core functionality
from radbot.tools.mcp.mcp_core import (
    get_available_mcp_tools,
    create_mcp_tools,
    logger,
    os,
    logging,
    Dict, Any, Optional, List, Tuple, Union, Callable
)

# Import Home Assistant tools
from radbot.tools.mcp.mcp_homeassistant import (
    create_home_assistant_toolset
)

# Import entity search tools
from radbot.tools.mcp.mcp_entity_search import (
    create_find_ha_entities_tool,
    search_home_assistant_entities
)

# Import MCP agent factory functions
from radbot.tools.mcp.mcp_agent_factory import (
    create_mcp_enabled_agent,
)

# Import Home Assistant agent factory
from radbot.tools.mcp.mcp_ha_agent import (
    create_ha_mcp_enabled_agent
)

# Export all relevant components
__all__ = [
    'get_available_mcp_tools',
    'create_mcp_tools',
    'create_home_assistant_toolset',
    'create_find_ha_entities_tool',
    'search_home_assistant_entities',
    'create_mcp_enabled_agent',
    'create_ha_mcp_enabled_agent'
]
