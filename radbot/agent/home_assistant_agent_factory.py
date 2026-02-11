"""
Home Assistant agent factory for creating agents with Home Assistant capabilities.

This module provides a factory function for creating agents with Home Assistant
integration using the REST API approach.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from google.adk import Agent

from radbot.config.settings import ConfigManager

# Import tools directly, but separately to avoid circular imports
from radbot.tools.homeassistant import (
    get_ha_entity_state,
    list_ha_entities,
    search_ha_entities,
    toggle_ha_entity,
    turn_off_ha_entity,
    turn_on_ha_entity,
)

logger = logging.getLogger(__name__)


def create_home_assistant_agent_factory(
    base_agent_factory: Callable,
    config_manager: Optional[ConfigManager] = None,
    base_tools: Optional[List[Any]] = None,
) -> Callable:
    """
    Create a factory function that adds Home Assistant capabilities to agents.

    Args:
        base_agent_factory: Base agent factory function to extend
        config_manager: Optional configuration manager instance
        base_tools: Optional list of base tools to include

    Returns:
        A factory function that creates agents with Home Assistant capabilities
    """
    if not config_manager:
        config_manager = ConfigManager()

    def factory_function(*args, **kwargs) -> Agent:
        """
        Factory function to create an agent with Home Assistant capabilities.

        Args:
            *args: Positional arguments to pass to the base agent factory
            **kwargs: Keyword arguments to pass to the base agent factory

        Returns:
            An agent with Home Assistant capabilities
        """
        # Check if Home Assistant integration is enabled
        ha_enabled = config_manager.is_home_assistant_enabled()

        if not ha_enabled:
            logger.info("Home Assistant integration not enabled, using base agent")
            return base_agent_factory(*args, **kwargs)

        logger.info("Creating agent with Home Assistant REST API integration")

        # Include any existing tools
        tools = list(kwargs.pop("tools", []))
        if base_tools:
            tools.extend(base_tools)

        # Add Home Assistant tools
        ha_tools = [
            # Entity discovery and state query tools
            search_ha_entities,
            list_ha_entities,
            get_ha_entity_state,
            # Entity control tools
            turn_on_ha_entity,
            turn_off_ha_entity,
            toggle_ha_entity,
        ]

        # Add Home Assistant tools to the agent's tools
        tools.extend(ha_tools)
        logger.info(f"Added {len(ha_tools)} Home Assistant tools to agent")

        # Create the agent with the combined tools
        agent = base_agent_factory(*args, tools=tools, **kwargs)

        return agent

    return factory_function


def create_home_assistant_enabled_agent(
    agent_factory: Callable,
    base_tools: Optional[List[Any]] = None,
    ensure_memory_tools: bool = True,
) -> Agent:
    """
    Create an agent with Home Assistant capabilities.

    Args:
        agent_factory: Function to create the base agent
        base_tools: Optional list of base tools to include
        ensure_memory_tools: Whether to ensure memory tools are included

    Returns:
        An agent with Home Assistant capabilities
    """
    # Start with base tools
    tools = list(base_tools or [])

    # Add Home Assistant tools with search as highest priority
    ha_tools = [
        # Entity discovery and state query tools
        search_ha_entities,
        list_ha_entities,
        get_ha_entity_state,
        # Entity control tools
        turn_on_ha_entity,
        turn_off_ha_entity,
        toggle_ha_entity,
    ]

    # Add the search tool as highest priority
    tools.insert(0, search_ha_entities)

    # Add other Home Assistant tools
    for tool in ha_tools[1:]:
        tools.append(tool)

    logger.info(f"Added {len(ha_tools)} Home Assistant tools to agent")

    # Add memory tools if requested
    if ensure_memory_tools:
        try:
            from radbot.tools.memory import (
                search_past_conversations,
                store_important_information,
            )

            # Check if memory tools are already in tools list
            memory_tools = [search_past_conversations, store_important_information]
            existing_tool_names = set()

            for tool in tools:
                if hasattr(tool, "__name__"):
                    existing_tool_names.add(tool.__name__)

            # Add any missing memory tools
            for tool in memory_tools:
                if tool.__name__ not in existing_tool_names:
                    tools.append(tool)
                    logger.info(f"Added memory tool: {tool.__name__}")
        except ImportError:
            logger.info("Memory tools not available, skipping")

    # Create the agent with the combined tools
    agent = agent_factory(tools=tools)

    # Log the tools added to the agent
    if hasattr(agent, "tools"):
        logger.info(f"Agent created with {len(agent.tools)} tools")
    elif hasattr(agent, "root_agent") and hasattr(agent.root_agent, "tools"):
        logger.info(f"Agent wrapper created with {len(agent.root_agent.tools)} tools")

    return agent
