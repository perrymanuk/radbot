"""Authentication module for Gmail API.

Supports multiple Gmail accounts via named tokens:
  python -m radbot.tools.gmail.setup --account personal
  python -m radbot.tools.gmail.setup --account work

Token files are stored as ~/.radbot/gmail_token_{account}.json.
The legacy ~/.radbot/gmail_token.json is treated as account "default".

Authentication methods (tried in order per account):
1. Saved OAuth token from a previous setup (per-account)
2. Application Default Credentials (ADC) as fallback (only for "default")
3. OAuth2 client_secret.json flow (only for "default")
"""

import glob
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Gmail read-only scope
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = [GMAIL_READONLY_SCOPE]

# Default paths
TOKEN_DIR = os.path.join(os.path.expanduser("~"), ".radbot")
DEFAULT_TOKEN_PATH = os.path.join(TOKEN_DIR, "gmail_token.json")
ADC_PATH = os.path.join(os.path.expanduser("~"), ".config", "gcloud", "application_default_credentials.json")

# Global cached services keyed by account label
_gmail_services: Dict[str, Any] = {}


def _get_token_path(account: Optional[str] = None) -> str:
    """Get the token storage path for an account.

    Args:
        account: Account label (e.g. "personal", "work").
                 None or "default" uses the legacy path.

    Returns:
        Absolute path to the token JSON file.
    """
    if account and account != "default":
        return os.path.join(TOKEN_DIR, f"gmail_token_{account}.json")

    # Check config/env for legacy single-account path
    token_path = os.environ.get("GMAIL_TOKEN_FILE", "")
    if token_path:
        return os.path.expanduser(token_path)

    try:
        from radbot.config import config_manager
        gmail_config = config_manager.get_config().get("integrations", {}).get("gmail", {})
        token_path = gmail_config.get("token_file", "")
        if token_path:
            return os.path.expanduser(token_path)
    except Exception:
        pass

    return DEFAULT_TOKEN_PATH


def _get_client_file() -> str:
    """Get the OAuth2 client credentials file path from config or environment."""
    client_file = os.environ.get("GMAIL_OAUTH_CLIENT_FILE", "")
    if client_file:
        return os.path.expanduser(client_file)

    try:
        from radbot.config import config_manager
        gmail_config = config_manager.get_config().get("integrations", {}).get("gmail", {})
        client_file = gmail_config.get("oauth_client_file", "")
        if client_file:
            return os.path.expanduser(client_file)
    except Exception:
        pass

    return ""


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
    except Exception as e:
        logger.debug(f"Could not read ADC file: {e}")

    return None


def _get_quota_project() -> Optional[str]:
    """Get a quota project ID for user credentials."""
    for env_var in ("GOOGLE_CLOUD_QUOTA_PROJECT", "GOOGLE_CLOUD_PROJECT",
                    "GCLOUD_PROJECT", "DEVSHELL_PROJECT_ID"):
        project = os.environ.get(env_var, "")
        if project:
            return project

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


def _apply_quota_project(creds: Credentials) -> Credentials:
    """Apply quota project to user credentials if available."""
    if hasattr(creds, 'with_quota_project'):
        quota_project = _get_quota_project()
        if quota_project:
            creds = creds.with_quota_project(quota_project)
            logger.debug(f"Gmail: Applied quota project {quota_project}")
    return creds


def _try_saved_token(token_path: str) -> Optional[Credentials]:
    """Try to load and refresh a previously saved OAuth token."""
    if not os.path.exists(token_path):
        return None

    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        logger.info(f"Loaded Gmail token from {token_path}")
    except Exception as e:
        logger.warning(f"Failed to load Gmail token from {token_path}: {e}")
        return None

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("Successfully refreshed Gmail token")
        except Exception as e:
            logger.warning(f"Failed to refresh Gmail token: {e}")
            return None

    if creds and creds.valid:
        return _apply_quota_project(creds)

    return None


def _try_adc() -> Optional[Credentials]:
    """Try to get credentials via Application Default Credentials."""
    try:
        creds, project = google.auth.default(scopes=SCOPES)
        if not creds.valid:
            creds.refresh(Request())
        if hasattr(creds, 'with_quota_project') and project:
            creds = creds.with_quota_project(project)
            logger.debug(f"Gmail ADC: Applied quota project {project}")
        logger.info("Gmail: Using Application Default Credentials (ADC)")
        return creds
    except Exception as e:
        logger.debug(f"Gmail ADC not available: {e}")
        return None


def _try_oauth_flow(client_file: str, token_path: str) -> Optional[Credentials]:
    """Run the OAuth2 browser consent flow using a client_secret.json file."""
    if not client_file or not os.path.exists(client_file):
        return None

    try:
        flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
        creds = flow.run_local_server(port=0)
        logger.info("Gmail OAuth2 consent flow completed successfully")
    except Exception as e:
        logger.error(f"Gmail OAuth2 flow failed: {e}")
        return None

    _save_token(creds, token_path)
    return _apply_quota_project(creds)


def _save_token(creds: Credentials, token_path: str) -> None:
    """Save credentials to a token file."""
    try:
        token_dir = os.path.dirname(token_path)
        if token_dir:
            os.makedirs(token_dir, exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        logger.info(f"Saved Gmail token to {token_path}")
    except Exception as e:
        logger.warning(f"Failed to save Gmail token: {e}")


def discover_accounts() -> List[Dict[str, str]]:
    """Discover all configured Gmail accounts by scanning token files and credential store.

    Returns:
        List of dicts with 'account' (label) and 'email' keys.
    """
    accounts = []
    seen_labels: set = set()

    # Check credential store first (DB-backed tokens for containerized deployment)
    try:
        from radbot.credentials.store import get_credential_store
        store = get_credential_store()
        if store.available:
            for entry in store.list():
                name = entry["name"]
                if not name.startswith("gmail_token_"):
                    continue
                label = name[len("gmail_token_"):]
                if not label:
                    continue
                # Try to build service and get email from the stored token
                try:
                    token_json = store.get(name)
                    if token_json:
                        creds = Credentials.from_authorized_user_info(
                            json.loads(token_json), SCOPES
                        )
                        if creds and creds.expired and creds.refresh_token:
                            creds.refresh(Request())
                        if creds and creds.valid:
                            creds = _apply_quota_project(creds)
                            service = build(
                                "gmail", "v1", credentials=creds, cache_discovery=False
                            )
                            profile = service.users().getProfile(userId="me").execute()
                            email = profile.get("emailAddress", "unknown")
                        else:
                            email = "unknown (token invalid)"
                    else:
                        email = "unknown"
                except Exception as e:
                    logger.debug(f"Could not get email for credential store token {name}: {e}")
                    email = "unknown"
                accounts.append({"account": label, "email": email, "source": "credential_store"})
                seen_labels.add(label)
    except Exception as e:
        logger.debug(f"Could not check credential store for Gmail tokens: {e}")

    # Check named token files: gmail_token_{label}.json
    pattern = os.path.join(TOKEN_DIR, "gmail_token_*.json")
    for path in sorted(glob.glob(pattern)):
        basename = os.path.basename(path)
        # Skip the legacy file (no underscore after "gmail_token")
        if basename == "gmail_token.json":
            continue
        # Extract label: gmail_token_personal.json -> personal
        label = basename.replace("gmail_token_", "").replace(".json", "")
        if not label or label in seen_labels:
            continue
        email = _get_email_from_token(path)
        accounts.append({"account": label, "email": email, "token_file": path})
        seen_labels.add(label)

    # Check legacy default token
    if "default" not in seen_labels:
        default_path = _get_token_path(None)
        if os.path.exists(default_path):
            # Don't double-count if the default path is also a named file
            if not any(a.get("token_file") == default_path for a in accounts):
                email = _get_email_from_token(default_path)
                accounts.append({"account": "default", "email": email, "token_file": default_path})

    return accounts


def _get_email_from_token(token_path: str) -> str:
    """Try to get the email address from a saved token by calling the Gmail API."""
    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if creds and creds.valid:
            creds = _apply_quota_project(creds)
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            profile = service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress", "unknown")
    except Exception as e:
        logger.debug(f"Could not get email from token {token_path}: {e}")
    return "unknown"


def run_setup(port: int = 0, account: Optional[str] = None) -> bool:
    """Interactive setup: authenticate a Gmail account and save a dedicated token.

    Args:
        port: Port for the local OAuth callback server.
        account: Account label (e.g. "personal", "work"). None for default.

    Returns:
        True if setup succeeded.
    """
    token_path = _get_token_path(account)
    label = account or "default"

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
                "  2. Set GMAIL_OAUTH_CLIENT_FILE to a client_secret.json path"
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

    _save_token(creds, token_path)

    # Verify
    try:
        verify_creds = _apply_quota_project(creds)
        service = build("gmail", "v1", credentials=verify_creds, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "unknown")
        print(f"Gmail account '{label}' authenticated as: {email}")
        print(f"Token saved to: {token_path}")
        return True
    except Exception as e:
        print(f"Token saved but verification failed: {e}")
        return False


def authenticate_gmail(account: Optional[str] = None) -> Optional[Credentials]:
    """Authenticate with Gmail API for a specific account.

    Args:
        account: Account label. None tries "default" (legacy behavior).

    Returns:
        Credentials object if successful, None otherwise.
    """
    # 0. Try credential store first
    key = account or "default"
    try:
        from radbot.credentials.store import get_credential_store
        store = get_credential_store()
        if store.available:
            token_json = store.get(f"gmail_token_{key}")
            if token_json:
                import json as _json
                creds = Credentials.from_authorized_user_info(_json.loads(token_json), SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    store.set(
                        f"gmail_token_{key}",
                        creds.to_json(),
                        credential_type="oauth_token",
                    )
                if creds and creds.valid:
                    logger.info(f"Gmail '{key}': Using token from credential store")
                    return _apply_quota_project(creds)
    except Exception as e:
        logger.debug(f"Gmail credential store lookup failed: {e}")

    # 1. Try saved token first
    token_path = _get_token_path(account)
    creds = _try_saved_token(token_path)
    if creds:
        return creds

    # For named accounts, only saved tokens are supported
    if account and account != "default":
        logger.error(
            f"Gmail account '{account}' not set up. "
            f"Run: python -m radbot.tools.gmail.setup --account {account}"
        )
        return None

    # 2. Try ADC as fallback (default account only)
    creds = _try_adc()
    if creds:
        return creds

    # 3. Try OAuth flow with client_secret.json (default account only)
    client_file = _get_client_file()
    creds = _try_oauth_flow(client_file, token_path)
    if creds:
        return creds

    logger.error(
        "Gmail authentication failed. Either:\n"
        "  1. Run: python -m radbot.tools.gmail.setup --account <label> (recommended)\n"
        "  2. Run: gcloud auth application-default login "
        '--scopes="https://www.googleapis.com/auth/gmail.readonly,'
        'https://www.googleapis.com/auth/cloud-platform"\n'
        "  3. Or set GMAIL_OAUTH_CLIENT_FILE to a client_secret.json path"
    )
    return None


def get_gmail_service(account: Optional[str] = None, force_new: bool = False) -> Any:
    """Get an authenticated Gmail API service object (cached per account).

    Args:
        account: Account label. None for default.
        force_new: If True, create a new service instance.

    Returns:
        Gmail API service object.

    Raises:
        RuntimeError: If authentication fails.
    """
    key = account or "default"

    if not force_new and key in _gmail_services:
        return _gmail_services[key]

    creds = authenticate_gmail(account)
    if not creds:
        raise RuntimeError(
            f"Gmail authentication failed for account '{key}'. "
            f"Run: python -m radbot.tools.gmail.setup --account {key}"
        )

    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    _gmail_services[key] = service
    logger.info(f"Gmail API service created for account '{key}'")
    return service
