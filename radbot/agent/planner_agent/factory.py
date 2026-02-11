"""
Factory function for creating the Planner agent.

Planner handles calendar events, scheduled tasks, reminders, and time queries.
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


def create_planner_agent() -> Optional[Agent]:
    """Create the Planner agent for calendar, scheduling, and reminders.

    Returns:
        The created Planner ADK Agent, or None if creation failed.
    """
    try:
        # Get model
        model = config_manager.get_agent_model("planner_agent")
        if not model:
            model = config_manager.get_sub_model()
        logger.info(f"Planner agent model: {model}")

        # Get instruction
        try:
            instruction = config_manager.get_instruction("planner")
        except FileNotFoundError:
            instruction = (
                "You are Planner, a time and scheduling specialist. "
                "Manage calendar events, scheduled tasks, and reminders."
            )
        instruction += TRANSFER_INSTRUCTIONS

        # Build tools list
        tools = []

        # Basic tools (time)
        try:
            from radbot.tools.basic import get_current_time

            tools.append(get_current_time)
            logger.info("Added get_current_time to Planner")
        except Exception as e:
            logger.warning(f"Failed to add time tool to Planner: {e}")

        # Calendar tools
        try:
            from radbot.tools.calendar.calendar_tools import (
                check_calendar_availability_tool,
                create_calendar_event_tool,
                delete_calendar_event_tool,
                list_calendar_events_tool,
                update_calendar_event_tool,
            )

            tools.extend(
                [
                    list_calendar_events_tool,
                    create_calendar_event_tool,
                    update_calendar_event_tool,
                    delete_calendar_event_tool,
                    check_calendar_availability_tool,
                ]
            )
            logger.info("Added 5 calendar tools to Planner")
        except Exception as e:
            logger.warning(f"Failed to add calendar tools to Planner: {e}")

        # Scheduler tools
        try:
            from radbot.tools.scheduler import SCHEDULER_TOOLS

            tools.extend(SCHEDULER_TOOLS)
            logger.info(f"Added {len(SCHEDULER_TOOLS)} scheduler tools to Planner")
        except Exception as e:
            logger.warning(f"Failed to add scheduler tools to Planner: {e}")

        # Reminder tools
        try:
            from radbot.tools.reminders import REMINDER_TOOLS

            tools.extend(REMINDER_TOOLS)
            logger.info(f"Added {len(REMINDER_TOOLS)} reminder tools to Planner")
        except Exception as e:
            logger.warning(f"Failed to add reminder tools to Planner: {e}")

        # Agent-scoped memory tools
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        memory_tools = create_agent_memory_tools("planner")
        tools.extend(memory_tools)

        agent = Agent(
            name="planner",
            model=model,
            description="Calendar events, scheduled recurring tasks, one-shot reminders, and time queries.",
            instruction=instruction,
            tools=tools,
        )

        logger.info(f"Created Planner agent with {len(tools)} tools")
        return agent

    except Exception as e:
        logger.error(f"Failed to create Planner agent: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None
