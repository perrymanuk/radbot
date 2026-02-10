"""
Factory for creating specialized agents in the RadBot system.

Creates all domain-specific sub-agents (casa, planner, tracker, comms, axel)
and registers them with the root agent.
"""

import logging
from typing import List, Any, Optional

from google.adk.agents import Agent

from radbot.config import config_manager

# Configure logging
logger = logging.getLogger(__name__)


def _create_axel_agent() -> Optional[Agent]:
    """Create the Axel agent for implementation tasks.

    Returns:
        The created Axel agent or None if creation failed.
    """
    try:
        from radbot.agent.execution_agent import create_execution_agent
        from radbot.agent.execution_agent.tools import execution_tools

        axel_model = config_manager.get_agent_model("axel_agent_model")
        if not axel_model:
            axel_model = config_manager.get_agent_model("axel_agent")
            if not axel_model:
                axel_model = config_manager.get_sub_model()

        logger.info(f"Using model for Axel: {axel_model}")

        adk_agent = create_execution_agent(
            name="axel",
            model=axel_model,
            tools=execution_tools,
            as_subagent=True,
            enable_code_execution=True,
            app_name="beto",
        )

        logger.info(f"Successfully created Axel agent with {len(execution_tools)} tools")
        return adk_agent

    except Exception as e:
        logger.error(f"Failed to create Axel agent: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def create_specialized_agents(root_agent: Agent) -> List[Agent]:
    """Create all specialized agents and register them with the root agent.

    Args:
        root_agent: The root agent to attach specialized agents to.

    Returns:
        List of created specialized agents.
    """
    specialized_agents = []

    # Import factories lazily to avoid circular imports
    from radbot.agent.home_agent.factory import create_home_agent
    from radbot.agent.planner_agent.factory import create_planner_agent
    from radbot.agent.tracker_agent.factory import create_tracker_agent
    from radbot.agent.comms_agent.factory import create_comms_agent

    # Create all domain agents
    factories = [
        ("casa", create_home_agent),
        ("planner", create_planner_agent),
        ("tracker", create_tracker_agent),
        ("comms", create_comms_agent),
        ("axel", _create_axel_agent),
    ]

    for agent_name, factory in factories:
        try:
            agent = factory()
            if agent:
                specialized_agents.append(agent)
                logger.info(f"Created {agent_name} agent")
            else:
                logger.warning(f"Factory returned None for {agent_name} agent")
        except Exception as e:
            logger.error(f"Failed to create {agent_name} agent: {e}")

    # Add all specialized agents to root agent's sub_agents list
    current_sub_agents = list(root_agent.sub_agents) if root_agent.sub_agents else []
    current_sub_agents.extend(specialized_agents)
    root_agent.sub_agents = current_sub_agents

    # Manually set parent_agent on each new agent.
    # ADK only sets parent_agent during model_post_init (at construction time),
    # so agents added to sub_agents after construction need this set explicitly.
    # Without it, transfer_to_agent("beto") fails on these agents.
    for agent in specialized_agents:
        if agent.parent_agent is None:
            agent.parent_agent = root_agent
            logger.debug(f"Set parent_agent on {agent.name} -> {root_agent.name}")

    logger.info(
        f"Registered {len(specialized_agents)} specialized agents. "
        f"Total sub-agents on beto: {len(root_agent.sub_agents)}"
    )

    return specialized_agents
