"""Authentication module for Gmail API.

Supports multiple Gmail accounts via named tokens stored in the DB credential
store (``gmail_token_{label}``).  The ``setup`` sub-module can still write a
local file for initial bootstrapping, but at runtime **only** the credential
store is consulted — no filesystem scanning.

Authentication methods (tried in order per account):
1. DB credential store token (``gmail_token_{label}``)
2. Application Default Credentials (ADC) as fallback (only for "default")
3. OAuth2 client_secret.json flow (only for "default")
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

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
ADC_PATH = os.path.join(
    os.path.expanduser("~"), ".config", "gcloud", "application_default_credentials.json"
)

# Global cached services keyed by account label
_gmail_services: Dict[str, Any] = {}


def _get_client_json_from_store() -> Optional[str]:
    """Try to load the OAuth client JSON from the credential store."""
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            client_json = store.get("gmail_oauth_client")
            if client_json:
                logger.info("Using Gmail OAuth client from credential store")
                return client_json
    except Exception as e:
        logger.debug(f"Credential store lookup for gmail_oauth_client failed: {e}")
    return None


def _get_client_file() -> str:
    """Get the OAuth2 client credentials file path from config or environment."""
    client_file = os.environ.get("GMAIL_OAUTH_CLIENT_FILE", "")
    if client_file:
        return os.path.expanduser(client_file)

    try:
        from radbot.config import config_manager

        gmail_config = (
            config_manager.get_config().get("integrations", {}).get("gmail", {})
        )
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
    for env_var in (
        "GOOGLE_CLOUD_QUOTA_PROJECT",
        "GOOGLE_CLOUD_PROJECT",
        "GCLOUD_PROJECT",
        "DEVSHELL_PROJECT_ID",
    ):
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


def _apply_quota_project(creds: Credentials) -> Credentials:
    """Apply quota project to user credentials if available."""
    if hasattr(creds, "with_quota_project"):
        quota_project = _get_quota_project()
        if quota_project:
            creds = creds.with_quota_project(quota_project)
            logger.debug(f"Gmail: Applied quota project {quota_project}")
    return creds


def _try_adc() -> Optional[Credentials]:
    """Try to get credentials via Application Default Credentials."""
    try:
        creds, project = google.auth.default(scopes=SCOPES)
        if not creds.valid:
            creds.refresh(Request())
        # Apply quota project — try google.auth.default() project first, then
        # fall back to _get_quota_project() which checks env vars and gcloud config
        quota_project = project or _get_quota_project()
        if hasattr(creds, "with_quota_project") and quota_project:
            creds = creds.with_quota_project(quota_project)
            logger.debug(f"Gmail ADC: Applied quota project {quota_project}")
        logger.info("Gmail: Using Application Default Credentials (ADC)")
        return creds
    except Exception as e:
        logger.debug(f"Gmail ADC not available: {e}")
        return None


def discover_accounts() -> List[Dict[str, str]]:
    """Discover all configured Gmail accounts from the DB credential store.

    Returns:
        List of dicts with 'account' (label) and 'email' keys.
    """
    accounts = []

    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            for entry in store.list():
                name = entry["name"]
                if not name.startswith("gmail_token_"):
                    continue
                label = name[len("gmail_token_") :]
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
                    logger.debug(
                        f"Could not get email for credential store token {name}: {e}"
                    )
                    email = "unknown"
                accounts.append(
                    {"account": label, "email": email, "source": "credential_store"}
                )
    except Exception as e:
        logger.debug(f"Could not check credential store for Gmail tokens: {e}")

    return accounts


def run_setup(port: int = 0, account: Optional[str] = None) -> bool:
    """Interactive setup: authenticate a Gmail account and save the token to the credential store.

    Args:
        port: Port for the local OAuth callback server.
        account: Account label (e.g. "personal", "work"). None for default.

    Returns:
        True if setup succeeded.
    """
    label = account or "default"

    # Try credential store first, then client_secret.json file, then ADC
    client_json = _get_client_json_from_store()
    client_file = _get_client_file()

    if client_json:
        print("Using OAuth client from credential store")
        try:
            client_config = json.loads(client_json)
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=port, open_browser=(port == 0))
        except Exception as e:
            print(f"OAuth flow failed: {e}")
            return False
    elif client_file and os.path.exists(client_file):
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

    # Save token to credential store
    cred_name = f"gmail_token_{label}"
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        store.set(cred_name, creds.to_json(), credential_type="oauth_token")
        print(f"Token saved to credential store as '{cred_name}'")
    except Exception as e:
        print(f"WARNING: Could not save to credential store: {e}")
        # Fallback: save to disk so the token isn't lost
        token_path = os.path.join(TOKEN_DIR, f"gmail_token_{label}.json")
        os.makedirs(TOKEN_DIR, exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print(f"Token saved to disk at: {token_path}")
        print("Upload it to the credential store via /admin/ when available.")

    # Verify
    try:
        verify_creds = _apply_quota_project(creds)
        service = build("gmail", "v1", credentials=verify_creds, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "unknown")
        print(f"Gmail account '{label}' authenticated as: {email}")
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
    # 1. Try credential store (primary — all tokens live in DB)
    key = account or "default"
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            token_json = store.get(f"gmail_token_{key}")
            if token_json:
                creds = Credentials.from_authorized_user_info(
                    json.loads(token_json), SCOPES
                )
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

    # For named accounts, only credential store tokens are supported
    if account and account != "default":
        logger.error(
            f"Gmail account '{account}' not found in credential store. "
            f"Run: python -m radbot.tools.gmail.setup --account {account}"
        )
        return None

    # 2. Try ADC as fallback (default account only)
    creds = _try_adc()
    if creds:
        return creds

    logger.error(
        "Gmail authentication failed. Either:\n"
        "  1. Run: python -m radbot.tools.gmail.setup --account <label> (recommended)\n"
        "  2. Run: gcloud auth application-default login "
        '--scopes="https://www.googleapis.com/auth/gmail.readonly,'
        'https://www.googleapis.com/auth/cloud-platform"'
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
