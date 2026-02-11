"""
Agent transfer tools for the Radbot system.

This module provides tools for transferring control between agents
in a multi-agent system.
"""

import inspect
import logging
from typing import Any, Dict, List, Optional

from google.adk.agents import Agent

# Configure logging
logger = logging.getLogger(__name__)


def handle_agent_transfers(agent, from_agent: str, request: str):
    """
    Handle a transfer request from one agent to another.

    This function processes a transfer request from one agent to another,
    handling the agent lookup and transfer.

    Args:
        agent: The agent receiving the transfer
        from_agent: The name of the agent sending the transfer
        request: The request to process

    Returns:
        The response from the agent
    """
    logger.info(
        f"Transfer request from {from_agent} to {agent.name}: {request[:50]}..."
    )

    # Instead of forwarding the request, just return a greeting from the new agent
    # This prevents context confusion between agents by not forwarding the original prompt
    greeting = f"I am now {agent.name}. How can I help you today?"
    logger.info(
        f"Agent transfer complete - request NOT forwarded to maintain context separation"
    )
    return greeting


def process_request(agent, request: str) -> str:
    """
    Process a request using the given agent.

    Args:
        agent: The agent to process the request
        request: The request to process

    Returns:
        The response from the agent
    """
    # Check if the agent has a generate_content method
    if hasattr(agent, "generate_content") and callable(agent.generate_content):
        # Use generate_content method
        response = agent.generate_content(request)

        # Extract text from response
        if hasattr(response, "text"):
            return response.text
        elif hasattr(response, "parts") and response.parts:
            for part in response.parts:
                if hasattr(part, "text") and part.text:
                    return part.text

        # Fallback to string representation
        return str(response)
    else:
        # Log warning about missing method
        logger.warning(f"Agent {agent.name} does not have a generate_content method")
        return f"Error: Agent {agent.name} does not have a generate_content method"


def check_agent_tree(root_agent, visited=None) -> Dict[str, Any]:
    """
    Check the agent tree for proper structure and circular references.

    Args:
        root_agent: The root agent of the tree
        visited: Set of agent IDs already visited

    Returns:
        Dict with agent tree information
    """
    if visited is None:
        visited = set()

    result = {}

    # Generate agent identity
    agent_id = id(root_agent)

    # Check for circular references
    if agent_id in visited:
        return {
            "name": root_agent.name if hasattr(root_agent, "name") else "unnamed",
            "circular": True,
        }

    # Add this agent to visited set
    visited.add(agent_id)

    # Get basic agent info
    if hasattr(root_agent, "name"):
        result["name"] = root_agent.name
    else:
        result["name"] = "unnamed"

    # Get sub-agents
    if hasattr(root_agent, "sub_agents") and root_agent.sub_agents:
        sub_agents = []
        for sub_agent in root_agent.sub_agents:
            sub_agents.append(check_agent_tree(sub_agent, visited))
        result["sub_agents"] = sub_agents

    return result


def find_agent_by_name(root_agent, name: str, visited=None) -> Optional[Agent]:
    """
    Find an agent by name in the agent tree.

    This function traverses the agent tree to find an agent with the given name.
    It handles circular references by keeping track of visited agents.

    Args:
        root_agent: The root agent to start the search from
        name: The name of the agent to find
        visited: Set of agent IDs already visited

    Returns:
        The agent with the given name, or None if not found
    """
    if visited is None:
        visited = set()

    # Generate agent identity
    agent_id = id(root_agent)

    # Check for circular references
    if agent_id in visited:
        return None

    # Add this agent to visited set
    visited.add(agent_id)

    # Check if this is the agent we're looking for
    if hasattr(root_agent, "name") and root_agent.name == name:
        return root_agent

    # Check sub-agents
    if hasattr(root_agent, "sub_agents") and root_agent.sub_agents:
        for sub_agent in root_agent.sub_agents:
            found_agent = find_agent_by_name(sub_agent, name, visited)
            if found_agent:
                return found_agent

    return None


def debug_agent_structure(root_agent):
    """
    Debug utility to log the agent structure.

    Args:
        root_agent: The root agent of the tree
    """
    agent_tree = check_agent_tree(root_agent)
    logger.info(f"Agent tree: {agent_tree}")
