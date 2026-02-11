"""Calendar toolset for specialized agents.

This module provides tools for interacting with calendar services,
managing events, and scheduling.
"""

import logging
from typing import Any, List, Optional

# Import calendar tools
try:
    from radbot.tools.calendar.calendar_tools import (
        check_calendar_availability_wrapper,
        create_calendar_event_wrapper,
        delete_calendar_event_wrapper,
        list_calendar_events_wrapper,
        update_calendar_event_wrapper,
    )
except ImportError:
    # Define placeholders if not available
    list_calendar_events_wrapper = None
    create_calendar_event_wrapper = None
    update_calendar_event_wrapper = None
    delete_calendar_event_wrapper = None
    check_calendar_availability_wrapper = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)


def create_calendar_toolset() -> List[Any]:
    """Create the set of tools for the calendar specialized agent.

    Returns:
        List of tools for calendar operations and scheduling
    """
    toolset = []

    # Add calendar event management tools
    calendar_funcs = [
        (list_calendar_events_wrapper, "list_calendar_events_wrapper"),
        (create_calendar_event_wrapper, "create_calendar_event_wrapper"),
        (update_calendar_event_wrapper, "update_calendar_event_wrapper"),
        (delete_calendar_event_wrapper, "delete_calendar_event_wrapper"),
        (check_calendar_availability_wrapper, "check_calendar_availability_wrapper"),
    ]

    for func, name in calendar_funcs:
        if func:
            try:
                toolset.append(func)
                logger.info(f"Added {name} to calendar toolset")
            except Exception as e:
                logger.error(f"Failed to add {name}: {e}")

    return toolset


# Register the toolset with the system
register_toolset(
    name="calendar",
    toolset_func=create_calendar_toolset,
    description="Agent specialized in calendar operations and scheduling",
    allowed_transfers=[],  # Only allows transfer back to main orchestrator
)
