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

TASK_FINISH_INSTRUCTIONS = (
    "\n\nCRITICAL RULE — Completing your task:\n"
    "1. Complete your task using your tools.\n"
    "2. Call finish_task(result='<your full response with all results>') to return the results.\n"
    "You MUST call finish_task when done — include ALL substantive data in the result string."
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


def load_agent_instruction(agent_name: str, fallback: str, *, use_task_mode: bool = False) -> str:
    """Load agent instructions from config, falling back to a default string.

    Automatically appends completion instructions (task or transfer).

    Args:
        agent_name: The instruction file name (e.g. "casa", "planner").
        fallback: Default instruction text if no file is found.
        use_task_mode: If True, append TASK_FINISH_INSTRUCTIONS instead of TRANSFER_INSTRUCTIONS.

    Returns:
        The full instruction string with completion instructions appended.
    """
    try:
        instruction = config_manager.get_instruction(agent_name)
    except FileNotFoundError:
        instruction = fallback
    instruction += TASK_FINISH_INSTRUCTIONS if use_task_mode else TRANSFER_INSTRUCTIONS
    return instruction
