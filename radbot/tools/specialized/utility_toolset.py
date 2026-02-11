"""Utility toolset for specialized agents.

This module provides common utility tools needed across multiple agents,
such as time functions and general utilities.
"""

import logging
from typing import Any, List, Optional

# Import basic utility tools
try:
    from radbot.tools.basic.basic_tools import get_current_time
except ImportError:
    get_current_time = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)


def create_utility_toolset() -> List[Any]:
    """Create the set of tools for the utility specialized agent.

    Returns:
        List of common utility tools
    """
    toolset = []

    # Add time utility
    if get_current_time:
        try:
            toolset.append(get_current_time)
            logger.info("Added get_current_time to utility toolset")
        except Exception as e:
            logger.error(f"Failed to add get_current_time: {e}")

    return toolset


# Register the toolset with the system
register_toolset(
    name="utility",
    toolset_func=create_utility_toolset,
    description="Agent providing common utility functions",
    allowed_transfers=[],  # Only allows transfer back to main orchestrator
)
