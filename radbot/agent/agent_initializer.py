"""
Root agent initialization for ADK web interface.

This module sets up the imports and basic configuration needed for the RadBot agents.
It serves as the initialization module for the root agent.py file.

Domain tool imports have been moved to individual agent factories
(home_agent, planner_agent, tracker_agent, comms_agent).
"""

import logging

logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

# Import ADK components
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from radbot.config import config_manager

# Log basic info
logger.debug(f"Config manager loaded. Model config: {config_manager.model_config}")
logger.debug(f"Main model from config: '{config_manager.get_main_model()}'")

# Log startup
logger.debug("agent_initializer.py loaded - initialization module for root agent.py")
