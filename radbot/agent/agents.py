"""
Agent registry module for RadBot system.

This module re-exports agent instances from agent_tools_setup.py,
which is the single source of truth for agent creation. This ensures
that the agents used by agent_tools.py (AgentTool wrappers) are the
exact same objects that are registered as beto's sub_agents.
"""

import logging

# Set up logging
logger = logging.getLogger(__name__)

# Import the canonical agent instances from agent_tools_setup
# These are the same instances used as beto's sub_agents in agent_core.py
from radbot.agent.agent_tools_setup import (
    code_execution_agent,
    scout_agent,
    search_agent,
)

# Export all agents
__all__ = ["search_agent", "code_execution_agent", "scout_agent"]

# Log available agents
available_agents = []
if search_agent:
    available_agents.append("search_agent")
if code_execution_agent:
    available_agents.append("code_execution_agent")
if scout_agent:
    available_agents.append("scout_agent")

logger.info(f"Available agents in registry: {', '.join(available_agents)}")
