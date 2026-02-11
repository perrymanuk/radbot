"""Home Assistant toolset for specialized agents.

This module provides tools for controlling and interacting with
Home Assistant smart home devices and services.
"""

import logging
from typing import Any, List, Optional

# Import Home Assistant tools
try:
    from radbot.tools.homeassistant.ha_tools_impl import (
        get_ha_entity_state,
        list_ha_entities,
        search_ha_entities,
        toggle_ha_entity,
        turn_off_ha_entity,
        turn_on_ha_entity,
    )
except ImportError:
    # Define placeholders if not available
    search_ha_entities = None
    list_ha_entities = None
    get_ha_entity_state = None
    turn_on_ha_entity = None
    turn_off_ha_entity = None
    toggle_ha_entity = None

# Import MCP Home Assistant tools if available
try:
    from radbot.tools.mcp.mcp_homeassistant import get_ha_mcp_tools
except ImportError:
    get_ha_mcp_tools = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)


def create_homeassistant_toolset() -> List[Any]:
    """Create the set of tools for the Home Assistant specialized agent.

    Returns:
        List of tools for controlling smart home devices
    """
    toolset = []

    # Add Home Assistant entity tools
    ha_funcs = [
        (search_ha_entities, "search_ha_entities"),
        (list_ha_entities, "list_ha_entities"),
        (get_ha_entity_state, "get_ha_entity_state"),
        (turn_on_ha_entity, "turn_on_ha_entity"),
        (turn_off_ha_entity, "turn_off_ha_entity"),
        (toggle_ha_entity, "toggle_ha_entity"),
    ]

    for func, name in ha_funcs:
        if func:
            try:
                toolset.append(func)
                logger.info(f"Added {name} to Home Assistant toolset")
            except Exception as e:
                logger.error(f"Failed to add {name}: {e}")

    # Try to add Home Assistant MCP tools if available
    if get_ha_mcp_tools:
        try:
            ha_mcp_tools = get_ha_mcp_tools()
            if ha_mcp_tools:
                toolset.extend(ha_mcp_tools)
                logger.info(
                    f"Added {len(ha_mcp_tools)} HA MCP tools to Home Assistant toolset"
                )
        except Exception as e:
            logger.error(f"Failed to add HA MCP tools: {e}")

    return toolset


# Register the toolset with the system
register_toolset(
    name="homeassistant",
    toolset_func=create_homeassistant_toolset,
    description="Agent specialized in controlling smart home devices",
    allowed_transfers=[],  # Only allows transfer back to main orchestrator
)
