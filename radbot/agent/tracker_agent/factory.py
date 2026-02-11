"""
Factory function for creating the Tracker agent.

Tracker handles todo/project management and webhook configuration.
"""

import logging
from typing import Optional

from google.adk.agents import Agent

from radbot.config import config_manager

logger = logging.getLogger(__name__)

TRANSFER_INSTRUCTIONS = (
    "\n\nCRITICAL RULE — Returning control:\n"
    "1. First, complete your task using your tools and compose your full text response with the results.\n"
    "2. Then, call transfer_to_agent(agent_name='beto') to return control to the main agent.\n"
    "You MUST always do BOTH steps — never return without text content, and never skip the transfer back."
)


def create_tracker_agent() -> Optional[Agent]:
    """Create the Tracker agent for todo/project management and webhooks.

    Returns:
        The created Tracker ADK Agent, or None if creation failed.
    """
    try:
        # Get model
        model = config_manager.get_agent_model("tracker_agent")
        if not model:
            model = config_manager.get_sub_model()
        logger.info(f"Tracker agent model: {model}")

        # Get instruction
        try:
            instruction = config_manager.get_instruction("tracker")
        except FileNotFoundError:
            instruction = (
                "You are Tracker, a task and project management specialist. "
                "Manage todo items, projects, and webhook integrations."
            )
        instruction += TRANSFER_INSTRUCTIONS

        # Build tools list
        tools = []

        # Todo tools
        try:
            from radbot.tools.todo import ALL_TOOLS

            tools.extend(ALL_TOOLS)
            logger.info(f"Added {len(ALL_TOOLS)} todo tools to Tracker")
        except Exception as e:
            logger.warning(f"Failed to add todo tools to Tracker: {e}")

        # Webhook tools
        try:
            from radbot.tools.webhooks import WEBHOOK_TOOLS

            tools.extend(WEBHOOK_TOOLS)
            logger.info(f"Added {len(WEBHOOK_TOOLS)} webhook tools to Tracker")
        except Exception as e:
            logger.warning(f"Failed to add webhook tools to Tracker: {e}")

        # Agent-scoped memory tools
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        memory_tools = create_agent_memory_tools("tracker")
        tools.extend(memory_tools)

        agent = Agent(
            name="tracker",
            model=model,
            description="Todo lists, project management, task tracking, and webhook configuration.",
            instruction=instruction,
            tools=tools,
        )

        logger.info(f"Created Tracker agent with {len(tools)} tools")
        return agent

    except Exception as e:
        logger.error(f"Failed to create Tracker agent: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None
