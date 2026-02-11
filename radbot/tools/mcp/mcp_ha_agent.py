"""
Home Assistant agent factory for MCP integration.

This module provides factory functions for creating agents with Home Assistant
capabilities via MCP Server integration.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

from radbot.tools.mcp.mcp_entity_search import (
    create_find_ha_entities_tool,
    search_home_assistant_entities,
)

# Import necessary components
from radbot.tools.mcp.mcp_homeassistant import create_home_assistant_toolset


def create_ha_mcp_enabled_agent(
    agent_factory, base_tools=None, ensure_memory_tools=True
):
    """
    Create an agent with Home Assistant MCP tools.

    Args:
        agent_factory: Function to create an agent (like AgentFactory.create_root_agent or create_memory_enabled_agent)
        base_tools: Optional list of base tools to include
        ensure_memory_tools: If True, ensure memory tools are included in the agent tools

    Returns:
        Agent: The created agent, or None if creation fails
    """
    try:
        # Start with base tools or empty list
        tools = list(base_tools or [])

        # Add the entity search tool as a pure function (highest priority)
        tools.insert(0, search_home_assistant_entities)
        logger.info(
            "Added search_home_assistant_entities as pure function (highest priority)"
        )

        # Ensure memory tools are included if requested
        if ensure_memory_tools:
            from radbot.tools.memory.memory_tools import (
                search_past_conversations,
                store_important_information,
            )

            memory_tools = [search_past_conversations, store_important_information]

            # Check if memory tools are already in tools list
            memory_tool_names = set([tool.__name__ for tool in memory_tools])
            existing_tool_names = set()
            for tool in tools:
                if hasattr(tool, "__name__"):
                    existing_tool_names.add(tool.__name__)
                elif hasattr(tool, "name"):
                    existing_tool_names.add(tool.name)

            # Add any missing memory tools
            for tool in memory_tools:
                if tool.__name__ not in existing_tool_names:
                    tools.append(tool)
                    logger.info(f"Explicitly adding memory tool: {tool.__name__}")

        # Also add the wrapped version as a backup
        entity_search_tool = create_find_ha_entities_tool()
        if entity_search_tool:
            tools.insert(1, entity_search_tool)
            logger.info(
                f"Added wrapped entity search tool as backup with name: {getattr(entity_search_tool, 'name', 'unknown')}"
            )

        # Try to add Home Assistant MCP tools (using ADK 0.3.0 API)
        ha_tools = create_home_assistant_toolset()

        if ha_tools and len(ha_tools) > 0:
            logger.info(f"Adding {len(ha_tools)} Home Assistant MCP tools to agent")

            # Create proper function wrappers for each Home Assistant tool with schemas
            from google.adk.tools import FunctionTool

            # Add each tool individually with proper schema information
            for tool in ha_tools:
                if hasattr(tool, "name"):
                    tool_name = tool.name
                    logger.info(f"Processing tool: {tool_name}")

                    # Create a wrapper function with clear parameter definitions
                    if tool_name == "HassTurnOn" or tool_name == "HassTurnOff":
                        # Create a wrapper function for turn on/off
                        def wrap_hass_tool(tool_ref, tool_name_ref):
                            async def wrapped_tool(entity_id: str):
                                """Control a Home Assistant entity."""
                                logger.info(
                                    f"Calling {tool_name_ref} with entity_id: {entity_id}"
                                )
                                return await tool_ref(entity_id=entity_id)

                            # Preserve the original tool name
                            wrapped_tool.__name__ = tool_name_ref
                            return wrapped_tool

                        # Add the wrapped tool with explicit schema
                        wrapped_tool = wrap_hass_tool(tool, tool_name)

                        try:
                            # ADK 0.3.0 style
                            function_tool = FunctionTool(
                                function=wrapped_tool,
                                function_schema={
                                    "name": tool_name,
                                    "description": getattr(
                                        tool,
                                        "description",
                                        f"{tool_name} function for Home Assistant entity control",
                                    ),
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "entity_id": {
                                                "type": "string",
                                                "description": "The entity ID to control (e.g. light.kitchen, switch.fan)",
                                            }
                                        },
                                        "required": ["entity_id"],
                                    },
                                },
                            )
                            logger.info(
                                f"Added wrapped tool: {tool_name} with schema (ADK 0.3.0 style)"
                            )
                        except TypeError:
                            # Fallback for older ADK versions
                            function_tool = FunctionTool(
                                wrapped_tool,
                                {
                                    "name": tool_name,
                                    "description": getattr(
                                        tool,
                                        "description",
                                        f"{tool_name} function for Home Assistant entity control",
                                    ),
                                    "parameters": {
                                        "type": "object",
                                        "properties": {
                                            "entity_id": {
                                                "type": "string",
                                                "description": "The entity ID to control (e.g. light.kitchen, switch.fan)",
                                            }
                                        },
                                        "required": ["entity_id"],
                                    },
                                },
                            )
                            logger.info(
                                f"Added wrapped tool: {tool_name} with schema (legacy style)"
                            )

                        tools.append(function_tool)
                        logger.info(f"Added wrapped tool: {tool_name} with schema")
                    else:
                        # For other tools, just add them directly for now
                        logger.info(f"Adding original tool: {tool_name}")
                        tools.append(tool)
                else:
                    logger.warning(f"Skipping tool without name: {tool}")

            logger.info(f"Total tools after adding HA tools: {len(tools)}")
        else:
            logger.warning("No Home Assistant MCP tools were found")

        # Log all tool names before creating agent
        tool_names = []
        for tool in tools:
            if hasattr(tool, "name"):
                tool_names.append(tool.name)
            elif hasattr(tool, "__name__"):
                tool_names.append(tool.__name__)
            else:
                tool_names.append(str(type(tool)))
        logger.info(f"Tools being added to agent: {', '.join(tool_names[:10])}...")

        # Create the agent with tools
        logger.info(f"Creating agent with {len(tools)} total tools")
        agent = agent_factory(tools=tools)

        # Verify tools were added correctly
        if hasattr(agent, "tools"):
            agent_tools = agent.tools
            search_tools = []
            memory_tools = []
            for t in agent_tools:
                if hasattr(t, "name") and t.name == "search_home_assistant_entities":
                    search_tools.append(t)
                elif (
                    hasattr(t, "__name__")
                    and t.__name__ == "search_home_assistant_entities"
                ):
                    search_tools.append(t)

                # Check for memory tools
                if hasattr(t, "__name__") and t.__name__ in [
                    "search_past_conversations",
                    "store_important_information",
                ]:
                    memory_tools.append(t.__name__)
                elif hasattr(t, "name") and t.name in [
                    "search_past_conversations",
                    "store_important_information",
                ]:
                    memory_tools.append(t.name)

            ha_tools_in_agent = [
                t
                for t in agent_tools
                if hasattr(t, "name") and t.name.startswith("Hass")
            ]
            logger.info(f"Agent created with {len(agent_tools)} tools")
            logger.info(
                f"Found {len(search_tools)} search tools, {len(ha_tools_in_agent)} Home Assistant control tools"
            )
            logger.info(f"Memory tools present: {memory_tools}")
        elif hasattr(agent, "root_agent") and hasattr(agent.root_agent, "tools"):
            agent_tools = agent.root_agent.tools
            search_tools = []
            memory_tools = []
            for t in agent_tools:
                if hasattr(t, "name") and t.name == "search_home_assistant_entities":
                    search_tools.append(t)
                elif (
                    hasattr(t, "__name__")
                    and t.__name__ == "search_home_assistant_entities"
                ):
                    search_tools.append(t)

                # Check for memory tools
                if hasattr(t, "__name__") and t.__name__ in [
                    "search_past_conversations",
                    "store_important_information",
                ]:
                    memory_tools.append(t.__name__)
                elif hasattr(t, "name") and t.name in [
                    "search_past_conversations",
                    "store_important_information",
                ]:
                    memory_tools.append(t.name)

            ha_tools_in_agent = [
                t
                for t in agent_tools
                if hasattr(t, "name") and t.name.startswith("Hass")
            ]
            logger.info(f"Agent wrapper created with {len(agent_tools)} tools")
            logger.info(
                f"Found {len(search_tools)} search tools, {len(ha_tools_in_agent)} Home Assistant control tools"
            )
            logger.info(f"Memory tools present: {memory_tools}")

            # Log all tool names for debugging
            tool_names = []
            for tool in agent_tools:
                if hasattr(tool, "name"):
                    tool_names.append(tool.name)
                elif hasattr(tool, "__name__"):
                    tool_names.append(tool.__name__)
                else:
                    tool_names.append(str(type(tool)))
            logger.info(f"Tools in agent: {', '.join(tool_names[:20])}...")

        return agent
    except Exception as e:
        logger.error(f"Error creating agent with Home Assistant MCP tools: {str(e)}")
        return None
