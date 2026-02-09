"""
Factory functions for creating MCP-enabled agents.

This module provides factory functions for creating agents with MCP capabilities
including tools from Home Assistant, FileServer, and other MCP integrations.
"""

import os
import logging
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)

# Import necessary modules
from radbot.config.config_loader import config_loader
from radbot.tools.mcp.mcp_core import get_available_mcp_tools

def create_mcp_enabled_agent(agent_factory: Callable, base_tools: Optional[List[Any]] = None, **kwargs) -> Any:
    """
    Create an agent with all MCP tools enabled.

    This function creates an agent with all MCP tools from config.yaml.

    Args:
        agent_factory: Function to create an agent (like create_agent)
        base_tools: Optional list of base tools to include
        **kwargs: Additional arguments to pass to agent_factory

    Returns:
        Agent: The created agent with MCP tools
    """
    try:
        # Start with base tools or empty list
        tools = list(base_tools or [])

        # Create MCP tools
        mcp_tools = get_available_mcp_tools()

        if mcp_tools:
            # Add the tools to our list
            tools.extend(mcp_tools)
            logger.info(f"Added {len(mcp_tools)} MCP tools to agent")
        else:
            logger.warning("No MCP tools were created")

        # Create the agent with the tools
        agent = agent_factory(tools=tools, **kwargs)
        return agent
    except Exception as e:
        logger.error(f"Error creating agent with MCP tools: {str(e)}")
        # Create agent without MCP tools as fallback
        return agent_factory(tools=base_tools, **kwargs)
