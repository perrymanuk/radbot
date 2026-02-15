"""Admin API for managing encrypted credentials and configuration.

All endpoints require a bearer token matching ``RADBOT_ADMIN_TOKEN``.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from radbot.credentials.store import CredentialStore, get_credential_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_TOKEN_ENV = "RADBOT_ADMIN_TOKEN"
_bearer_scheme = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------
# Auth dependency
# ------------------------------------------------------------------
def _verify_admin(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> None:
    expected = os.environ.get(_ADMIN_TOKEN_ENV, "")
    if not expected:
        # Fall back to config.yaml admin_token
        try:
            from radbot.config.config_loader import config_loader

            expected = config_loader.get_config().get("admin_token") or ""
        except Exception:
            pass
    if not expected:
        raise HTTPException(503, "Admin API disabled — RADBOT_ADMIN_TOKEN not set")
    # Accept Bearer header or ?token= query parameter (for OAuth redirect links)
    if creds and creds.credentials == expected:
        return
    query_token = request.query_params.get("token", "")
    if query_token == expected:
        return
    raise HTTPException(401, "Invalid or missing admin bearer token")


def _require_store() -> CredentialStore:
    store = get_credential_store()
    if not store.available:
        raise HTTPException(
            503, "Credential store unavailable — RADBOT_CREDENTIAL_KEY not set"
        )
    return store


# ------------------------------------------------------------------
# Admin UI page
# ------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Serve the admin page (React SPA)."""
    dist_index = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static", "dist", "index.html"
    )
    if os.path.isfile(dist_index):
        with open(dist_index, "r") as f:
            html = f.read()
        html = html.replace('"/assets/', '"/static/dist/assets/')
        html = html.replace("'/assets/", "'/static/dist/assets/")
        return HTMLResponse(content=html)
    return HTMLResponse(
        content="<h1>RadBot Admin</h1><p>React frontend not built. Run <code>make build-frontend</code> first.</p>",
        status_code=503,
    )


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
    # Reset HA client singletons when the HA token is updated
    if name == "ha_token":
        try:
            from radbot.tools.homeassistant.ha_client_singleton import reset_ha_client

            reset_ha_client()
        except Exception:
            pass
        try:
            from radbot.tools.homeassistant.ha_ws_singleton import reset_ha_ws_client

            reset_ha_ws_client()
        except Exception:
            pass
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
        section = name[len("config:") :]
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
async def save_config_section(
    section: str, request: Request, _: None = Depends(_verify_admin)
):
    """Save a config section to the DB.  Body is the JSON object for that section."""
    if section == "database":
        raise HTTPException(
            400,
            "Cannot override database config from admin — it is the bootstrap config",
        )
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
    # Hot-reload agent model when agent config changes
    if section == "agent":
        try:
            from agent import root_agent
            from radbot.config import config_manager

            config_manager.apply_model_config(root_agent)
        except Exception as e:
            logger.warning(f"Agent model hot-reload failed: {e}")
    # Re-initialize memory service when vector_db config changes
    if section == "vector_db":
        try:
            from agent import root_agent
            from radbot.agent import agent_core
            from radbot.agent.agent_core import initialize_memory_service

            initialize_memory_service()
            if agent_core.memory_service:
                root_agent._memory_service = agent_core.memory_service
                logger.info(
                    "Re-initialized memory service after vector_db config change"
                )
        except Exception as e:
            logger.warning(f"Memory service hot-reload failed: {e}")
    # Reset client singletons so next call picks up new config
    if section == "integrations":
        try:
            from radbot.tools.homeassistant.ha_client_singleton import reset_ha_client

            reset_ha_client()
        except Exception:
            pass
        try:
            from radbot.tools.homeassistant.ha_ws_singleton import reset_ha_ws_client

            reset_ha_ws_client()
        except Exception:
            pass
        try:
            from radbot.tools.overseerr.overseerr_client import reset_overseerr_client

            reset_overseerr_client()
        except Exception:
            pass
        try:
            from radbot.tools.ntfy.ntfy_client import reset_ntfy_client

            reset_ntfy_client()
        except Exception:
            pass
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
    # Return a copy, redacting sensitive fields
    import copy

    from radbot.config.config_loader import config_loader

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
async def gmail_oauth_setup(
    request: Request,
    account: str = Query("default", description="Gmail account label"),
    _: None = Depends(_verify_admin),
):
    """Start the Gmail OAuth consent flow (server-side redirect)."""
    store = get_credential_store()
    client_json = store.get("gmail_oauth_client") if store.available else None

    if not client_json:
        # Try file-based client secret
        client_file = ""
        try:
            from radbot.tools.gmail.gmail_auth import _get_client_file

            client_file = _get_client_file()
        except Exception:
            pass
        if not client_file:
            # Also try config_loader directly
            try:
                from radbot.config.config_loader import config_loader

                gmail_cfg = (
                    config_loader.get_config().get("integrations", {}).get("gmail", {})
                )
                client_file = gmail_cfg.get("oauth_client_file", "")
                if client_file:
                    client_file = os.path.expanduser(client_file)
            except Exception:
                pass
        if not client_file or not os.path.exists(client_file):
            raise HTTPException(
                400,
                "No Gmail OAuth client configured. "
                "Store it as 'gmail_oauth_client' via the admin UI, "
                "or set integrations.gmail.oauth_client_file in config.yaml.",
            )
        with open(client_file) as f:
            client_json = f.read()

    from google_auth_oauthlib.flow import Flow

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
    redirect_uri = _get_oauth_redirect_uri(
        request, "/admin/api/credentials/gmail/callback"
    )

    client_config = json.loads(client_json)
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=redirect_uri
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    if not store.available:
        raise HTTPException(
            400,
            "Gmail OAuth flow requires the credential store to save tokens. "
            "Set RADBOT_CREDENTIAL_KEY to enable it.",
        )
    store.set(
        "_oauth_state_gmail",
        json.dumps({"state": state, "redirect_uri": redirect_uri, "account": account}),
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
        client_file = ""
        try:
            from radbot.tools.gmail.gmail_auth import _get_client_file

            client_file = _get_client_file()
        except Exception:
            pass
        if not client_file:
            try:
                from radbot.config.config_loader import config_loader

                gmail_cfg = (
                    config_loader.get_config().get("integrations", {}).get("gmail", {})
                )
                client_file = gmail_cfg.get("oauth_client_file", "")
                if client_file:
                    client_file = os.path.expanduser(client_file)
            except Exception:
                pass
        if client_file and os.path.exists(client_file):
            with open(client_file) as f:
                client_json = f.read()
        else:
            raise HTTPException(400, "No Gmail OAuth client configured")

    client_config = json.loads(client_json)
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=redirect_uri
    )
    # Google may return additional scopes (e.g. cloud-platform); accept them
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    flow.fetch_token(code=code)
    creds = flow.credentials

    account_label = state_data.get("account", "default")
    store.set(
        f"gmail_token_{account_label}",
        creds.to_json(),
        credential_type="oauth_token",
        description=f"Gmail OAuth token ({account_label} account)",
    )
    store.delete("_oauth_state_gmail")
    return HTMLResponse(
        f"<h2>Gmail token stored for account '{account_label}'.</h2>"
        "<p><a href='/admin/'>Back to admin</a></p>"
    )


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
    redirect_uri = _get_oauth_redirect_uri(
        request, "/admin/api/credentials/calendar/callback"
    )

    client_config = json.loads(client_json)
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=redirect_uri
    )
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
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=redirect_uri
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    store.set(
        "calendar_token",
        creds.to_json(),
        credential_type="oauth_token",
        description="Google Calendar OAuth token",
    )
    store.delete("_oauth_state_calendar")
    return HTMLResponse(
        "<h2>Calendar token stored successfully.</h2><p><a href='/admin/'>Back to admin</a></p>"
    )


# ------------------------------------------------------------------
# Gmail accounts discovery
# ------------------------------------------------------------------
@router.get("/api/gmail/accounts")
async def list_gmail_accounts(_: None = Depends(_verify_admin)):
    """List all discovered Gmail accounts (credential store + file tokens)."""
    try:
        from radbot.tools.gmail.gmail_auth import discover_accounts

        accounts = discover_accounts()
        return {"accounts": accounts}
    except Exception as e:
        logger.warning(f"Gmail account discovery failed: {e}")
        return {"accounts": [], "error": str(e)}


# ------------------------------------------------------------------
# Test connection endpoints
# ------------------------------------------------------------------
def _ok(message: str, **extra: Any) -> Dict[str, Any]:
    return {"status": "ok", "message": message, **extra}


def _err(message: str) -> Dict[str, Any]:
    return {"status": "error", "message": message}


@router.post("/api/test/google")
async def test_google(request: Request, _: None = Depends(_verify_admin)):
    """Test Google API key by listing models."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    api_key = body.get("api_key", "")
    if not api_key:
        store = get_credential_store()
        if store.available:
            api_key = store.get("google_api_key") or ""
    if not api_key:
        try:
            from radbot.config.config_loader import config_loader

            api_key = config_loader.get_config().get("api_keys", {}).get("google", "")
        except Exception:
            pass
    if not api_key:
        return _err("No Google API key configured")
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        models = list(client.models.list())
        return _ok(f"Connected — {len(models)} models available")
    except Exception as e:
        return _err(f"Connection failed: {e}")


@router.post("/api/test/gmail/{account}")
async def test_gmail(account: str, _: None = Depends(_verify_admin)):
    """Test Gmail token for a specific account."""
    try:
        from googleapiclient.discovery import build as gmail_build

        from radbot.tools.gmail.gmail_auth import authenticate_gmail

        creds = authenticate_gmail(account)
        if not creds:
            return _err(f"No valid credentials for account '{account}'")
        service = gmail_build("gmail", "v1", credentials=creds, cache_discovery=False)
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "unknown")
        return _ok(f"Authenticated as {email}")
    except Exception as e:
        return _err(f"Gmail test failed: {e}")


@router.post("/api/test/calendar")
async def test_calendar(request: Request, _: None = Depends(_verify_admin)):
    """Test Google Calendar connectivity by listing 1 event."""
    try:
        from radbot.config.config_loader import config_loader
        from radbot.tools.calendar.calendar_auth import get_calendar_service

        cal_cfg = config_loader.get_config().get("integrations", {}).get("calendar", {})
        calendar_id = cal_cfg.get("calendar_id", "primary")
        service = get_calendar_service(force_new=True)
        if not service:
            return _err("Could not create Calendar service — check credentials")
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                maxResults=1,
                singleEvents=True,
                orderBy="startTime",
                timeMin="2020-01-01T00:00:00Z",
            )
            .execute()
        )
        count = len(events_result.get("items", []))
        return _ok(
            f"Calendar access OK (calendar: {calendar_id}, found {count} event(s))"
        )
    except ImportError:
        return _err("Calendar module not available")
    except Exception as e:
        return _err(f"Calendar test failed: {e}")


@router.post("/api/test/jira")
async def test_jira(request: Request, _: None = Depends(_verify_admin)):
    """Test Jira connectivity with provided or stored credentials."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    url = body.get("url", "")
    email = body.get("email", "")
    api_token = body.get("api_token", "")

    # Fall back to stored config/credentials
    if not url or not email:
        try:
            from radbot.config.config_loader import config_loader

            jira_cfg = (
                config_loader.get_config().get("integrations", {}).get("jira", {})
            )
            url = url or jira_cfg.get("url", "")
            email = email or jira_cfg.get("email", "")
        except Exception:
            pass
    if not api_token or api_token == "***":
        store = get_credential_store()
        if store.available:
            api_token = store.get("jira_api_token") or ""
        if not api_token:
            try:
                from radbot.config.config_loader import config_loader

                api_token = (
                    config_loader.get_config()
                    .get("integrations", {})
                    .get("jira", {})
                    .get("api_token", "")
                )
            except Exception:
                pass

    if not url or not email or not api_token:
        return _err("Jira URL, email, and API token are all required")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{url.rstrip('/')}/rest/api/2/myself",
                auth=(email, api_token),
            )
            if resp.status_code == 200:
                data = resp.json()
                return _ok(
                    f"Connected as {data.get('displayName', data.get('name', 'unknown'))}"
                )
            return _err(f"Jira returned HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        return _err(f"Jira connection failed: {e}")


@router.post("/api/test/overseerr")
async def test_overseerr(request: Request, _: None = Depends(_verify_admin)):
    """Test Overseerr connectivity with provided or stored credentials."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    url = body.get("url", "")
    api_key = body.get("api_key", "")

    # Fall back to stored config/credentials
    if not url:
        try:
            from radbot.config.config_loader import config_loader

            overseerr_cfg = (
                config_loader.get_config().get("integrations", {}).get("overseerr", {})
            )
            url = url or overseerr_cfg.get("url", "")
        except Exception:
            pass
    if not api_key or api_key == "***":
        store = get_credential_store()
        if store.available:
            api_key = store.get("overseerr_api_key") or ""
        if not api_key:
            try:
                from radbot.config.config_loader import config_loader

                api_key = (
                    config_loader.get_config()
                    .get("integrations", {})
                    .get("overseerr", {})
                    .get("api_key", "")
                )
            except Exception:
                pass

    if not url or not api_key:
        return _err("Overseerr URL and API key are both required")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{url.rstrip('/')}/api/v1/status",
                headers={"X-Api-Key": api_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                return _ok(f"Connected to Overseerr v{data.get('version', '?')}")
            return _err(
                f"Overseerr returned HTTP {resp.status_code}: {resp.text[:200]}"
            )
    except Exception as e:
        return _err(f"Overseerr connection failed: {e}")


@router.post("/api/test/home-assistant")
async def test_home_assistant(request: Request, _: None = Depends(_verify_admin)):
    """Test Home Assistant connectivity."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    ha_url = body.get("url", "")
    ha_token = body.get("token", "")

    if not ha_url:
        try:
            from radbot.config.config_loader import config_loader

            ha_cfg = (
                config_loader.get_config()
                .get("integrations", {})
                .get("home_assistant", {})
            )
            ha_url = ha_url or ha_cfg.get("url", "")
        except Exception:
            pass
    if not ha_token or ha_token == "***":
        store = get_credential_store()
        if store.available:
            ha_token = store.get("ha_token") or ""
        if not ha_token:
            try:
                from radbot.config.config_loader import config_loader

                ha_token = (
                    config_loader.get_config()
                    .get("integrations", {})
                    .get("home_assistant", {})
                    .get("token", "")
                )
            except Exception:
                pass

    if not ha_url or not ha_token:
        return _err("Home Assistant URL and token are required")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{ha_url.rstrip('/')}/api/",
                headers={"Authorization": f"Bearer {ha_token}"},
            )
            if resp.status_code == 200:
                return _ok("Connected to Home Assistant")
            return _err(f"Home Assistant returned HTTP {resp.status_code}")
    except Exception as e:
        return _err(f"Home Assistant connection failed: {e}")


@router.post("/api/test/qdrant")
async def test_qdrant(request: Request, _: None = Depends(_verify_admin)):
    """Test Qdrant vector DB connectivity."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    url = body.get("url", "")
    api_key = body.get("api_key", "")
    host = body.get("host", "")
    port = body.get("port", None)

    # Fall back to config
    if not url and not host:
        try:
            from radbot.config.config_loader import config_loader

            vdb = config_loader.get_config().get("vector_db", {})
            url = url or vdb.get("url", "")
            host = host or vdb.get("host", "")
            port = port or vdb.get("port", None)
        except Exception:
            pass
    if not api_key or api_key == "***":
        store = get_credential_store()
        if store.available:
            api_key = store.get("qdrant_api_key") or ""
        if not api_key:
            try:
                from radbot.config.config_loader import config_loader

                api_key = (
                    config_loader.get_config().get("vector_db", {}).get("api_key", "")
                )
            except Exception:
                pass

    try:
        from qdrant_client import QdrantClient

        kwargs: Dict[str, Any] = {}
        if url:
            kwargs["url"] = url
        elif host:
            kwargs["host"] = host
            if port:
                kwargs["port"] = int(port)
        else:
            return _err("No Qdrant URL or host configured")
        if api_key:
            kwargs["api_key"] = api_key

        client = QdrantClient(**kwargs, timeout=10)
        collections = client.get_collections()
        names = [c.name for c in collections.collections]
        return _ok(f"Connected — {len(names)} collections: {', '.join(names[:5])}")
    except Exception as e:
        return _err(f"Qdrant connection failed: {e}")


@router.post("/api/test/ntfy")
async def test_ntfy(request: Request, _: None = Depends(_verify_admin)):
    """Test ntfy push notification by sending a test message."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    url = body.get("url", "")
    topic = body.get("topic", "")
    token = body.get("token", "")

    # Fall back to stored config
    if not url or not topic:
        try:
            from radbot.config.config_loader import config_loader

            ntfy_cfg = (
                config_loader.get_config().get("integrations", {}).get("ntfy", {})
            )
            url = url or ntfy_cfg.get("url", "https://ntfy.sh")
            topic = topic or ntfy_cfg.get("topic", "")
        except Exception:
            pass
    if not token or token == "***":
        store = get_credential_store()
        if store.available:
            token = store.get("ntfy_token") or ""
        if not token:
            try:
                from radbot.config.config_loader import config_loader

                token = (
                    config_loader.get_config()
                    .get("integrations", {})
                    .get("ntfy", {})
                    .get("token", "")
                )
            except Exception:
                pass

    if not topic:
        return _err("ntfy topic is required")

    try:
        headers: Dict[str, str] = {
            "Title": "RadBot Test",
            "Tags": "white_check_mark,robot",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{url.rstrip('/')}/{topic}",
                content="Push notifications are working!",
                headers=headers,
            )
            if resp.status_code == 200:
                return _ok(f"Test notification sent to {topic}")
            return _err(f"ntfy returned HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        return _err(f"ntfy test failed: {e}")


@router.post("/api/test/redis")
async def test_redis(request: Request, _: None = Depends(_verify_admin)):
    """Test Redis connectivity."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    redis_url = body.get("redis_url", "")
    if not redis_url:
        try:
            from radbot.config.config_loader import config_loader

            redis_url = config_loader.get_config().get("cache", {}).get("redis_url", "")
        except Exception:
            pass

    if not redis_url:
        return _err("No Redis URL configured")

    try:
        import redis

        r = redis.from_url(redis_url, socket_timeout=5)
        r.ping()
        info = r.info("server")
        version = info.get("redis_version", "unknown")
        r.close()
        return _ok(f"Connected — Redis {version}")
    except Exception as e:
        return _err(f"Redis connection failed: {e}")


# ------------------------------------------------------------------
# Telemetry endpoints
# ------------------------------------------------------------------
@router.get("/api/telemetry/usage")
async def get_telemetry_usage(_: None = Depends(_verify_admin)):
    """Return token usage and estimated cost stats."""
    from radbot.telemetry.usage_tracker import usage_tracker

    return usage_tracker.get_stats()


@router.post("/api/telemetry/reset")
async def reset_telemetry(_: None = Depends(_verify_admin)):
    """Reset all telemetry counters."""
    from radbot.telemetry.usage_tracker import usage_tracker

    usage_tracker.reset()
    return {"status": "ok", "message": "Telemetry counters reset"}


# ------------------------------------------------------------------
# Aggregate status endpoint (powers sidebar dots)
# ------------------------------------------------------------------
@router.get("/api/status")
async def get_integration_status(_: None = Depends(_verify_admin)):
    """Return aggregate connectivity status for all integrations.

    Uses config values (file + DB) and credential store.  Falls back
    gracefully when the credential store is unavailable.
    """
    from radbot.config.config_loader import config_loader

    cfg = config_loader.get_config()

    # Credential store may not be available (RADBOT_CREDENTIAL_KEY not set)
    store = get_credential_store()
    store_ok = store.available

    def _store_get(name: str) -> Optional[str]:
        if store_ok:
            try:
                return store.get(name)
            except Exception:
                return None
        return None

    status: Dict[str, Dict[str, str]] = {}

    # Google API — check if a key exists in credential store or config
    api_key = _store_get("google_api_key") or cfg.get("api_keys", {}).get("google", "")
    if api_key:
        status["google"] = {"status": "ok"}
    else:
        status["google"] = {"status": "unconfigured"}

    # Gmail — check credential store tokens AND file-based tokens
    gmail_cfg = cfg.get("integrations", {}).get("gmail", {})
    gmail_has_tokens = False
    # Check credential store
    if store_ok:
        try:
            for entry in store.list():
                if entry["name"].startswith("gmail_token_"):
                    gmail_has_tokens = True
                    break
        except Exception:
            pass
    # Check file-based tokens
    if not gmail_has_tokens:
        try:
            from radbot.tools.gmail.gmail_auth import discover_accounts

            accounts = discover_accounts()
            if accounts:
                gmail_has_tokens = True
        except Exception:
            pass
    # Also check if token_file is configured and exists
    if not gmail_has_tokens and gmail_cfg.get("token_file"):
        import os as _os

        token_path = _os.path.expanduser(gmail_cfg["token_file"])
        if _os.path.exists(token_path):
            gmail_has_tokens = True

    if gmail_has_tokens:
        status["gmail"] = {"status": "ok"}
    elif gmail_cfg.get("enabled"):
        status["gmail"] = {"status": "error", "message": "Enabled but no tokens found"}
    else:
        status["gmail"] = {"status": "unconfigured"}

    # Calendar
    cal_cfg = cfg.get("integrations", {}).get("calendar", {})
    cal_token = _store_get("calendar_token")
    cal_sa = _store_get("calendar_service_account")
    if cal_token or cal_sa or cal_cfg.get("service_account_file"):
        status["calendar"] = {"status": "ok"}
    elif cal_cfg.get("enabled"):
        status["calendar"] = {
            "status": "error",
            "message": "Enabled but no credentials",
        }
    else:
        status["calendar"] = {"status": "unconfigured"}

    # Jira
    jira_cfg = cfg.get("integrations", {}).get("jira", {})
    jira_token = _store_get("jira_api_token") or jira_cfg.get("api_token", "")
    if jira_cfg.get("url") and jira_token:
        status["jira"] = {"status": "ok"}
    elif jira_cfg.get("enabled"):
        status["jira"] = {"status": "error", "message": "Enabled but missing config"}
    else:
        status["jira"] = {"status": "unconfigured"}

    # Overseerr
    overseerr_cfg = cfg.get("integrations", {}).get("overseerr", {})
    overseerr_key = _store_get("overseerr_api_key") or overseerr_cfg.get("api_key", "")
    if overseerr_cfg.get("url") and overseerr_key:
        status["overseerr"] = {"status": "ok"}
    elif overseerr_cfg.get("enabled"):
        status["overseerr"] = {
            "status": "error",
            "message": "Enabled but missing config",
        }
    else:
        status["overseerr"] = {"status": "unconfigured"}

    # ntfy
    ntfy_cfg = cfg.get("integrations", {}).get("ntfy", {})
    ntfy_topic = ntfy_cfg.get("topic", "")
    if ntfy_topic and ntfy_cfg.get("enabled", True):
        status["ntfy"] = {"status": "ok"}
    elif ntfy_cfg.get("enabled") and not ntfy_topic:
        status["ntfy"] = {
            "status": "error",
            "message": "Enabled but no topic configured",
        }
    else:
        status["ntfy"] = {"status": "unconfigured"}

    # Home Assistant
    ha_cfg = cfg.get("integrations", {}).get("home_assistant", {})
    ha_token = _store_get("ha_token") or ha_cfg.get("token", "")
    if ha_cfg.get("url") and ha_token:
        status["home_assistant"] = {"status": "ok"}
    elif ha_cfg.get("enabled"):
        status["home_assistant"] = {
            "status": "error",
            "message": "Enabled but missing config",
        }
    else:
        status["home_assistant"] = {"status": "unconfigured"}

    # Qdrant
    vdb = cfg.get("vector_db", {})
    if vdb.get("url") or vdb.get("host"):
        try:
            from qdrant_client import QdrantClient

            qd_kwargs: Dict[str, Any] = {}
            if vdb.get("url"):
                qd_kwargs["url"] = vdb["url"]
            else:
                qd_kwargs["host"] = vdb["host"]
                if vdb.get("port"):
                    qd_kwargs["port"] = vdb["port"]
            qd_key = _store_get("qdrant_api_key") or vdb.get("api_key", "")
            if qd_key:
                qd_kwargs["api_key"] = qd_key
            qc = QdrantClient(**qd_kwargs, timeout=5)
            qc.get_collections()
            status["qdrant"] = {"status": "ok"}
        except Exception as e:
            status["qdrant"] = {"status": "error", "message": str(e)[:100]}
    else:
        status["qdrant"] = {"status": "unconfigured"}

    # Redis
    redis_url = cfg.get("cache", {}).get("redis_url", "")
    if redis_url:
        try:
            import redis as redis_lib

            r = redis_lib.from_url(redis_url, socket_timeout=3)
            r.ping()
            r.close()
            status["redis"] = {"status": "ok"}
        except Exception as e:
            status["redis"] = {"status": "error", "message": str(e)[:100]}
    else:
        status["redis"] = {"status": "unconfigured"}

    # PostgreSQL — always ok if we got this far (admin page loaded)
    status["postgresql"] = {"status": "ok"}

    # Credential store availability (needed for save operations)
    status["_credential_store"] = {"status": "ok" if store_ok else "unavailable"}

    return status
