"""
Root agent initialization for ADK web interface.

This module sets up the imports and basic configuration needed for the RadBot agents.
It serves as the initialization module for the root agent.py file.

Domain tool imports have been moved to individual agent factories
(home_agent, planner_agent, comms_agent, etc.).
"""

import logging

from dotenv import load_dotenv

# Load environment variables before other imports that depend on config/env.
load_dotenv()

# Import ADK components. These imports are re-exported for downstream
# modules (agent_core.py, agent.py) — listed in __all__ so flake8
# doesn't flag them as unused.
from google.adk.agents import Agent  # noqa: E402 — after load_dotenv()
from google.adk.agents.callback_context import CallbackContext  # noqa: E402
from google.genai import types  # noqa: E402

from radbot.config import config_manager  # noqa: E402

logger = logging.getLogger(__name__)

__all__ = ["Agent", "CallbackContext", "config_manager", "logger", "types"]

# Log basic info
logger.debug(f"Config manager loaded. Model config: {config_manager.model_config}")
logger.debug(f"Main model from config: '{config_manager.get_main_model()}'")

# Log startup
logger.debug("agent_initializer.py loaded - initialization module for root agent.py")
