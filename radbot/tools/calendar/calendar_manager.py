"""Calendar Manager class for Google Calendar integration."""

import datetime
import logging
import os.path
from typing import Any, Dict, List, Optional, Union

from radbot.tools.calendar.calendar_auth import (
    get_calendar_service,
    get_workspace_calendar_service,
    validate_calendar_access,
)
from radbot.tools.calendar.calendar_operations import (
    check_calendar_access,
    create_event,
    delete_event,
    get_calendar_availability,
    list_events,
    update_event,
)

# Set up logging
logger = logging.getLogger(__name__)

# Type aliases
TimeValue = Union[datetime.datetime, datetime.date]


class CalendarManager:
    """Manages Google Calendar operations for radbot."""

    def __init__(self, service_account_path: Optional[str] = None):
        """Initialize CalendarManager.

        Args:
            service_account_path: Path to the service account JSON file. If None,
                                 uses GOOGLE_CREDENTIALS_PATH environment variable.
        """
        self.service_account_path = service_account_path
        self.personal_service = None
        self.workspace_service = None
        self.workspace_email = None

    def authenticate_personal(self) -> bool:
        """Authenticate with Google Calendar using service account.

        Returns:
            True if authentication was successful, False otherwise.
        """
        try:
            from radbot.tools.calendar.calendar_auth import (
                _get_service_account_json,
                _get_service_account_path,
            )

            # Get the service account path from init or DB config
            credentials_path = self.service_account_path or _get_service_account_path()

            # Check if using JSON from credential store, skip path check in that case
            if not _get_service_account_json():
                if credentials_path and not os.path.exists(credentials_path):
                    logger.error(
                        f"Service account file not found at {credentials_path}"
                    )
                    return False

            # Try to authenticate with service account
            logger.info("Authenticating with Google Calendar using service account")
            self.personal_service = get_calendar_service(
                force_new=True,
                service_account_path=credentials_path,
            )

            # Test the service with a simple API call
            if self.personal_service:
                try:
                    # Try to get the primary calendar to confirm authentication worked
                    primary_calendar = (
                        self.personal_service.calendars()
                        .get(calendarId="primary")
                        .execute()
                    )
                    logger.info(
                        f"Successfully authenticated with Google Calendar as: {primary_calendar.get('summary', 'Unknown')}"
                    )
                    return True
                except Exception as e:
                    logger.error(f"Failed to access primary calendar: {e}")
                    return False

            return False
        except Exception as e:
            logger.error(f"Google Calendar authentication failed: {e}")
            return False

    def authenticate_workspace(self, email: str) -> bool:
        """Authenticate with Google Workspace account using service account impersonation.

        Args:
            email: The user email to impersonate.

        Returns:
            True if authentication was successful, False otherwise.
        """
        try:
            from radbot.tools.calendar.calendar_auth import (
                _get_service_account_json,
                _get_service_account_path,
            )

            # Get the service account path from init or DB config
            credentials_path = self.service_account_path or _get_service_account_path()

            # Check if using JSON from credential store, skip path check in that case
            if not _get_service_account_json():
                if credentials_path and not os.path.exists(credentials_path):
                    logger.error(
                        f"Service account file not found at {credentials_path}"
                    )
                    return False

            logger.info(f"Authenticating with Google Workspace as {email}")
            self.workspace_email = email
            self.workspace_service = get_workspace_calendar_service(
                user_email=email, service_account_path=credentials_path, force_new=True
            )

            # Test the service with a simple API call
            if self.workspace_service:
                try:
                    # Try to get the primary calendar to confirm authentication worked
                    primary_calendar = (
                        self.workspace_service.calendars()
                        .get(calendarId="primary")
                        .execute()
                    )
                    logger.info(
                        f"Successfully authenticated with Google Workspace as: {email}"
                    )
                    return True
                except Exception as e:
                    logger.error(f"Failed to access primary calendar as {email}: {e}")
                    return False

            return False
        except Exception as e:
            logger.error(f"Workspace calendar authentication failed: {e}")
            return False

    def list_upcoming_events(
        self,
        calendar_id: str = "primary",
        max_results: int = 10,
        query: Optional[str] = None,
        time_min: Optional[datetime.datetime] = None,
        time_max: Optional[datetime.datetime] = None,
        is_workspace: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """List upcoming events from selected calendar.

        Args:
            calendar_id: Calendar identifier, default is 'primary'.
            max_results: Maximum number of events to return.
            query: Free text search term.
            time_min: Start time for events, defaults to now.
            time_max: End time for events.
            is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

        Returns:
            List of event dictionaries or error dictionary.
        """
        service = self.workspace_service if is_workspace else self.personal_service
        if not service:
            return {"error": "Not authenticated"}

        return list_events(
            service,
            calendar_id=calendar_id,
            max_results=max_results,
            query=query,
            time_min=time_min,
            time_max=time_max,
        )

    def create_new_event(
        self,
        summary: str,
        start_time: TimeValue,
        end_time: TimeValue,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        calendar_id: str = "primary",
        timezone: str = "UTC",
        is_workspace: bool = False,
    ) -> Union[Dict[str, Any], Dict[str, str]]:
        """Create a new event in selected calendar.

        Args:
            summary: Event title.
            start_time: Start time or date.
            end_time: End time or date.
            description: Optional event description.
            location: Optional location.
            attendees: Optional list of attendee email addresses.
            calendar_id: Calendar identifier, default is 'primary'.
            timezone: Timezone for the event.
            is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

        Returns:
            Event dictionary if successful, error dictionary otherwise.
        """
        service = self.workspace_service if is_workspace else self.personal_service
        if not service:
            return {"error": "Not authenticated"}

        event = create_event(
            service,
            summary,
            start_time,
            end_time,
            description=description,
            location=location,
            attendees=attendees,
            calendar_id=calendar_id,
            timezone=timezone,
        )

        if event:
            return event
        else:
            return {"error": "Failed to create event"}

    def update_existing_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        is_workspace: bool = False,
        **kwargs: Any,
    ) -> Union[Dict[str, Any], Dict[str, str]]:
        """Update an existing event.

        Args:
            event_id: ID of the event to update.
            calendar_id: Calendar identifier, default is 'primary'.
            is_workspace: Whether to use workspace calendar (True) or personal calendar (False).
            **kwargs: Fields to update (summary, description, start, end, location, etc.).

        Returns:
            Updated event dictionary if successful, error dictionary otherwise.
        """
        service = self.workspace_service if is_workspace else self.personal_service
        if not service:
            return {"error": "Not authenticated"}

        updated_event = update_event(
            service, event_id, calendar_id=calendar_id, **kwargs
        )

        if updated_event:
            return updated_event
        else:
            return {"error": "Failed to update event"}

    def delete_existing_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        is_workspace: bool = False,
    ) -> Dict[str, Union[bool, str]]:
        """Delete an existing event.

        Args:
            event_id: ID of the event to delete.
            calendar_id: Calendar identifier, default is 'primary'.
            is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

        Returns:
            Success dictionary if successful, error dictionary otherwise.
        """
        service = self.workspace_service if is_workspace else self.personal_service
        if not service:
            return {"error": "Not authenticated"}

        success = delete_event(service, event_id, calendar_id=calendar_id)

        if success:
            return {"success": True}
        else:
            return {"error": "Failed to delete event"}

    def get_calendar_busy_times(
        self,
        calendar_ids: List[str],
        time_min: datetime.datetime,
        time_max: datetime.datetime,
        is_workspace: bool = False,
    ) -> Union[Dict[str, Any], Dict[str, str]]:
        """Get busy time slots for calendars.

        Args:
            calendar_ids: List of calendar identifiers.
            time_min: Start time.
            time_max: End time.
            is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

        Returns:
            Free/busy information if successful, error dictionary otherwise.
        """
        service = self.workspace_service if is_workspace else self.personal_service
        if not service:
            return {"error": "Not authenticated"}

        availability = get_calendar_availability(
            service,
            calendar_ids,
            time_min,
            time_max,
        )

        if availability:
            return availability
        else:
            return {"error": "Failed to get calendar availability"}

    def handle_calendar_request(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        is_workspace: bool = False,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Process calendar requests with appropriate error handling.

        Args:
            action: The action to perform.
            params: Parameters for the action.
            is_workspace: Whether to use workspace calendar (True) or personal calendar (False).

        Returns:
            Result of the action or error dictionary.
        """
        if params is None:
            params = {}

        try:
            if action == "list_events":
                return self.list_upcoming_events(is_workspace=is_workspace, **params)
            elif action == "create_event":
                required = ["summary", "start_time", "end_time"]
                if not all(k in params for k in required):
                    return {"error": "Missing required parameters"}
                return self.create_new_event(is_workspace=is_workspace, **params)
            elif action == "update_event":
                if "event_id" not in params:
                    return {"error": "Missing event_id parameter"}
                event_id = params.pop("event_id")
                return self.update_existing_event(
                    event_id, is_workspace=is_workspace, **params
                )
            elif action == "delete_event":
                if "event_id" not in params:
                    return {"error": "Missing event_id parameter"}
                return self.delete_existing_event(
                    params["event_id"], is_workspace=is_workspace
                )
            elif action == "get_availability":
                required = ["calendar_ids", "time_min", "time_max"]
                if not all(k in params for k in required):
                    return {"error": "Missing required parameters"}
                return self.get_calendar_busy_times(
                    params["calendar_ids"],
                    params["time_min"],
                    params["time_max"],
                    is_workspace=is_workspace,
                )
            else:
                return {"error": "Unknown action"}
        except Exception as e:
            return {"error": str(e)}
