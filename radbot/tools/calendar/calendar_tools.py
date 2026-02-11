"""Google Calendar function tools for ADK integration."""

import datetime
from typing import Any, Dict, List, Optional, Union

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field

from radbot.tools.calendar.calendar_auth import CALENDAR_TIMEZONE
from radbot.tools.calendar.calendar_manager import CalendarManager


# Response models
class CalendarEvent(BaseModel):
    """Model for a calendar event."""

    id: str = Field(description="Event identifier")
    summary: str = Field(description="Event title")
    description: Optional[str] = Field(None, description="Event description")
    start: Dict[str, Any] = Field(description="Start time")
    end: Dict[str, Any] = Field(description="End time")
    location: Optional[str] = Field(None, description="Event location")
    attendees: Optional[List[Dict[str, Any]]] = Field(
        None, description="List of attendees"
    )
    htmlLink: Optional[str] = Field(None, description="HTML link to the event")


class ErrorResponse(BaseModel):
    """Model for error responses."""

    error: str = Field(description="Error message")


class ListEventsParameters(BaseModel):
    """Parameters for list_calendar_events function."""

    calendar_id: str = Field(
        default="primary",
        description="Calendar identifier, default is 'primary'",
    )
    max_results: int = Field(
        default=10,
        description="Maximum number of events to return",
        ge=1,
        le=100,
    )
    query: Optional[str] = Field(
        default=None,
        description="Free text search term",
    )
    days_ahead: int = Field(
        default=7,
        description="Number of days ahead to search for events",
        ge=1,
        le=365,
    )
    is_workspace: bool = Field(
        default=False,
        description="Whether to use workspace calendar (True) or personal calendar (False)",
    )


class CreateEventParameters(BaseModel):
    """Parameters for create_calendar_event function."""

    summary: str = Field(
        description="Event title",
    )
    start_time: str = Field(
        description=(
            "Start time in ISO format (YYYY-MM-DDTHH:MM:SS) for a datetime, "
            "or (YYYY-MM-DD) for an all-day event"
        ),
    )
    end_time: str = Field(
        description=(
            "End time in ISO format (YYYY-MM-DDTHH:MM:SS) for a datetime, "
            "or (YYYY-MM-DD) for an all-day event"
        ),
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional event description",
    )
    location: Optional[str] = Field(
        default=None,
        description="Optional location",
    )
    attendees: Optional[List[str]] = Field(
        default=None,
        description="Optional list of attendee email addresses",
    )
    calendar_id: str = Field(
        default="primary",
        description="Calendar identifier, default is 'primary'",
    )
    timezone: str = Field(
        default=CALENDAR_TIMEZONE,
        description="Timezone for the event",
    )
    is_workspace: bool = Field(
        default=False,
        description="Whether to use workspace calendar (True) or personal calendar (False)",
    )


class UpdateEventParameters(BaseModel):
    """Parameters for update_calendar_event function."""

    event_id: str = Field(
        description="ID of the event to update",
    )
    summary: Optional[str] = Field(
        default=None,
        description="New event title",
    )
    start_time: Optional[str] = Field(
        default=None,
        description=(
            "New start time in ISO format (YYYY-MM-DDTHH:MM:SS) for a datetime, "
            "or (YYYY-MM-DD) for an all-day event"
        ),
    )
    end_time: Optional[str] = Field(
        default=None,
        description=(
            "New end time in ISO format (YYYY-MM-DDTHH:MM:SS) for a datetime, "
            "or (YYYY-MM-DD) for an all-day event"
        ),
    )
    description: Optional[str] = Field(
        default=None,
        description="New event description",
    )
    location: Optional[str] = Field(
        default=None,
        description="New location",
    )
    attendees: Optional[List[str]] = Field(
        default=None,
        description="New list of attendee email addresses",
    )
    calendar_id: str = Field(
        default="primary",
        description="Calendar identifier, default is 'primary'",
    )
    timezone: str = Field(
        default=CALENDAR_TIMEZONE,
        description="Timezone for the event",
    )
    is_workspace: bool = Field(
        default=False,
        description="Whether to use workspace calendar (True) or personal calendar (False)",
    )


class DeleteEventParameters(BaseModel):
    """Parameters for delete_calendar_event function."""

    event_id: str = Field(
        description="ID of the event to delete",
    )
    calendar_id: str = Field(
        default="primary",
        description="Calendar identifier, default is 'primary'",
    )
    is_workspace: bool = Field(
        default=False,
        description="Whether to use workspace calendar (True) or personal calendar (False)",
    )


class AvailabilityParameters(BaseModel):
    """Parameters for check_calendar_availability function."""

    calendar_ids: List[str] = Field(
        description="List of calendar identifiers",
    )
    days_ahead: int = Field(
        default=7,
        description="Number of days ahead to check availability",
        ge=1,
        le=60,
    )
    is_workspace: bool = Field(
        default=False,
        description="Whether to use workspace calendar (True) or personal calendar (False)",
    )


# Calendar manager singleton
_calendar_manager = None


def get_calendar_manager() -> CalendarManager:
    """Get the calendar manager singleton.

    Returns:
        CalendarManager instance.
    """
    global _calendar_manager
    if _calendar_manager is None:
        _calendar_manager = CalendarManager()
        # Authenticate with personal account
        auth_success = _calendar_manager.authenticate_personal()

        if not auth_success:
            print(
                "WARNING: Calendar authentication failed. Calendar operations will not work."
            )
            # Still return the manager - operations will return appropriate error messages

    return _calendar_manager


def parse_time(time_str: str) -> Union[datetime.datetime, datetime.date]:
    """Parse a time string into a datetime or date object.

    Args:
        time_str: Time string in ISO format.

    Returns:
        datetime.datetime or datetime.date object.

    Raises:
        ValueError: If the time string is invalid.
    """
    try:
        if "T" in time_str:
            return datetime.datetime.fromisoformat(time_str)
        else:
            return datetime.date.fromisoformat(time_str)
    except ValueError:
        raise ValueError(f"Invalid time format: {time_str}. Use ISO format.")


def list_calendar_events(
    manager: Optional[CalendarManager] = None,
    calendar_id: str = "primary",
    max_results: int = 10,
    query: Optional[str] = None,
    days_ahead: int = 7,
    is_workspace: bool = False,
) -> List[Dict[str, Any]]:
    """List upcoming events from Google Calendar.

    Args:
        manager: CalendarManager instance. If None, uses the singleton.
        calendar_id: Calendar identifier, default is 'primary'.
        max_results: Maximum number of events to return.
        query: Free text search term.
        days_ahead: Number of days ahead to search for events.
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        List of event dictionaries.
    """
    if manager is None:
        manager = get_calendar_manager()

    time_min = datetime.datetime.utcnow()
    time_max = time_min + datetime.timedelta(days=days_ahead)

    result = manager.list_upcoming_events(
        calendar_id=calendar_id,
        max_results=max_results,
        query=query,
        time_min=time_min,
        time_max=time_max,
        is_workspace=is_workspace,
    )

    # If result is an error dictionary, return an empty list
    if isinstance(result, dict) and "error" in result:
        print(f"Error listing events: {result['error']}")
        return []

    return result


def create_calendar_event(
    manager: Optional[CalendarManager] = None,
    summary: str = "",
    start_time: str = "",
    end_time: str = "",
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    calendar_id: str = "primary",
    timezone: str = CALENDAR_TIMEZONE,
    is_workspace: bool = False,
) -> Dict[str, Any]:
    """Create a new event in Google Calendar.

    Args:
        manager: CalendarManager instance. If None, uses the singleton.
        summary: Event title.
        start_time: Start time in ISO format.
        end_time: End time in ISO format.
        description: Optional event description.
        location: Optional location.
        attendees: Optional list of attendee email addresses.
        calendar_id: Calendar identifier, default is 'primary'.
        timezone: Timezone for the event.
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        Event dictionary if successful, error dictionary otherwise.
    """
    if manager is None:
        manager = get_calendar_manager()

    # Parse start and end times
    start = parse_time(start_time)
    end = parse_time(end_time)

    return manager.create_new_event(
        summary=summary,
        start_time=start,
        end_time=end,
        description=description,
        location=location,
        attendees=attendees,
        calendar_id=calendar_id,
        timezone=timezone,
        is_workspace=is_workspace,
    )


def update_calendar_event(
    manager: Optional[CalendarManager] = None,
    event_id: str = "",
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    calendar_id: str = "primary",
    timezone: str = CALENDAR_TIMEZONE,
    is_workspace: bool = False,
) -> Dict[str, Any]:
    """Update an existing event in Google Calendar.

    Args:
        manager: CalendarManager instance. If None, uses the singleton.
        event_id: ID of the event to update.
        summary: New event title.
        start_time: New start time in ISO format.
        end_time: New end time in ISO format.
        description: New event description.
        location: New location.
        attendees: New list of attendee email addresses.
        calendar_id: Calendar identifier, default is 'primary'.
        timezone: Timezone for the event.
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        Updated event dictionary if successful, error dictionary otherwise.
    """
    if manager is None:
        manager = get_calendar_manager()

    # Build kwargs with non-None values
    kwargs = {}

    if summary is not None:
        kwargs["summary"] = summary

    if start_time is not None:
        kwargs["start"] = parse_time(start_time)

    if end_time is not None:
        kwargs["end"] = parse_time(end_time)

    if description is not None:
        kwargs["description"] = description

    if location is not None:
        kwargs["location"] = location

    if attendees is not None:
        kwargs["attendees"] = [{"email": email} for email in attendees]

    # Add timezone to kwargs if start or end time is provided
    if (start_time is not None or end_time is not None) and timezone:
        kwargs["timezone"] = timezone

    return manager.update_existing_event(
        event_id=event_id, calendar_id=calendar_id, is_workspace=is_workspace, **kwargs
    )


def delete_calendar_event(
    manager: Optional[CalendarManager] = None,
    event_id: str = "",
    calendar_id: str = "primary",
    is_workspace: bool = False,
) -> Dict[str, Union[bool, str]]:
    """Delete an event from Google Calendar.

    Args:
        manager: CalendarManager instance. If None, uses the singleton.
        event_id: ID of the event to delete.
        calendar_id: Calendar identifier, default is 'primary'.
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        Success dictionary if successful, error dictionary otherwise.
    """
    if manager is None:
        manager = get_calendar_manager()

    return manager.delete_existing_event(
        event_id=event_id,
        calendar_id=calendar_id,
        is_workspace=is_workspace,
    )


def check_calendar_availability(
    manager: Optional[CalendarManager] = None,
    calendar_ids: Optional[List[str]] = None,
    days_ahead: int = 7,
    is_workspace: bool = False,
) -> Dict[str, Any]:
    """Check availability for Google Calendars.

    Args:
        manager: CalendarManager instance. If None, uses the singleton.
        calendar_ids: List of calendar identifiers.
        days_ahead: Number of days ahead to check availability.
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        Free/busy information if successful, error dictionary otherwise.
    """
    if manager is None:
        manager = get_calendar_manager()

    # Use environment variable for calendar_id if not specified
    from radbot.tools.calendar.calendar_auth import (
        CALENDAR_ID as DEFAULT_ENV_CALENDAR_ID,
    )

    if calendar_ids is None:
        calendar_ids = [DEFAULT_ENV_CALENDAR_ID]

    time_min = datetime.datetime.utcnow()
    time_max = time_min + datetime.timedelta(days=days_ahead)

    return manager.get_calendar_busy_times(
        calendar_ids=calendar_ids,
        time_min=time_min,
        time_max=time_max,
        is_workspace=is_workspace,
    )


# Create wrapper functions without manager parameter for ADK function tools
def list_calendar_events_wrapper(
    calendar_id: Optional[str] = None,
    max_results: int = 10,
    query: Optional[str] = None,
    days_ahead: int = 7,
    is_workspace: bool = False,
) -> List[Dict[str, Any]]:
    """List upcoming events from Google Calendar.

    Args:
        calendar_id: Calendar identifier. If None, uses the environment variable GOOGLE_CALENDAR_ID.
        max_results: Maximum number of events to return.
        query: Free text search term.
        days_ahead: Number of days ahead to search for events.
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        List of event dictionaries.
    """
    try:
        # Use environment variable for calendar_id if not specified
        from radbot.tools.calendar.calendar_auth import (
            CALENDAR_ID as DEFAULT_ENV_CALENDAR_ID,
        )

        # If calendar_id is None, use the environment variable
        if calendar_id is None:
            calendar_id = DEFAULT_ENV_CALENDAR_ID

        result = list_calendar_events(
            calendar_id=calendar_id,
            max_results=max_results,
            query=query,
            days_ahead=days_ahead,
            is_workspace=is_workspace,
        )

        # If the result is a dictionary with an 'error' key, it's an error
        if isinstance(result, dict) and "error" in result:
            print(f"Calendar API error: {result.get('error', 'Unknown error')}")
            return []  # Return empty list instead of raising exception

        # Ensure we always return a list
        if not isinstance(result, list):
            return []

        from radbot.tools.shared.sanitize import sanitize_external_content

        return sanitize_external_content(result, source="calendar")
    except Exception as e:
        print(
            f"Exception while listing calendar events: {str(e)}. Please check authentication credentials."
        )
        return []  # Return empty list instead of raising exception


def create_calendar_event_wrapper(
    summary: str,
    start_time: str,
    end_time: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    calendar_id: Optional[str] = None,
    timezone: str = CALENDAR_TIMEZONE,
    is_workspace: bool = False,
) -> Dict[str, Any]:
    """Create a new event in Google Calendar.

    Args:
        summary: Event title.
        start_time: Start time in ISO format.
        end_time: End time in ISO format.
        description: Optional event description.
        location: Optional location.
        attendees: Optional list of attendee email addresses.
        calendar_id: Calendar identifier, default is 'primary'.
        timezone: Timezone for the event.
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        Event dictionary if successful, or a dictionary with error information.
    """
    try:
        # Parse time inputs to check for format errors
        try:
            parsed_start = parse_time(start_time)
            parsed_end = parse_time(end_time)
        except ValueError as e:
            error_message = f"Invalid time format: {str(e)}"
            print(error_message)
            return {"status": "error", "message": error_message}

        # Use environment variable for calendar_id if not specified
        from radbot.tools.calendar.calendar_auth import (
            CALENDAR_ID as DEFAULT_ENV_CALENDAR_ID,
        )

        # If calendar_id is None, use the environment variable
        if calendar_id is None:
            calendar_id = DEFAULT_ENV_CALENDAR_ID

        result = create_calendar_event(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees,
            calendar_id=calendar_id,
            timezone=timezone,
            is_workspace=is_workspace,
        )

        if result is None:
            error_message = (
                "Failed to create event. Check calendar authentication and permissions."
            )
            print(error_message)
            return {"status": "error", "message": error_message}
        elif isinstance(result, dict) and "error" in result:
            error_message = (
                f"Failed to create event: {result.get('error', 'Unknown error')}"
            )
            print(error_message)
            return {"status": "error", "message": error_message}

        return result
    except Exception as e:
        error_message = f"Exception while creating calendar event: {str(e)}. Please check authentication credentials."
        print(error_message)
        return {"status": "error", "message": error_message}


def update_calendar_event_wrapper(
    event_id: str,
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    calendar_id: Optional[str] = None,
    timezone: str = CALENDAR_TIMEZONE,
    is_workspace: bool = False,
) -> Dict[str, Any]:
    """Update an existing event in Google Calendar.

    Args:
        event_id: ID of the event to update.
        summary: New event title.
        start_time: New start time in ISO format.
        end_time: New end time in ISO format.
        description: New event description.
        location: New location.
        attendees: New list of attendee email addresses.
        calendar_id: Calendar identifier, default is 'primary'.
        timezone: Timezone for the event (default: UTC).
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        Updated event dictionary if successful, or a dictionary with error information.
    """
    try:
        # Parse time inputs to check for format errors if provided
        if start_time:
            try:
                parsed_start = parse_time(start_time)
            except ValueError as e:
                error_message = f"Invalid start_time format: {str(e)}"
                print(error_message)
                return {"status": "error", "message": error_message}

        if end_time:
            try:
                parsed_end = parse_time(end_time)
            except ValueError as e:
                error_message = f"Invalid end_time format: {str(e)}"
                print(error_message)
                return {"status": "error", "message": error_message}

        # Use environment variable for calendar_id if not specified
        from radbot.tools.calendar.calendar_auth import (
            CALENDAR_ID as DEFAULT_ENV_CALENDAR_ID,
        )

        # If calendar_id is None, use the environment variable
        if calendar_id is None:
            calendar_id = DEFAULT_ENV_CALENDAR_ID

        result = update_calendar_event(
            event_id=event_id,
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees,
            calendar_id=calendar_id,
            timezone=timezone,
            is_workspace=is_workspace,
        )

        if result is None:
            error_message = f"Failed to update event {event_id}. Check calendar authentication and permissions."
            print(error_message)
            return {"status": "error", "message": error_message}
        elif isinstance(result, dict) and "error" in result:
            error_message = (
                f"Failed to update event: {result.get('error', 'Unknown error')}"
            )
            print(error_message)
            return {"status": "error", "message": error_message}

        return result
    except Exception as e:
        error_message = f"Exception while updating calendar event: {str(e)}. Please check authentication credentials."
        print(error_message)
        return {"status": "error", "message": error_message}


def delete_calendar_event_wrapper(
    event_id: str,
    calendar_id: Optional[str] = None,
    is_workspace: bool = False,
) -> Dict[str, str]:
    """Delete an event from Google Calendar.

    Args:
        event_id: ID of the event to delete.
        calendar_id: Calendar identifier, default is 'primary'.
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        Dictionary with success message or error information.
    """
    try:
        if not event_id:
            error_message = "Event ID is required to delete an event"
            print(error_message)
            return {"status": "error", "message": error_message}

        # Use environment variable for calendar_id if not specified
        from radbot.tools.calendar.calendar_auth import (
            CALENDAR_ID as DEFAULT_ENV_CALENDAR_ID,
        )

        # If calendar_id is None, use the environment variable
        if calendar_id is None:
            calendar_id = DEFAULT_ENV_CALENDAR_ID

        result = delete_calendar_event(
            event_id=event_id, calendar_id=calendar_id, is_workspace=is_workspace
        )

        if isinstance(result, dict):
            if "success" in result and result["success"]:
                return {
                    "status": "success",
                    "message": f"Event {event_id} deleted successfully",
                }
            elif "error" in result:
                error_message = (
                    f"Failed to delete event: {result.get('error', 'Unknown error')}"
                )
                print(error_message)
                return {"status": "error", "message": error_message}

        # If it's not a dict or doesn't have success/error keys
        if result:
            return {
                "status": "success",
                "message": f"Event {event_id} deleted successfully",
            }
        else:
            error_message = f"Failed to delete event {event_id}. Check calendar authentication and permissions."
            print(error_message)
            return {"status": "error", "message": error_message}
    except Exception as e:
        error_message = f"Exception while deleting calendar event: {str(e)}. Please check authentication credentials."
        print(error_message)
        return {"status": "error", "message": error_message}


def check_calendar_availability_wrapper(
    calendar_ids: Optional[List[str]] = None,
    days_ahead: int = 7,
    is_workspace: bool = False,
) -> Dict[str, Any]:
    """Check availability for Google Calendars.

    Args:
        calendar_ids: List of calendar identifiers.
        days_ahead: Number of days ahead to check availability.
        is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

    Returns:
        Free/busy information if successful, or a dictionary with error information.
    """
    try:
        if days_ahead < 1:
            error_message = "days_ahead must be a positive integer"
            print(error_message)
            return {"status": "error", "message": error_message}

        result = check_calendar_availability(
            calendar_ids=calendar_ids, days_ahead=days_ahead, is_workspace=is_workspace
        )

        if isinstance(result, dict) and "error" in result:
            error_message = f"Failed to check calendar availability: {result.get('error', 'Unknown error')}"
            print(error_message)
            return {"status": "error", "message": error_message}

        return result
    except Exception as e:
        error_message = f"Exception while checking calendar availability: {str(e)}. Please check authentication credentials."
        print(error_message)
        return {"status": "error", "message": error_message, "calendars": {}}


# Function tool definitions with wrapper functions
list_calendar_events_tool = FunctionTool(list_calendar_events_wrapper)
create_calendar_event_tool = FunctionTool(create_calendar_event_wrapper)
update_calendar_event_tool = FunctionTool(update_calendar_event_wrapper)
delete_calendar_event_tool = FunctionTool(delete_calendar_event_wrapper)
check_calendar_availability_tool = FunctionTool(check_calendar_availability_wrapper)
