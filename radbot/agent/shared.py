"""
Shared utilities for agent factory modules.

Centralizes patterns that were previously duplicated across all factory files.
"""

import logging

from radbot.config import config_manager

logger = logging.getLogger(__name__)

TRANSFER_INSTRUCTIONS = (
    "\n\nCRITICAL RULE — Returning control:\n"
    "1. First, complete your task using your tools and compose your full text response with the results.\n"
    "2. Then, call transfer_to_agent(agent_name='beto') to return control to the main agent.\n"
    "You MUST always do BOTH steps — never return without text content, and never skip the transfer back."
)


def resolve_agent_model(agent_name: str) -> str:
    """Resolve the model to use for an agent, falling back to sub_model.

    Args:
        agent_name: The agent config key (e.g. "casa_agent", "planner_agent").

    Returns:
        The resolved model string.
    """
    model = config_manager.get_agent_model(agent_name)
    if not model:
        model = config_manager.get_sub_model()
    return model


def load_agent_instruction(agent_name: str, fallback: str) -> str:
    """Load agent instructions from config, falling back to a default string.

    Automatically appends TRANSFER_INSTRUCTIONS.

    Args:
        agent_name: The instruction file name (e.g. "casa", "planner").
        fallback: Default instruction text if no file is found.

    Returns:
        The full instruction string with transfer instructions appended.
    """
    try:
        instruction = config_manager.get_instruction(agent_name)
    except FileNotFoundError:
        instruction = fallback
    instruction += TRANSFER_INSTRUCTIONS
    return instruction
