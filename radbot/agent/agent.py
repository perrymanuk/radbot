"""
Core agent implementation for RadBot.

This module defines the essential RadBotAgent class and factory functions for the RadBot framework.
It serves as the single source of truth for all agent functionality.
"""

# Import base RadBotAgent class
from radbot.agent.agent_base import (
    FALLBACK_INSTRUCTION,
    Agent,
    Any,
    ConfigManager,
    Content,
    Dict,
    InMemorySessionService,
    List,
    Optional,
    Part,
    RadBotAgent,
    Runner,
    SessionService,
    Union,
    config_manager,
    load_dotenv,
    logging,
    os,
    setup_vertex_environment,
)

# Import AgentFactory
from radbot.agent.agent_factory import AgentFactory

# Import RadBotAgent methods
from radbot.agent.agent_methods import (  # Methods are attached to the RadBotAgent class in the agent_methods.py module
    MessageToDict,
)

# Import utility functions
from radbot.agent.agent_utils import (
    create_agent,
    create_core_agent_for_web,
    create_runner,
    transfer_to_agent,
)

# Configure logging
logger = logging.getLogger(__name__)

# Export all relevant components
__all__ = [
    "RadBotAgent",
    "AgentFactory",
    "create_runner",
    "create_agent",
    "create_core_agent_for_web",
]
