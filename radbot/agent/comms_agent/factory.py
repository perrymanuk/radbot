"""
Factory function for creating the Comms agent.

Comms handles Gmail (read-only) and Jira issue management.
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


def create_comms_agent() -> Optional[Agent]:
    """Create the Comms agent for email and issue tracking.

    Returns:
        The created Comms ADK Agent, or None if creation failed.
    """
    try:
        # Get model and resolve (wraps Ollama models in LiteLlm)
        model_str = config_manager.get_agent_model("comms_agent")
        if not model_str:
            model_str = config_manager.get_sub_model()
        model = config_manager.resolve_model(model_str)
        logger.info(f"Comms agent model: {model_str}")

        # Get instruction
        try:
            instruction = config_manager.get_instruction("comms")
        except FileNotFoundError:
            instruction = (
                "You are Comms, a communications specialist. "
                "Read emails via Gmail and manage Jira issues."
            )
        instruction += TRANSFER_INSTRUCTIONS

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
