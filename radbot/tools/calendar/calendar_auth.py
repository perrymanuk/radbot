"""Authentication module for Google Calendar API.

Supports (in order):
1. Application Default Credentials (ADC) - from gcloud auth application-default login
2. Service account credentials (existing behavior)
"""

import json
import logging
import os.path
import random
import socket
import time
from typing import Any, Dict, List, Optional, Tuple

import google.auth
import httplib2
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Set up logging
logger = logging.getLogger(__name__)

# Define scope constants
READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
FULL_ACCESS_SCOPE = "https://www.googleapis.com/auth/calendar"
FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"

# Default locations for credentials
DEFAULT_SERVICE_ACCOUNT_PATH = os.path.join(
    os.path.dirname(__file__), "credentials", "service-account.json"
)

# Try to get service account path from environment variable first
CALENDAR_SERVICE_ACCOUNT_PATH = os.environ.get(
    "GOOGLE_CALENDAR_SERVICE_ACCOUNT_FILE", DEFAULT_SERVICE_ACCOUNT_PATH
)

# Default calendar ID and environment variable configuration
DEFAULT_CALENDAR_ID = "primary"
DEFAULT_TIMEZONE = "UTC"

# Get calendar ID from environment variable or use default
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", DEFAULT_CALENDAR_ID)
# Get default timezone from environment variable or use default
CALENDAR_TIMEZONE = os.environ.get("GOOGLE_CALENDAR_TIMEZONE", DEFAULT_TIMEZONE)

# Global service instance
_calendar_service = None
_workspace_services = {}


# Decorator for retrying API calls with exponential backoff
def retry_calendar_api(max_attempts=5, base_wait=2):
    """Decorator that provides retry logic with exponential backoff for calendar API calls."""

    def decorator(func):
        @retry(
            reraise=True,
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=base_wait, min=1, max=60),
            retry=retry_if_exception_type(
                (
                    socket.timeout,
                    ConnectionError,
                    httplib2.HttpLib2Error,
                    TimeoutError,
                    OSError,
                    IOError,
                )
            ),
            before_sleep=lambda retry_state: logger.info(
                f"Retrying {func.__name__} after error. "
                f"Attempt {retry_state.attempt_number}/{max_attempts}. "
                f"Waiting {retry_state.next_action.sleep} seconds."
            ),
        )
        def wrapper(*args, **kwargs):
            try:
                # Add jitter to avoid thundering herd problem
                jitter = random.uniform(0.1, 1.0)
                time.sleep(jitter)

                return func(*args, **kwargs)

            except (socket.timeout, ConnectionError, httplib2.HttpLib2Error) as e:
                logger.warning(
                    f"Network error in {func.__name__}: {str(e)}. Retrying..."
                )
                # Force new service on connection errors
                get_calendar_service(force_new=True)
                raise

            except Exception as e:
                if "SSL" in str(e):
                    logger.error(
                        f"SSL error in {func.__name__}: {str(e)}. Refreshing connection..."
                    )
                    # Force new service on SSL errors
                    get_calendar_service(force_new=True)
                raise

        return wrapper

    return decorator


def get_calendar_service(
    force_new: bool = False,
    service_account_path: str = CALENDAR_SERVICE_ACCOUNT_PATH,
    scopes: Optional[List[str]] = None,
) -> Any:
    """
    Create and return an authenticated Google Calendar API service with retry logic.

    Args:
        force_new: If True, create a new service instance even if one exists
        service_account_path: Path to the service account credentials JSON file
        scopes: List of authorization scopes to request

    Returns:
        A Google Calendar API service object with authentication set up.

    Raises:
        FileNotFoundError: If service account file is not found.
        ValueError: If credentials_path is None.
        Exception: If authentication fails.
    """
    global _calendar_service

    # Return cached service if available and not forced to create new
    if _calendar_service is not None and not force_new:
        return _calendar_service

    if scopes is None:
        scopes = [FULL_ACCESS_SCOPE]

    # 0. Try credential store for OAuth token or service account JSON
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            # Try OAuth token from credential store
            token_json = store.get("calendar_token")
            if token_json:
                from google.auth.transport.requests import Request as AuthRequest
                from google.oauth2.credentials import Credentials as OAuthCredentials

                token_info = json.loads(token_json)
                creds = OAuthCredentials.from_authorized_user_info(
                    token_info, scopes
                )
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(AuthRequest())
                    # Write refreshed token back to store, preserving
                    # fields that creds.to_json() drops (e.g. quota_project_id)
                    refreshed = json.loads(creds.to_json())
                    for key in ("quota_project_id",):
                        if key in token_info and key not in refreshed:
                            refreshed[key] = token_info[key]
                    store.set(
                        "calendar_token", json.dumps(refreshed), credential_type="oauth_token"
                    )
                if creds and creds.valid:
                    _calendar_service = build("calendar", "v3", credentials=creds)
                    logger.info("Calendar: Using OAuth token from credential store")
                    return _calendar_service

            # Try service account JSON from credential store
            sa_json = store.get("calendar_service_account")
            if sa_json:
                sa_info = json.loads(sa_json)
                sa_creds = service_account.Credentials.from_service_account_info(
                    sa_info, scopes=scopes
                )
                impersonation_email = os.environ.get("GOOGLE_IMPERSONATION_EMAIL")
                if impersonation_email:
                    sa_creds = sa_creds.with_subject(impersonation_email)
                _calendar_service = build("calendar", "v3", credentials=sa_creds)
                logger.info("Calendar: Using service account from credential store")
                return _calendar_service
    except Exception as e:
        logger.error(f"Calendar credential store lookup failed: {e}", exc_info=True)

    # 1. Try saved OAuth token first (from python -m radbot.tools.calendar.setup)
    try:
        from radbot.tools.calendar.setup import load_saved_token

        oauth_creds = load_saved_token()
        if oauth_creds:
            _calendar_service = build("calendar", "v3", credentials=oauth_creds)
            try:
                calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", CALENDAR_ID)
                calendar = (
                    _calendar_service.calendars().get(calendarId=calendar_id).execute()
                )
                logger.info(
                    f"Calendar: Using saved OAuth token. Connected as: {calendar.get('summary', 'Unknown')}"
                )
                return _calendar_service
            except HttpError as e:
                logger.info(
                    f"Calendar OAuth token available but access failed: {e}. Trying ADC."
                )
                _calendar_service = None
    except Exception as e:
        logger.debug(f"Calendar OAuth token not available: {e}")

    # 2. Try Application Default Credentials (from gcloud auth application-default login)
    try:
        adc_creds, adc_project = google.auth.default(scopes=scopes)
        if not adc_creds.valid:
            adc_creds.refresh(Request())

        # User credentials need a quota project for Calendar API
        if hasattr(adc_creds, "with_quota_project") and adc_project:
            adc_creds = adc_creds.with_quota_project(adc_project)
            logger.debug(f"Calendar ADC: Applied quota project {adc_project}")

        _calendar_service = build("calendar", "v3", credentials=adc_creds)

        # Verify connectivity
        try:
            calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", CALENDAR_ID)
            calendar = (
                _calendar_service.calendars().get(calendarId=calendar_id).execute()
            )
            logger.info(
                f"Calendar: Using ADC. Connected as: {calendar.get('summary', 'Unknown')}"
            )
            return _calendar_service
        except HttpError as e:
            logger.info(
                f"Calendar ADC available but calendar access failed: {e}. Trying service account."
            )
            _calendar_service = None
    except Exception as e:
        logger.debug(f"Calendar ADC not available: {e}. Trying service account.")

    try:
        # Get the impersonation email for domain-wide delegation if set
        impersonation_email = os.environ.get("GOOGLE_IMPERSONATION_EMAIL")

        # Get service account credentials path from environment or use default
        credentials_path = os.environ.get(
            "GOOGLE_CALENDAR_SERVICE_ACCOUNT_FILE", service_account_path
        )

        # Check JSON string from environment
        service_account_json = os.environ.get("GOOGLE_CALENDAR_SERVICE_ACCOUNT_JSON")

        use_file_path = True
        if service_account_json and service_account_json.strip():
            try:
                # Try to parse the JSON string from environment variable
                service_account_info = json.loads(service_account_json)
                logger.info(
                    "Using GOOGLE_CALENDAR_SERVICE_ACCOUNT_JSON environment variable"
                )

                # Create credentials from JSON string
                credentials = service_account.Credentials.from_service_account_info(
                    service_account_info, scopes=scopes
                )
                use_file_path = False
            except json.JSONDecodeError as e:
                # Fall back to file path if JSON parsing fails
                logger.warning(
                    f"Error parsing GOOGLE_CALENDAR_SERVICE_ACCOUNT_JSON: {e}. Falling back to file path method."
                )
                # Continue to the file path method
                use_file_path = True

        if use_file_path:
            # Use file path
            if credentials_path is None:
                error_msg = "No credentials path provided and GOOGLE_CALENDAR_SERVICE_ACCOUNT_FILE is not set"
                logger.error(error_msg)
                raise ValueError(error_msg)

            if not os.path.exists(credentials_path):
                error_msg = f"Service account file not found at {credentials_path}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)

            logger.info(f"Loading service account credentials from: {credentials_path}")

            # Create credentials from file
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=scopes
            )

        # Apply impersonation if configured
        if impersonation_email:
            logger.info(
                f"Using service account impersonation for user: {impersonation_email}"
            )
            credentials = credentials.with_subject(impersonation_email)

        # Create the calendar service with our credentials
        _calendar_service = build("calendar", "v3", credentials=credentials)

        # Test with a simple API call to verify connectivity
        try:
            # Try to get the primary calendar to verify service works
            calendar = _calendar_service.calendars().get(calendarId="primary").execute()
            logger.info(
                f"Successfully connected to Google Calendar as: {calendar.get('summary', 'Unknown')}"
            )
        except HttpError as e:
            logger.error(f"Error verifying Google Calendar connection: {str(e)}")
            raise

        return _calendar_service

    except Exception as e:
        logger.exception(f"Error creating Calendar service: {str(e)}")
        raise


def get_workspace_calendar_service(
    user_email: str,
    service_account_path: str = CALENDAR_SERVICE_ACCOUNT_PATH,
    scopes: Optional[List[str]] = None,
    force_new: bool = False,
) -> Any:
    """
    Get calendar service using domain-wide delegation for Google Workspace.

    Args:
        user_email: The user email to impersonate
        service_account_path: Path to the service account credentials JSON file
        scopes: List of authorization scopes to request
        force_new: If True, create a new service instance even if one exists

    Returns:
        A Google Calendar API service object for the specified user

    Raises:
        FileNotFoundError: If service account file is not found
        ValueError: If credentials_path is None
        Exception: If authentication fails
    """
    global _workspace_services

    # Return cached service if available and not forced to create new
    cache_key = f"{user_email}:{','.join(scopes or [FULL_ACCESS_SCOPE])}"
    if not force_new and cache_key in _workspace_services:
        return _workspace_services[cache_key]

    if scopes is None:
        scopes = [FULL_ACCESS_SCOPE]

    try:
        # Get service account credentials path from environment or use default
        credentials_path = os.environ.get(
            "GOOGLE_CALENDAR_SERVICE_ACCOUNT_FILE", service_account_path
        )

        # Check JSON string from environment
        service_account_json = os.environ.get("GOOGLE_CALENDAR_SERVICE_ACCOUNT_JSON")

        use_file_path = True
        if service_account_json and service_account_json.strip():
            try:
                # Try to parse the JSON string from environment variable
                service_account_info = json.loads(service_account_json)
                logger.info(
                    "Using GOOGLE_CALENDAR_SERVICE_ACCOUNT_JSON environment variable"
                )

                # Create credentials from JSON string
                credentials = service_account.Credentials.from_service_account_info(
                    service_account_info, scopes=scopes
                )
                use_file_path = False
            except json.JSONDecodeError as e:
                # Fall back to file path if JSON parsing fails
                logger.warning(
                    f"Error parsing GOOGLE_CALENDAR_SERVICE_ACCOUNT_JSON: {e}. Falling back to file path method."
                )
                # Continue to the file path method
                use_file_path = True

        if use_file_path:
            # Use file path
            if credentials_path is None:
                error_msg = "No credentials path provided and GOOGLE_CALENDAR_SERVICE_ACCOUNT_FILE is not set"
                logger.error(error_msg)
                raise ValueError(error_msg)

            if not os.path.exists(credentials_path):
                error_msg = f"Service account file not found at {credentials_path}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)

            logger.info(f"Loading service account credentials from: {credentials_path}")

            # Create credentials from file
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=scopes
            )

        # Delegate to impersonate the workspace user
        logger.info(f"Impersonating user: {user_email}")
        delegated_credentials = credentials.with_subject(user_email)

        # Create service with delegated credentials
        service = build("calendar", "v3", credentials=delegated_credentials)

        # Test with a simple API call to verify permissions
        try:
            # Try to get the primary calendar to verify service works
            calendar = service.calendars().get(calendarId="primary").execute()
            logger.info(f"Successfully connected to Google Calendar as: {user_email}")
        except HttpError as e:
            logger.error(
                f"Error verifying Google Calendar connection for {user_email}: {str(e)}"
            )
            if e.resp.status == 401 or e.resp.status == 403:
                logger.error(
                    "Authentication failed. Check service account permissions and domain-wide delegation."
                )
            raise

        # Cache the service
        _workspace_services[cache_key] = service
        return service

    except Exception as e:
        logger.exception(
            f"Error creating workspace calendar service for {user_email}: {str(e)}"
        )
        raise


def validate_calendar_access(calendar_id: Optional[str] = None):
    """
    Validate calendar access and connection setup.

    Args:
        calendar_id: The calendar ID to validate access to. If None, uses CALENDAR_ID from environment.

    Returns:
        bool: True if validation passes, False otherwise
    """
    logger.info("=== CALENDAR ACCESS VALIDATION ===")

    # If calendar_id is None, use the environment variable
    if calendar_id is None:
        calendar_id = CALENDAR_ID

    logger.info(f"Validating access to calendar ID: {calendar_id}")

    try:
        # Create calendar service
        service = get_calendar_service(force_new=True)
        if not service:
            logger.error("❌ Failed to create calendar service")
            return False

        # Try to get calendar metadata
        logger.info(f"Attempting to access calendar metadata...")
        try:
            calendar_info = service.calendars().get(calendarId=calendar_id).execute()
            logger.info(
                f"✅ Successfully accessed calendar: {calendar_info.get('summary', 'Unknown')}"
            )
        except HttpError as e:
            logger.error(f"❌ Failed to access calendar metadata: {str(e)}")
            if "notFound" in str(e):
                logger.error(
                    "   Calendar ID may be incorrect or the calendar doesn't exist"
                )
                logger.error(f"   Attempted to access calendar ID: {calendar_id}")
            elif "forbidden" in str(e).lower():
                logger.error(
                    "   Service account lacks permission to access this calendar"
                )
                logger.error(
                    f"   Make sure calendar {calendar_id} is shared with the service account"
                )
            return False

        # Try to list events (read access)
        try:
            from datetime import datetime

            now = datetime.utcnow().isoformat() + "Z"
            logger.info(f"Attempting to list calendar events...")
            events = (
                service.events()
                .list(calendarId=calendar_id, timeMin=now, maxResults=10)
                .execute()
            )

            items = events.get("items", [])
            logger.info(f"✅ Successfully listed events. Items found: {len(items)}")

            if items:
                logger.info("Sample of upcoming events:")
                for item in items[:3]:  # Show up to 3 events
                    start = item["start"].get("dateTime", item["start"].get("date"))
                    logger.info(f"  - {start}: {item.get('summary', 'No title')}")
            else:
                logger.info("No upcoming events found in this calendar")

        except HttpError as e:
            logger.error(f"❌ Failed to list calendar events: {str(e)}")
            if "forbidden" in str(e).lower():
                logger.error(
                    "   Service account lacks read permission for this calendar"
                )
                logger.error(
                    f"   Make sure calendar {calendar_id} is shared with the service account with at least read access"
                )
            return False

        logger.info("=== CALENDAR ACCESS VALIDATION SUCCESSFUL ===")
        return True

    except Exception as e:
        logger.exception(f"❌ Error during calendar validation: {str(e)}")
        return False


# Initialize calendar service at module import time
def initialize_calendar():
    """Initialize calendar service connection on startup."""
    try:
        logger.info("Initializing calendar service...")
        service = get_calendar_service()
        logger.info("Calendar service initialized successfully")
        return service
    except Exception as e:
        logger.warning(f"Failed to initialize calendar service: {e}")
        logger.info("Calendar service will be initialized on first use")
        return None


# Initialize service when module is imported (optional, can be commented out)
# initialize_calendar()
