"""
Core agent implementation for RadBot.

This module defines the essential RadBotAgent class and factory functions for the RadBot framework.
It serves as the single source of truth for all agent functionality.
"""

import logging

# Import agent_methods for its side effects — it monkey-patches method
# implementations onto RadBotAgent (add_tool, process_message,
# register_tool_handlers, etc.). Required even though no names are used.
import radbot.agent.agent_methods  # noqa: F401
from radbot.agent.agent_base import FALLBACK_INSTRUCTION, RadBotAgent
from radbot.agent.agent_factory import AgentFactory
from radbot.agent.agent_utils import (
    create_agent,
    create_core_agent_for_web,
    create_runner,
)

# Configure logging
logger = logging.getLogger(__name__)

# Export all relevant components
__all__ = [
    "FALLBACK_INSTRUCTION",
    "RadBotAgent",
    "AgentFactory",
    "create_runner",
    "create_agent",
    "create_core_agent_for_web",
]
