"""
Agent Tool functions for RadBot.

This module contains AgentTool functions for interacting with specialized agents.
It follows the pattern used in Google's ADK samples for agent interactions.

Agent instances are imported lazily from agent_tools_setup.py to avoid
circular imports (agent_initializer.py imports this module, and
agent_tools_setup.py imports agent_initializer.py).
"""

import logging
import json
from typing import Optional, Dict, Any, List

from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool

# Set up logging
logger = logging.getLogger(__name__)


def _get_search_agent():
    """Lazily import the search agent to avoid circular imports."""
    from radbot.agent.agent_tools_setup import search_agent
    return search_agent


def _get_code_execution_agent():
    """Lazily import the code execution agent to avoid circular imports."""
    from radbot.agent.agent_tools_setup import code_execution_agent
    return code_execution_agent


def _get_scout_agent():
    """Lazily import the scout agent to avoid circular imports."""
    from radbot.agent.agent_tools_setup import scout_agent
    return scout_agent


async def call_search_agent(
    query: str,
    max_results: int = 5,
    tool_context: Optional[ToolContext] = None
) -> str:
    """
    Execute a web search query using the search agent.

    Args:
        query: The search query to execute
        max_results: Maximum number of results to return (default: 5)
        tool_context: Tool context from the caller (optional)

    Returns:
        Search results formatted as text
    """
    agent = _get_search_agent()
    if not agent:
        return "Search agent is not available. Please check your configuration."

    logger.info(f"Calling search agent with query: {query}")

    # Create the agent tool for search_agent
    agent_tool = AgentTool(agent=agent)

    # Prepare the request
    request = {
        "query": query,
        "max_results": max_results
    }

    try:
        # Execute the search agent
        search_results = await agent_tool.run_async(
            args={"request": json.dumps(request)},
            tool_context=tool_context
        )

        logger.info(f"Search agent returned {len(search_results) if search_results else 0} characters of results")
        return search_results
    except Exception as e:
        error_msg = f"Error calling search agent: {str(e)}"
        logger.error(error_msg)
        return error_msg

async def call_code_execution_agent(
    code: str,
    description: str = "",
    tool_context: Optional[ToolContext] = None
) -> str:
    """
    Execute Python code using the code execution agent.

    Args:
        code: The Python code to execute
        description: Optional description of what the code does
        tool_context: Tool context from the caller (optional)

    Returns:
        Code execution results formatted as text
    """
    agent = _get_code_execution_agent()
    if not agent:
        return "Code execution agent is not available. Please check your configuration."

    logger.info(f"Calling code execution agent with {len(code)} characters of code")

    # Create the agent tool for code_execution_agent
    agent_tool = AgentTool(agent=agent)

    # Prepare the request
    request = {
        "code": code,
        "description": description
    }

    try:
        # Execute the code execution agent
        execution_results = await agent_tool.run_async(
            args={"request": json.dumps(request)},
            tool_context=tool_context
        )

        logger.info(f"Code execution agent returned {len(execution_results) if execution_results else 0} characters of results")
        return execution_results
    except Exception as e:
        error_msg = f"Error calling code execution agent: {str(e)}"
        logger.error(error_msg)
        return error_msg

async def call_scout_agent(
    research_topic: str,
    tool_context: Optional[ToolContext] = None
) -> str:
    """
    Research a topic using the scout agent.

    Args:
        research_topic: The topic to research
        tool_context: Tool context from the caller (optional)

    Returns:
        Research results formatted as text
    """
    agent = _get_scout_agent()
    if not agent:
        return "Scout agent is not available. Please check your configuration."

    logger.info(f"Calling scout agent with research topic: {research_topic}")

    # Create the agent tool for scout_agent
    agent_tool = AgentTool(agent=agent)

    try:
        # Execute the scout agent
        research_results = await agent_tool.run_async(
            args={"request": research_topic},
            tool_context=tool_context
        )

        logger.info(f"Scout agent returned {len(research_results) if research_results else 0} characters of results")
        return research_results
    except Exception as e:
        error_msg = f"Error calling scout agent: {str(e)}"
        logger.error(error_msg)
        return error_msg

# Create synchronous wrappers for easier use in non-async contexts
def search(query: str, max_results: int = 5) -> str:
    """Synchronous wrapper for call_search_agent."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Create a new event loop if one doesn't exist
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(call_search_agent(query, max_results))

def execute_code(code: str, description: str = "") -> str:
    """Synchronous wrapper for call_code_execution_agent."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Create a new event loop if one doesn't exist
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(call_code_execution_agent(code, description))

def research(topic: str) -> str:
    """Synchronous wrapper for call_scout_agent."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Create a new event loop if one doesn't exist
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(call_scout_agent(topic))
