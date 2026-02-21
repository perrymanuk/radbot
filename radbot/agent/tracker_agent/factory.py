"""
Factory function for creating the Tracker agent.

Tracker handles todo/project management and webhook configuration.
"""

import logging
from typing import Optional

from google.adk.agents import Agent

from radbot.agent.shared import load_agent_instruction, resolve_agent_model

logger = logging.getLogger(__name__)


def create_tracker_agent() -> Optional[Agent]:
    """Create the Tracker agent for todo/project management and webhooks.

    Returns:
        The created Tracker ADK Agent, or None if creation failed.
    """
    try:
        model = resolve_agent_model("tracker_agent")
        logger.info(f"Tracker agent model: {model}")

        instruction = load_agent_instruction(
            "tracker",
            "You are Tracker, a task and project management specialist. "
            "Manage todo items, projects, and webhook integrations.",
        )

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
