"""
ADK built-in tools integration.

This module provides integration with Google ADK's built-in tools 
like google_search and built_in_code_execution.
"""

import logging
import os
from google.adk.tools.transfer_to_agent_tool import transfer_to_agent

# Initialize logger
logger = logging.getLogger(__name__)

from .search_tool import create_search_agent
from .code_execution_tool import create_code_execution_agent

# Check if ADK built-in tools should be enabled
def is_search_enabled():
    """Check if search is enabled via environment variables."""
    return os.environ.get("RADBOT_ENABLE_ADK_SEARCH", "false").lower() in ["true", "1", "yes", "enable"]

def is_code_execution_enabled():
    """Check if code execution is enabled via environment variables."""
    return os.environ.get("RADBOT_ENABLE_ADK_CODE_EXEC", "false").lower() in ["true", "1", "yes", "enable"]

__all__ = [
    'create_search_agent',
    'create_code_execution_agent',
    'is_search_enabled',
    'is_code_execution_enabled'
]
