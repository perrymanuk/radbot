"""
Factory for creating specialized agents in the RadBot system.

Creates all domain-specific sub-agents (casa, planner, tracker, comms, axel)
and returns them for inclusion in the root agent's sub_agents list at
construction time.

NOTE: ADK 2.0 builds the internal routing mesh in model_post_init, so all
sub-agents MUST be passed to the root Agent constructor. Do NOT add agents
to sub_agents after construction — they won't be part of the mesh and
transfer_to_agent won't find them.
"""

import logging
from typing import Any, List, Optional

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

        logger.debug(f"Using model for Axel: {axel_model}")

        adk_agent = create_execution_agent(
            name="axel",
            model=axel_model,
            tools=execution_tools,
            as_subagent=True,
            enable_code_execution=True,
            app_name="beto",
        )

        logger.debug(
            f"Successfully created Axel agent with {len(execution_tools)} tools"
        )
        return adk_agent

    except Exception as e:
        logger.error(f"Failed to create Axel agent: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None


def create_specialized_agents() -> List[Agent]:
    """Create all specialized agents and return them.

    Returns:
        List of created specialized agents (None results filtered out).
    """
    specialized_agents = []

    # Import factories lazily to avoid circular imports
    from radbot.agent.comms_agent.factory import create_comms_agent
    from radbot.agent.home_agent.factory import create_home_agent
    from radbot.agent.planner_agent.factory import create_planner_agent
    from radbot.agent.tracker_agent.factory import create_tracker_agent

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
                logger.debug(f"Created {agent_name} agent")
            else:
                logger.warning(f"Factory returned None for {agent_name} agent")
        except Exception as e:
            logger.error(f"Failed to create {agent_name} agent: {e}")

    logger.info(f"Created {len(specialized_agents)} specialized agents")

    return specialized_agents
