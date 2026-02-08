"""Calendar account setup - run with: python -m radbot.tools.calendar.setup

Opens a browser to authenticate a Google account for Calendar access
and saves a dedicated token file, independent of gcloud ADC and service accounts.
"""

import json
import logging
import os
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
SCOPES = [CALENDAR_SCOPE]

DEFAULT_TOKEN_PATH = os.path.join(os.path.expanduser("~"), ".radbot", "calendar_token.json")
ADC_PATH = os.path.join(os.path.expanduser("~"), ".config", "gcloud", "application_default_credentials.json")


def _get_quota_project() -> Optional[str]:
    """Get a quota project ID for user credentials.

    Google APIs require a quota project when using user (non-service-account)
    credentials. Checks multiple sources.
    """
    # 1. Explicit env vars
    for env_var in ("GOOGLE_CLOUD_QUOTA_PROJECT", "GOOGLE_CLOUD_PROJECT",
                    "GCLOUD_PROJECT", "DEVSHELL_PROJECT_ID"):
        project = os.environ.get(env_var, "")
        if project:
            return project

    # 2. Read from ADC file (quota_project_id field)
    adc_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ADC_PATH)
    if os.path.exists(adc_path):
        try:
            with open(adc_path) as f:
                adc_data = json.load(f)
            project = adc_data.get("quota_project_id", "")
            if project:
                return project
        except Exception:
            pass

    # 3. Read from gcloud config files (default project)
    gcloud_config_files = [
        os.path.join(os.path.expanduser("~"), ".config", "gcloud", "properties"),
        os.path.join(os.path.expanduser("~"), ".config", "gcloud",
                     "configurations", "config_default"),
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

    return None


def _get_token_path() -> str:
    """Get the calendar token storage path from config or environment."""
    token_path = os.environ.get("CALENDAR_TOKEN_FILE", "")
    if token_path:
        return os.path.expanduser(token_path)

    try:
        from radbot.config import config_manager
        cal_config = config_manager.get_config().get("integrations", {}).get("calendar", {})
        token_path = cal_config.get("token_file", "")
        if token_path:
            return os.path.expanduser(token_path)
    except Exception:
        pass

    return DEFAULT_TOKEN_PATH


def _get_adc_client_config() -> Optional[dict]:
    """Extract OAuth client_id and client_secret from the ADC file."""
    adc_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ADC_PATH)
    if not os.path.exists(adc_path):
        return None

    try:
        with open(adc_path) as f:
            adc_data = json.load(f)
        client_id = adc_data.get("client_id")
        client_secret = adc_data.get("client_secret")
        if client_id and client_secret:
            return {"client_id": client_id, "client_secret": client_secret}
    except Exception:
        pass

    return None


def _get_client_file() -> str:
    """Get a client_secret.json path from config or environment."""
    client_file = os.environ.get("CALENDAR_OAUTH_CLIENT_FILE", "")
    if client_file:
        return os.path.expanduser(client_file)

    try:
        from radbot.config import config_manager
        cal_config = config_manager.get_config().get("integrations", {}).get("calendar", {})
        client_file = cal_config.get("oauth_client_file", "")
        if client_file:
            return os.path.expanduser(client_file)
    except Exception:
        pass

    return ""


def run_setup(port: int = 0) -> bool:
    """Interactive setup: authenticate a Google account for Calendar and save a token.

    Args:
        port: Port for the local OAuth callback server. Use 0 for auto-select,
              or a fixed port (e.g. 8085) for SSH tunneling from another machine.

    Returns:
        True if setup succeeded.
    """
    token_path = _get_token_path()

    # Try client_secret.json first
    client_file = _get_client_file()
    if client_file and os.path.exists(client_file):
        print(f"Using OAuth client from: {client_file}")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
            creds = flow.run_local_server(port=port, open_browser=(port == 0))
        except Exception as e:
            print(f"OAuth flow failed: {e}")
            return False
    else:
        # Extract client creds from ADC file
        adc_config = _get_adc_client_config()
        if not adc_config:
            print(
                "No OAuth client credentials found.\n"
                "Either:\n"
                "  1. Run: gcloud auth application-default login (creates ADC with client creds)\n"
                "  2. Set CALENDAR_OAUTH_CLIENT_FILE to a client_secret.json path"
            )
            return False

        print("Using OAuth client credentials from gcloud ADC file")
        client_config = {
            "installed": {
                "client_id": adc_config["client_id"],
                "client_secret": adc_config["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        try:
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=port, open_browser=(port == 0))
        except Exception as e:
            print(f"OAuth flow failed: {e}")
            return False

    # Save token
    try:
        token_dir = os.path.dirname(token_path)
        if token_dir:
            os.makedirs(token_dir, exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print(f"Token saved to: {token_path}")
    except Exception as e:
        print(f"Failed to save token: {e}")
        return False

    # Verify (user creds need a quota project for Calendar API)
    try:
        verify_creds = creds
        quota_project = _get_quota_project()
        if quota_project:
            verify_creds = creds.with_quota_project(quota_project)
            print(f"Using quota project: {quota_project}")
        service = build("calendar", "v3", credentials=verify_creds)
        calendar = service.calendars().get(calendarId="primary").execute()
        print(f"Calendar authenticated as: {calendar.get('summary', 'unknown')}")
        return True
    except Exception as e:
        print(f"Token saved but verification failed: {e}")
        return False


def load_saved_token() -> Optional[Credentials]:
    """Load a saved calendar OAuth token if it exists.

    Returns:
        Valid Credentials or None.
    """
    token_path = _get_token_path()
    if not os.path.exists(token_path):
        return None

    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    except Exception as e:
        logger.warning(f"Failed to load calendar token from {token_path}: {e}")
        return None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("Successfully refreshed calendar OAuth token")
        except Exception as e:
            logger.warning(f"Failed to refresh calendar token: {e}")
            return None

    if creds and creds.valid:
        logger.info(f"Calendar: Using saved OAuth token from {token_path}")
        # Apply quota project for user credentials
        quota_project = _get_quota_project()
        if quota_project:
            creds = creds.with_quota_project(quota_project)
            logger.info(f"Calendar: Applied quota project {quota_project}")
        return creds

    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Set up Calendar authentication for radbot")
    parser.add_argument(
        "--port", type=int, default=0,
        help="Fixed port for OAuth callback (default: auto). Use with SSH tunnel for remote machines."
    )
    args = parser.parse_args()

    print("=== Calendar Account Setup ===")
    if args.port:
        print(f"Listening on port {args.port} for OAuth callback.")
        print(f"If remote, tunnel with: ssh -L {args.port}:localhost:{args.port} user@this-machine")
    print("Sign in with the Google account whose calendar you want radbot to use.\n")

    success = run_setup(port=args.port)
    if success:
        print("\nSetup complete! Restart radbot to use the new account.")
    else:
        print("\nSetup failed.")
        raise SystemExit(1)
