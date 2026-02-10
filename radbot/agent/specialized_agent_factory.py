"""
Factory for creating specialized agents in the RadBot system.

This module implements the specialized agent pattern as described in
the agent_specialization.md documentation.
"""

import logging
from typing import List, Any, Optional

from google.adk.agents import Agent

from radbot.config import config_manager
from radbot.agent.execution_agent import create_execution_agent
from radbot.agent.execution_agent.tools import execution_tools

# Configure logging
logger = logging.getLogger(__name__)


def create_axel_agent(root_agent: Agent) -> Optional[Agent]:
    """
    Create the Axel agent for implementation tasks and register it with the root agent.

    All agents (search_agent, code_execution_agent, scout, axel) are siblings
    under beto. ADK's transfer_to_agent tool can find any agent in the tree
    by name, so no manual bidirectional linking is needed.

    Args:
        root_agent: The root agent to attach Axel to

    Returns:
        The created Axel agent or None if creation failed
    """
    try:
        # Get the model from config
        axel_model = config_manager.get_agent_model("axel_agent_model")
        if not axel_model:
            axel_model = config_manager.get_agent_model("axel_agent")
            if not axel_model:
                axel_model = "gemini-2.5-flash"
                logger.info(f"Using fallback model for Axel: {axel_model}")
            else:
                logger.info(f"Using configured model for Axel: {axel_model}")
        else:
            logger.info(f"Using configured model for Axel: {axel_model}")

        # Create the Axel agent using our factory function
        adk_agent = create_execution_agent(
            name="axel",
            model=axel_model,
            tools=execution_tools,
            as_subagent=True,
            enable_code_execution=True,
            app_name=root_agent.name if hasattr(root_agent, 'name') else "beto"
        )

        # Add Axel to beto's sub-agents list
        current_sub_agents = list(root_agent.sub_agents) if hasattr(root_agent, 'sub_agents') and root_agent.sub_agents else []
        current_sub_agents.append(adk_agent)
        root_agent.sub_agents = current_sub_agents

        logger.info(f"Successfully created and registered Axel agent with {len(execution_tools)} tools")
        return adk_agent

    except Exception as e:
        logger.error(f"Failed to create Axel agent: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def create_specialized_agents(root_agent: Agent) -> List[Agent]:
    """
    Create all specialized agents and register them with the root agent.

    Args:
        root_agent: The root agent to attach specialized agents to

    Returns:
        List of created specialized agents
    """
    specialized_agents = []

    # Create and register Axel agent
    axel_agent = create_axel_agent(root_agent)
    if axel_agent:
        specialized_agents.append(axel_agent)

    # Future specialized agents would be created here

    return specialized_agents
