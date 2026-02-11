"""
Home Assistant tool schemas for Google ADK integration.

This module provides tool schemas for Home Assistant API functions to be used with
the Google Agent Development Kit (ADK).
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Union

# Import necessary components for ADK integration
try:
    # First try to use the newer ADK tool decorator
    from google.adk.tools.decorators import tool

    HAVE_ADK_TOOL_DECORATOR = True
except (ImportError, AttributeError):
    # Fall back to FunctionTool
    from google.adk.tools import FunctionTool

    HAVE_ADK_TOOL_DECORATOR = False

logger = logging.getLogger(__name__)

from radbot.tools.ha_state_cache import search_ha_entities

# Import the tool functions
from radbot.tools.ha_tools_impl import (
    get_ha_entity_state,
    list_ha_entities,
    toggle_ha_entity,
    turn_off_ha_entity,
    turn_on_ha_entity,
)


def create_tool_schemas() -> List[Any]:
    """
    Create schema definitions for Home Assistant tools.

    Returns:
        List of tool objects with proper schemas
    """
    if HAVE_ADK_TOOL_DECORATOR:
        # Using newer ADK tool decorator
        logger.info("Creating Home Assistant tool schemas using ADK tool decorator")
        return create_tool_schemas_with_decorator()
    else:
        # Using FunctionTool fallback
        logger.info("Creating Home Assistant tool schemas using FunctionTool")
        return create_tool_schemas_with_function_tool()


def create_tool_schemas_with_decorator() -> List[Any]:
    """
    Create tool schemas using the ADK tool decorator approach.

    Returns:
        List of decorated tool functions
    """
    # Redefine the functions with decorators

    @tool(
        name="search_home_assistant_entities",
        description="Search for Home Assistant entities by name, room, or function",
        parameters={
            "search_term": {
                "type": "string",
                "description": "Text to search for in entity names, like 'kitchen' or 'lamp'",
            },
            "domain_filter": {
                "type": "string",
                "description": "Optional domain type to filter by (light, switch, sensor, etc.)",
                "required": False,
            },
        },
        required=["search_term"],
    )
    def search_ha_entities_tool(
        search_term: str, domain_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for Home Assistant entities by name, room, or function.

        Args:
            search_term: Text to search for in entity names
            domain_filter: Optional domain to filter results

        Returns:
            Dictionary with matching entities
        """
        return search_ha_entities(search_term, domain_filter)

    @tool(
        name="list_home_assistant_entities",
        description="List all available entities in Home Assistant",
        parameters={},
    )
    def list_ha_entities_tool() -> Dict[str, Any]:
        """
        List all available entities in Home Assistant.

        Returns:
            Dictionary with all entities and their states
        """
        return list_ha_entities()

    @tool(
        name="get_home_assistant_entity_state",
        description="Get the current state and attributes of a specific entity in Home Assistant",
        parameters={
            "entity_id": {
                "type": "string",
                "description": "The unique identifier of the entity (e.g., 'light.living_room', 'sensor.temperature')",
            }
        },
        required=["entity_id"],
    )
    def get_ha_entity_state_tool(entity_id: str) -> Dict[str, Any]:
        """
        Get the current state and attributes of a specific entity in Home Assistant.

        Args:
            entity_id: The unique identifier of the entity

        Returns:
            Dictionary with entity state information
        """
        return get_ha_entity_state(entity_id)

    @tool(
        name="turn_on_home_assistant_entity",
        description="Turn on a Home Assistant entity (light, switch, etc.)",
        parameters={
            "entity_id": {
                "type": "string",
                "description": "The unique identifier of the entity to turn on (e.g., 'light.living_room')",
            }
        },
        required=["entity_id"],
    )
    def turn_on_ha_entity_tool(entity_id: str) -> Dict[str, Any]:
        """
        Turn on a Home Assistant entity (light, switch, etc.).

        Args:
            entity_id: The unique identifier of the entity to turn on

        Returns:
            Dictionary with result information
        """
        return turn_on_ha_entity(entity_id)

    @tool(
        name="turn_off_home_assistant_entity",
        description="Turn off a Home Assistant entity (light, switch, etc.)",
        parameters={
            "entity_id": {
                "type": "string",
                "description": "The unique identifier of the entity to turn off (e.g., 'light.living_room')",
            }
        },
        required=["entity_id"],
    )
    def turn_off_ha_entity_tool(entity_id: str) -> Dict[str, Any]:
        """
        Turn off a Home Assistant entity (light, switch, etc.).

        Args:
            entity_id: The unique identifier of the entity to turn off

        Returns:
            Dictionary with result information
        """
        return turn_off_ha_entity(entity_id)

    @tool(
        name="toggle_home_assistant_entity",
        description="Toggle the state of a Home Assistant entity (e.g., turns lights/switches on if off, off if on)",
        parameters={
            "entity_id": {
                "type": "string",
                "description": "The unique identifier of the entity to toggle (e.g., 'light.living_room')",
            }
        },
        required=["entity_id"],
    )
    def toggle_ha_entity_tool(entity_id: str) -> Dict[str, Any]:
        """
        Toggle the state of a Home Assistant entity.

        Args:
            entity_id: The unique identifier of the entity to toggle

        Returns:
            Dictionary with result information
        """
        return toggle_ha_entity(entity_id)

    # Return the decorated functions
    return [
        search_ha_entities_tool,
        list_ha_entities_tool,
        get_ha_entity_state_tool,
        turn_on_ha_entity_tool,
        turn_off_ha_entity_tool,
        toggle_ha_entity_tool,
    ]


def create_tool_schemas_with_function_tool() -> List[Any]:
    """
    Create tool schemas using the FunctionTool approach.

    Returns:
        List of FunctionTool instances
    """
    tools = []

    # Search entities tool
    search_tool = FunctionTool(
        function=search_ha_entities,
        function_schema={
            "name": "search_home_assistant_entities",
            "description": "Search for Home Assistant entities by name, room, or function",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Text to search for in entity names, like 'kitchen' or 'lamp'",
                    },
                    "domain_filter": {
                        "type": "string",
                        "description": "Optional domain type to filter by (light, switch, sensor, etc.)",
                    },
                },
                "required": ["search_term"],
            },
        },
    )
    tools.append(search_tool)

    # List entities tool
    list_tool = FunctionTool(
        function=list_ha_entities,
        function_schema={
            "name": "list_home_assistant_entities",
            "description": "List all available entities in Home Assistant",
            "parameters": {"type": "object", "properties": {}},
        },
    )
    tools.append(list_tool)

    # Get entity state tool
    get_state_tool = FunctionTool(
        function=get_ha_entity_state,
        function_schema={
            "name": "get_home_assistant_entity_state",
            "description": "Get the current state and attributes of a specific entity in Home Assistant",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The unique identifier of the entity (e.g., 'light.living_room', 'sensor.temperature')",
                    }
                },
                "required": ["entity_id"],
            },
        },
    )
    tools.append(get_state_tool)

    # Turn on entity tool
    turn_on_tool = FunctionTool(
        function=turn_on_ha_entity,
        function_schema={
            "name": "turn_on_home_assistant_entity",
            "description": "Turn on a Home Assistant entity (light, switch, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The unique identifier of the entity to turn on (e.g., 'light.living_room')",
                    }
                },
                "required": ["entity_id"],
            },
        },
    )
    tools.append(turn_on_tool)

    # Turn off entity tool
    turn_off_tool = FunctionTool(
        function=turn_off_ha_entity,
        function_schema={
            "name": "turn_off_home_assistant_entity",
            "description": "Turn off a Home Assistant entity (light, switch, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The unique identifier of the entity to turn off (e.g., 'light.living_room')",
                    }
                },
                "required": ["entity_id"],
            },
        },
    )
    tools.append(turn_off_tool)

    # Toggle entity tool
    toggle_tool = FunctionTool(
        function=toggle_ha_entity,
        function_schema={
            "name": "toggle_home_assistant_entity",
            "description": "Toggle the state of a Home Assistant entity (e.g., turns lights/switches on if off, off if on)",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The unique identifier of the entity to toggle (e.g., 'light.living_room')",
                    }
                },
                "required": ["entity_id"],
            },
        },
    )
    tools.append(toggle_tool)

    return tools
