"""Core calendar operations for Google Calendar API."""

import datetime
from typing import Any, Dict, List, Optional, Union

from googleapiclient.errors import HttpError

# Type aliases for better readability
CalendarService = Any
TimeValue = Union[datetime.datetime, datetime.date]


def format_time(time_value: TimeValue, timezone: str = "UTC") -> Dict[str, str]:
    """Format datetime or date for Google Calendar API.

    Args:
        time_value: A datetime.datetime or datetime.date object.
        timezone: The timezone to use for dateTime values.

    Returns:
        Dictionary formatted for Google Calendar API with either dateTime or date.
    """
    if isinstance(time_value, datetime.datetime):
        return {"dateTime": time_value.isoformat(), "timeZone": timezone}
    else:  # Assume it's a date
        return {"date": time_value.isoformat()}


def list_events(
    service: CalendarService,
    calendar_id: str = "primary",
    max_results: int = 10,
    query: Optional[str] = None,
    time_min: Optional[datetime.datetime] = None,
    time_max: Optional[datetime.datetime] = None,
) -> List[Dict[str, Any]]:
    """List calendar events with optional filtering.

    Args:
        service: Google Calendar service object.
        calendar_id: Calendar identifier, default is 'primary'.
        max_results: Maximum number of events to return.
        query: Free text search term.
        time_min: Start time for events, defaults to now.
        time_max: End time for events.

    Returns:
        List of event dictionaries.

    Raises:
        HttpError: If the request fails.
    """
    # Get current time in ISO format if not specified
    if time_min is None:
        time_min = datetime.datetime.utcnow()

    time_min_iso = time_min.isoformat() + "Z"  # 'Z' indicates UTC time

    # Build request parameters
    params = {
        "calendarId": calendar_id,
        "timeMin": time_min_iso,
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
    }

    # Add time_max if specified
    if time_max:
        params["timeMax"] = time_max.isoformat() + "Z"

    # Add query if specified (free text search)
    if query:
        params["q"] = query

    try:
        events_result = service.events().list(**params).execute()
        events = events_result.get("items", [])
        return events
    except HttpError as error:
        print(f"Error fetching events: {error}")
        return []


def create_event(
    service: CalendarService,
    summary: str,
    start_time: TimeValue,
    end_time: TimeValue,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    calendar_id: str = "primary",
    timezone: str = "UTC",
) -> Optional[Dict[str, Any]]:
    """Create a calendar event.

    Args:
        service: Google Calendar service object.
        summary: Event title.
        start_time: Start time or date.
        end_time: End time or date.
        description: Optional event description.
        location: Optional location.
        attendees: Optional list of attendee email addresses.
        calendar_id: Calendar identifier, default is 'primary'.
        timezone: Timezone for the event.

    Returns:
        Event dictionary if successful, None otherwise.

    Raises:
        HttpError: If the request fails.
    """
    # Format start and end times
    start = format_time(start_time, timezone)
    end = format_time(end_time, timezone)

    # Build event body
    event_body = {
        "summary": summary,
        "start": start,
        "end": end,
    }

    # Add optional fields if provided
    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location
    if attendees:
        event_body["attendees"] = [{"email": email} for email in attendees]

    try:
        event = (
            service.events()
            .insert(
                calendarId=calendar_id,
                body=event_body,
                sendUpdates="all",  # Notify attendees
            )
            .execute()
        )
        return event
    except HttpError as error:
        print(f"Error creating event: {error}")
        return None


def update_event(
    service: CalendarService,
    event_id: str,
    calendar_id: str = "primary",
    **kwargs: Any,
) -> Optional[Dict[str, Any]]:
    """Update an existing calendar event with provided fields.

    Args:
        service: Google Calendar service object.
        event_id: ID of the event to update.
        calendar_id: Calendar identifier, default is 'primary'.
        **kwargs: Fields to update (summary, description, start, end, location, etc.).

    Returns:
        Updated event dictionary if successful, None otherwise.

    Raises:
        HttpError: If the request fails.
    """
    try:
        # First retrieve the event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        # Get timezone from kwargs or use UTC as default
        timezone = kwargs.pop("timezone", "UTC") if "timezone" in kwargs else "UTC"

        # Update fields that were provided
        for key, value in kwargs.items():
            if key in ["start", "end"]:
                event[key] = format_time(value, timezone)
            else:
                event[key] = value

        # Update the event
        updated_event = (
            service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=event)
            .execute()
        )

        return updated_event
    except HttpError as error:
        print(f"Error updating event: {error}")
        return None


def delete_event(
    service: CalendarService,
    event_id: str,
    calendar_id: str = "primary",
) -> bool:
    """Delete a calendar event.

    Args:
        service: Google Calendar service object.
        event_id: ID of the event to delete.
        calendar_id: Calendar identifier, default is 'primary'.

    Returns:
        True if successful, False otherwise.

    Raises:
        HttpError: If the request fails.
    """
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True
    except HttpError as error:
        print(f"Error deleting event: {error}")
        return False


def get_calendar_availability(
    service: CalendarService,
    calendar_ids: List[str],
    time_min: datetime.datetime,
    time_max: datetime.datetime,
) -> Optional[Dict[str, Any]]:
    """Get free/busy information for calendars.

    Args:
        service: Google Calendar service object.
        calendar_ids: List of calendar identifiers.
        time_min: Start time.
        time_max: End time.

    Returns:
        Free/busy information if successful, None otherwise.

    Raises:
        HttpError: If the request fails.
    """
    body = {
        "timeMin": time_min.isoformat() + "Z",
        "timeMax": time_max.isoformat() + "Z",
        "items": [{"id": calendar_id} for calendar_id in calendar_ids],
    }

    try:
        freebusy = service.freebusy().query(body=body).execute()
        return freebusy
    except HttpError as error:
        print(f"Error fetching free/busy info: {error}")
        return None
