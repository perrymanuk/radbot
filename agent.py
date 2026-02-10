"""
Root agent.py file for ADK web interface.

This file is used by the ADK web interface to create the agent with all needed tools.
The ADK web interface uses this file directly based on the adk.config.json setting.
"""

# Import from modular components
from radbot.agent.agent_initializer import logger

from radbot.agent.agent_core import (
    root_agent,
    create_agent
)

# Log startup
logger.info("ROOT agent.py loaded - this is the main implementation loaded by ADK web")

# Export create_agent function for ADK web interface
__all__ = ["create_agent"]
