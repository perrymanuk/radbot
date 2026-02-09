"""
Basic tools for radbot agents.

This module implements simple tools like time services.
"""
import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from google.adk.tools.tool_context import ToolContext

# Import the tool decorator if available (for ADK >=0.3.0)
try:
    from google.adk.tools.decorators import tool
    HAVE_TOOL_DECORATOR = True
except ImportError:
    HAVE_TOOL_DECORATOR = False
    # Create a no-op decorator for compatibility
    def tool(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


@tool(
    name="get_current_time",
    description="Get the current time for a specified city or timezone",
    parameters={
        "city": {
            "type": "string",
            "description": "The city name (e.g., 'New York', 'London'). Defaults to UTC if not specified.",
            "default": "UTC"
        }
    }
)
def get_current_time(city: str = "UTC", tool_context: Optional[ToolContext] = None) -> str:
    """
    Gets the current time for a specified city or defaults to UTC.

    Use this tool when the user asks for the current time.

    Args:
        city: The city name (e.g., 'New York', 'London'). Defaults to UTC if not specified.
        tool_context: Tool context for accessing session state.

    Returns:
        A string with the current time information or error message.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"get_current_time tool called with city: {city}")
    
    # Example mapping, expand as needed
    tz_map = {
        "new york": "America/New_York",
        "london": "Europe/London",
        "tokyo": "Asia/Tokyo",
        "paris": "Europe/Paris",
        "sydney": "Australia/Sydney",
        "los angeles": "America/Los_Angeles",
        "utc": "UTC"
    }
    tz_identifier = tz_map.get(city.lower())

    if not tz_identifier:
        result = f"Sorry, I don't have timezone information for {city}."
        logger.warning(f"No timezone found for {city}")
        return result

    try:
        tz = ZoneInfo(tz_identifier)
        now = datetime.datetime.now(tz)
        report = f'The current time in {city} is {now.strftime("%Y-%m-%d %H:%M:%S %Z%z")}'
        
        # Optionally save something to state if tool_context is provided
        if tool_context:
            tool_context.state['last_time_city'] = city
        
        logger.info(f"Returning time for {city}: {report}")
        return report
    except Exception as e:
        error_msg = f"An error occurred while fetching the time for {city}: {str(e)}"
        logger.error(f"Error in get_current_time: {error_msg}")
        return error_msg


