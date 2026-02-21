"""
Factory function for creating the Comms agent.

Comms handles Gmail (read-only) and Jira issue management.
"""

import logging
from typing import Optional

from google.adk.agents import Agent

from radbot.agent.shared import load_agent_instruction, resolve_agent_model

logger = logging.getLogger(__name__)


def create_comms_agent() -> Optional[Agent]:
    """Create the Comms agent for email and issue tracking.

    Returns:
        The created Comms ADK Agent, or None if creation failed.
    """
    try:
        model = resolve_agent_model("comms_agent")
        logger.info(f"Comms agent model: {model}")

        instruction = load_agent_instruction(
            "comms",
            "You are Comms, a communications specialist. "
            "Read emails via Gmail and manage Jira issues.",
        )

        # Build tools list
        tools = []

        # Gmail tools
        try:
            from radbot.tools.gmail import (
                get_email_tool,
                list_emails_tool,
                list_gmail_accounts_tool,
                search_emails_tool,
            )

            tools.extend(
                [
                    list_emails_tool,
                    search_emails_tool,
                    get_email_tool,
                    list_gmail_accounts_tool,
                ]
            )
            logger.info("Added 4 Gmail tools to Comms")
        except Exception as e:
            logger.warning(f"Failed to add Gmail tools to Comms: {e}")

        # Jira tools
        try:
            from radbot.tools.jira import JIRA_TOOLS

            tools.extend(JIRA_TOOLS)
            logger.info(f"Added {len(JIRA_TOOLS)} Jira tools to Comms")
        except Exception as e:
            logger.warning(f"Failed to add Jira tools to Comms: {e}")

        # Agent-scoped memory tools
        from radbot.tools.memory.agent_memory_factory import create_agent_memory_tools

        memory_tools = create_agent_memory_tools("comms")
        tools.extend(memory_tools)

        agent = Agent(
            name="comms",
            model=model,
            description="Email (Gmail read-only) and Jira issue management (list, view, transition, comment, search).",
            instruction=instruction,
            tools=tools,
        )

        logger.info(f"Created Comms agent with {len(tools)} tools")
        return agent

    except Exception as e:
        logger.error(f"Failed to create Comms agent: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return None
