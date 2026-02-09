"""Utility toolset for specialized agents.

This module provides common utility tools needed across multiple agents,
such as time functions, weather information, and general utilities.
"""

import logging
from typing import List, Any, Optional

# Import basic utility tools
try:
    from radbot.tools.basic.basic_tools import get_current_time, get_weather
except ImportError:
    get_current_time = None
    get_weather = None

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
    
    # Add weather utility
    if get_weather:
        try:
            toolset.append(get_weather)
            logger.info("Added get_weather to utility toolset")
        except Exception as e:
            logger.error(f"Failed to add get_weather: {e}")
    
    # Try to add weather connector if available
    try:
        from radbot.tools.basic.weather_connector import create_weather_tool
        weather_tool = create_weather_tool()
        if weather_tool:
            toolset.append(weather_tool)
            logger.info("Added weather_connector to utility toolset")
    except Exception as e:
        logger.error(f"Failed to add weather_connector: {e}")
    
    return toolset

# Register the toolset with the system
register_toolset(
    name="utility",
    toolset_func=create_utility_toolset,
    description="Agent providing common utility functions",
    allowed_transfers=[]  # Only allows transfer back to main orchestrator
)