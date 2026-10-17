"""Authentication module for Google Calendar API.

Supports (in order):
1. Application Default Credentials (ADC) - from gcloud auth application-default login
2. Service account credentials (existing behavior)
"""

import json
import logging
import os.path
from typing import Any, List, Optional

import google.auth
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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

# ADC path for quota project lookup
_ADC_PATH = os.path.join(
    os.path.expanduser("~"), ".config", "gcloud", "application_default_credentials.json"
)

# Global service instance
_calendar_service = None
_workspace_services = {}


def _get_quota_project() -> Optional[str]:
    """Get a quota project ID for user credentials.

    Checks (in order): env vars, ADC file, gcloud config files.
    """
    for env_var in (
        "GOOGLE_CLOUD_QUOTA_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
        "GCLOUD_PROJECT",
        "DEVSHELL_PROJECT_ID",
    ):
        project = os.environ.get(env_var, "")
        if project:
            return project

    adc_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", _ADC_PATH)
    if os.path.exists(adc_path):
        try:
            import json as _json

            with open(adc_path) as f:
                adc_data = _json.load(f)
            project = adc_data.get("quota_project_id", "")
            if project:
                return project
        except Exception:
            pass

    gcloud_config_files = [
        os.path.join(os.path.expanduser("~"), ".config", "gcloud", "properties"),
        os.path.join(
            os.path.expanduser("~"),
            ".config",
            "gcloud",
            "configurations",
            "config_default",
        ),
    ]
    for config_file in gcloud_config_files:
        if not os.path.exists(config_file):
            continue
        try:
            with open(config_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("project"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            project = parts[1].strip()
                            if project:
                                return project
        except Exception:
            pass

    # Fall back to DB config (google_cloud_project in agent section)
    try:
        from radbot.config import config_manager

        project = config_manager.get_google_cloud_project()
        if project:
            return project
    except Exception:
        pass

    return None


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
                creds = OAuthCredentials.from_authorized_user_info(token_info, scopes)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(AuthRequest())
                    # Write refreshed token back to store, preserving
                    # fields that creds.to_json() drops (e.g. quota_project_id)
                    refreshed = json.loads(creds.to_json())
                    for key in ("quota_project_id",):
                        if key in token_info and key not in refreshed:
                            refreshed[key] = token_info[key]
                    store.set(
                        "calendar_token",
                        json.dumps(refreshed),
                        credential_type="oauth_token",
                    )
                if creds and creds.valid:
                    _calendar_service = build("calendar", "v3", credentials=creds)
                    logger.debug("Calendar: Using OAuth token from credential store")
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
                logger.debug("Calendar: Using service account from credential store")
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
                logger.debug(
                    f"Calendar: Using saved OAuth token. Connected as: {calendar.get('summary', 'Unknown')}"
                )
                return _calendar_service
            except HttpError as e:
                logger.debug(
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
        quota_project = adc_project or _get_quota_project()
        if hasattr(adc_creds, "with_quota_project") and quota_project:
            adc_creds = adc_creds.with_quota_project(quota_project)
            logger.debug(f"Calendar ADC: Applied quota project {quota_project}")

        _calendar_service = build("calendar", "v3", credentials=adc_creds)

        # Verify connectivity
        try:
            calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", CALENDAR_ID)
            calendar = (
                _calendar_service.calendars().get(calendarId=calendar_id).execute()
            )
            logger.debug(
                f"Calendar: Using ADC. Connected as: {calendar.get('summary', 'Unknown')}"
            )
            return _calendar_service
        except HttpError as e:
            logger.debug(
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
                logger.debug(
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

            logger.debug(
                f"Loading service account credentials from: {credentials_path}"
            )

            # Create credentials from file
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=scopes
            )

        # Apply impersonation if configured
        if impersonation_email:
            logger.debug(
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
                logger.debug(
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

            logger.debug(
                f"Loading service account credentials from: {credentials_path}"
            )

            # Create credentials from file
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path, scopes=scopes
            )

        # Delegate to impersonate the workspace user
        logger.debug(f"Impersonating user: {user_email}")
        delegated_credentials = credentials.with_subject(user_email)

        # Create service with delegated credentials
        service = build("calendar", "v3", credentials=delegated_credentials)

        # Test with a simple API call to verify permissions
        try:
            # Try to get the primary calendar to verify service works
            service.calendars().get(calendarId="primary").execute()
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


# Initialize service when module is imported (optional, can be commented out)
# initialize_calendar()
