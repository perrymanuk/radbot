"""
Home Assistant tool schemas for Google ADK integration.

This module provides tool schemas for Home Assistant API functions to be used with
the Google Agent Development Kit (ADK).
"""

import logging
from typing import Any, List

from google.adk.tools import FunctionTool

from radbot.tools.ha_state_cache import search_ha_entities

# Import the tool functions
from radbot.tools.ha_tools_impl import (
    get_ha_entity_state,
    list_ha_entities,
    toggle_ha_entity,
    turn_off_ha_entity,
    turn_on_ha_entity,
)

logger = logging.getLogger(__name__)


def create_tool_schemas() -> List[Any]:
    """
    Create schema definitions for Home Assistant tools.

    Returns:
        List of tool objects with proper schemas
    """
    return create_tool_schemas_with_function_tool()


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
                        "description": "The unique identifier of the entity (e.g., 'light.living_room', 'sensor.temperature')",  # noqa: E501
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
            "description": "Toggle the state of a Home Assistant entity (e.g., turns lights/switches on if off, off if on)",  # noqa: E501
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
