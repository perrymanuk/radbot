"""Admin API for managing encrypted credentials and configuration.

All endpoints require a bearer token matching ``RADBOT_ADMIN_TOKEN``.
"""

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.templating import Jinja2Templates

from radbot.credentials.store import CredentialStore, get_credential_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_TOKEN_ENV = "RADBOT_ADMIN_TOKEN"
_bearer_scheme = HTTPBearer(auto_error=False)

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
)


# ------------------------------------------------------------------
# Auth dependency
# ------------------------------------------------------------------
def _verify_admin(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    expected = os.environ.get(_ADMIN_TOKEN_ENV, "")
    if not expected:
        raise HTTPException(503, "Admin API disabled — RADBOT_ADMIN_TOKEN not set")
    if creds is None or creds.credentials != expected:
        raise HTTPException(401, "Invalid or missing admin bearer token")


def _require_store() -> CredentialStore:
    store = get_credential_store()
    if not store.available:
        raise HTTPException(503, "Credential store unavailable — RADBOT_CREDENTIAL_KEY not set")
    return store


# ------------------------------------------------------------------
# Admin UI page
# ------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Serve the admin credentials management page."""
    return templates.TemplateResponse("admin.html", {"request": request})


# ------------------------------------------------------------------
# Credential CRUD
# ------------------------------------------------------------------
@router.get("/api/credentials")
async def list_credentials(_: None = Depends(_verify_admin)):
    store = _require_store()
    return store.list()


@router.post("/api/credentials")
async def store_credential(request: Request, _: None = Depends(_verify_admin)):
    store = _require_store()
    body = await request.json()
    name = body.get("name", "").strip()
    value = body.get("value", "")
    cred_type = body.get("credential_type", "api_key")
    description = body.get("description")

    if not name or not value:
        raise HTTPException(400, "name and value are required")

    store.set(name, value, credential_type=cred_type, description=description)
    return {"status": "ok", "name": name}


@router.delete("/api/credentials/{name:path}")
async def delete_credential(name: str, _: None = Depends(_verify_admin)):
    store = _require_store()
    if not store.delete(name):
        raise HTTPException(404, f"Credential '{name}' not found")
    return {"status": "ok", "name": name}


# ------------------------------------------------------------------
# Configuration section CRUD
# ------------------------------------------------------------------
# Config entries are stored with name "config:<section>" and type "config".
# The value is a JSON string of that config section.

@router.get("/api/config")
async def get_all_config(_: None = Depends(_verify_admin)):
    """Return all config sections stored in the DB (as a merged dict)."""
    store = _require_store()
    result = {}
    for entry in store.list():
        name = entry["name"]
        if not name.startswith("config:"):
            continue
        section = name[len("config:"):]
        raw = store.get(name)
        if raw:
            try:
                result[section] = json.loads(raw)
            except json.JSONDecodeError:
                result[section] = raw
    return result


@router.get("/api/config/{section}")
async def get_config_section(section: str, _: None = Depends(_verify_admin)):
    """Return a single config section from the DB."""
    store = _require_store()
    raw = store.get(f"config:{section}")
    if raw is None:
        raise HTTPException(404, f"Config section '{section}' not found in DB")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


@router.put("/api/config/{section}")
async def save_config_section(section: str, request: Request, _: None = Depends(_verify_admin)):
    """Save a config section to the DB.  Body is the JSON object for that section."""
    if section == "database":
        raise HTTPException(400, "Cannot override database config from admin — it is the bootstrap config")
    store = _require_store()
    body = await request.json()
    store.set(
        f"config:{section}",
        json.dumps(body),
        credential_type="config",
        description=f"Config section: {section}",
    )
    # Hot-reload into the running config
    try:
        from radbot.config.config_loader import config_loader
        config_loader.load_db_config()
    except Exception as e:
        logger.warning(f"Config hot-reload failed: {e}")
    return {"status": "ok", "section": section}


@router.delete("/api/config/{section}")
async def delete_config_section(section: str, _: None = Depends(_verify_admin)):
    """Delete a config section from the DB (reverts to file/default)."""
    store = _require_store()
    if not store.delete(f"config:{section}"):
        raise HTTPException(404, f"Config section '{section}' not found")
    return {"status": "ok", "section": section}


# ------------------------------------------------------------------
# Live config view (read-only, shows merged file+DB config)
# ------------------------------------------------------------------
@router.get("/api/config-live")
async def get_live_config(_: None = Depends(_verify_admin)):
    """Return the current merged config (file + DB overrides)."""
    from radbot.config.config_loader import config_loader
    # Return a copy, redacting sensitive fields
    import copy
    cfg = copy.deepcopy(config_loader.get_config())
    # Redact known sensitive fields
    if "database" in cfg and "password" in cfg["database"]:
        cfg["database"]["password"] = "***"
    if "api_keys" in cfg:
        for k in cfg["api_keys"]:
            if cfg["api_keys"][k]:
                cfg["api_keys"][k] = "***"
    return cfg


# ------------------------------------------------------------------
# OAuth flow helpers
# ------------------------------------------------------------------
def _get_oauth_redirect_uri(request: Request, callback_path: str) -> str:
    """Build an absolute redirect URI from the incoming request."""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    return f"{scheme}://{host}{callback_path}"


@router.get("/api/credentials/gmail/setup")
async def gmail_oauth_setup(request: Request, _: None = Depends(_verify_admin)):
    """Start the Gmail OAuth consent flow (server-side redirect)."""
    store = _require_store()
    client_json = store.get("gmail_oauth_client")

    if not client_json:
        from radbot.tools.gmail.gmail_auth import _get_client_file
        client_file = _get_client_file()
        if not client_file or not os.path.exists(client_file):
            raise HTTPException(
                400,
                "No Gmail OAuth client configured. "
                "Store it as 'gmail_oauth_client' via the admin UI first.",
            )
        with open(client_file) as f:
            client_json = f.read()

    from google_auth_oauthlib.flow import Flow

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
    redirect_uri = _get_oauth_redirect_uri(request, "/admin/api/credentials/gmail/callback")

    client_config = json.loads(client_json)
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    store.set(
        "_oauth_state_gmail",
        json.dumps({"state": state, "redirect_uri": redirect_uri}),
        credential_type="internal",
        description="Temporary Gmail OAuth state",
    )
    return RedirectResponse(auth_url)


@router.get("/api/credentials/gmail/callback")
async def gmail_oauth_callback(request: Request, code: str = "", state: str = ""):
    """Handle the Gmail OAuth callback and store the token."""
    store = _require_store()

    from google_auth_oauthlib.flow import Flow

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    state_json = store.get("_oauth_state_gmail")
    if not state_json:
        raise HTTPException(400, "No OAuth flow in progress")

    state_data = json.loads(state_json)
    redirect_uri = state_data["redirect_uri"]

    client_json = store.get("gmail_oauth_client")
    if not client_json:
        from radbot.tools.gmail.gmail_auth import _get_client_file
        client_file = _get_client_file()
        with open(client_file) as f:
            client_json = f.read()

    client_config = json.loads(client_json)
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials

    store.set(
        "gmail_token_default",
        creds.to_json(),
        credential_type="oauth_token",
        description="Gmail OAuth token (default account)",
    )
    store.delete("_oauth_state_gmail")
    return HTMLResponse("<h2>Gmail token stored successfully.</h2><p><a href='/admin/'>Back to admin</a></p>")


@router.get("/api/credentials/calendar/setup")
async def calendar_oauth_setup(request: Request, _: None = Depends(_verify_admin)):
    """Start the Google Calendar OAuth consent flow."""
    store = _require_store()
    client_json = store.get("calendar_oauth_client")

    if not client_json:
        raise HTTPException(
            400,
            "No Calendar OAuth client configured. "
            "Store it as 'calendar_oauth_client' via the admin UI first.",
        )

    from google_auth_oauthlib.flow import Flow

    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    redirect_uri = _get_oauth_redirect_uri(request, "/admin/api/credentials/calendar/callback")

    client_config = json.loads(client_json)
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    store.set(
        "_oauth_state_calendar",
        json.dumps({"state": state, "redirect_uri": redirect_uri}),
        credential_type="internal",
        description="Temporary Calendar OAuth state",
    )
    return RedirectResponse(auth_url)


@router.get("/api/credentials/calendar/callback")
async def calendar_oauth_callback(request: Request, code: str = "", state: str = ""):
    """Handle the Google Calendar OAuth callback and store the token."""
    store = _require_store()

    from google_auth_oauthlib.flow import Flow

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    state_json = store.get("_oauth_state_calendar")
    if not state_json:
        raise HTTPException(400, "No OAuth flow in progress")

    state_data = json.loads(state_json)
    redirect_uri = state_data["redirect_uri"]

    client_json = store.get("calendar_oauth_client")
    if not client_json:
        raise HTTPException(400, "No Calendar OAuth client configured")

    client_config = json.loads(client_json)
    flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials

    store.set(
        "calendar_token",
        creds.to_json(),
        credential_type="oauth_token",
        description="Google Calendar OAuth token",
    )
    store.delete("_oauth_state_calendar")
    return HTMLResponse("<h2>Calendar token stored successfully.</h2><p><a href='/admin/'>Back to admin</a></p>")
