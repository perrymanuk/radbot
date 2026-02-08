"""
Root agent initialization for ADK web interface.

This module sets up the imports and basic configuration needed for the RadBot agents.
It serves as the initialization module for the root agent.py file.
"""

import logging
import os
from typing import Optional, Any, List
from datetime import date

# Set up logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
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
logger.info(f"Config manager loaded. Model config: {config_manager.model_config}")
logger.info(f"Main model from config: '{config_manager.get_main_model()}'")

# Import tools
from google.adk.tools import load_artifacts
from radbot.tools.basic import get_current_time, get_weather
from radbot.tools.memory import search_past_conversations, store_important_information
from radbot.tools.web_search import create_tavily_search_tool
from radbot.tools.mcp import create_fileserver_toolset
from radbot.tools.mcp.mcp_crawl4ai_client import create_crawl4ai_toolset
from radbot.tools.shell import get_shell_tool
from radbot.tools.todo import ALL_TOOLS, init_database

# Import calendar tools
from radbot.tools.calendar.calendar_tools import (
    list_calendar_events_tool,
    create_calendar_event_tool,
    update_calendar_event_tool,
    delete_calendar_event_tool,
    check_calendar_availability_tool
)

# Import Gmail tools
from radbot.tools.gmail import (
    list_emails_tool,
    search_emails_tool,
    get_email_tool,
    list_gmail_accounts_tool,
)

# Import Home Assistant tools
from radbot.tools.homeassistant import (
    list_ha_entities,
    get_ha_entity_state,
    turn_on_ha_entity,
    turn_off_ha_entity,
    toggle_ha_entity,
    search_ha_entities,
    get_ha_client
)

# Import agent factory functions
from radbot.tools.adk_builtin.search_tool import create_search_agent
from radbot.tools.adk_builtin.code_execution_tool import create_code_execution_agent
from radbot.agent.research_agent.factory import create_research_agent

# Import the AgentTool functions for sub-agent interactions
from radbot.tools.agent_tools import (
    call_search_agent,
    call_code_execution_agent,
    call_scout_agent
)

# Import dynamic MCP tools loader
from radbot.tools.mcp.dynamic_tools_loader import load_dynamic_mcp_tools, load_specific_mcp_tools

# Import scheduler tools
from radbot.tools.scheduler import SCHEDULER_TOOLS, init_scheduler_schema

# Import webhook tools
from radbot.tools.webhooks import WEBHOOK_TOOLS, init_webhook_schema

# Import Jira tools
from radbot.tools.jira import JIRA_TOOLS

# Log startup
logger.info("agent_initializer.py loaded - initialization module for root agent.py")
# Removed debug message for MCP_FS_ROOT_DIR