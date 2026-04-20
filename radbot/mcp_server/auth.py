"""Bearer token auth for the HTTP/SSE MCP transport.

Stdio transport runs as a local subprocess and does not use auth.

Token lookup order (matches radbot's standard priority: credential store
beats env var):

1. Credential store entry `mcp_token` (rotatable from the admin UI)
2. `RADBOT_MCP_TOKEN` env var (bootstrap value set by the Nomad job)

If both are unset, the HTTP endpoints return 503. Rotating via the admin
UI writes a new value to the credential store and existing clients must
re-copy the token (there is no refresh-token flow — this is a personal
system, not a production API).
"""

from __future__ import annotations

import logging
import os

from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_CREDENTIAL_KEY = "mcp_token"


def _expected_token() -> str | None:
    """The expected bearer token, or None if auth is unconfigured.

    Credential store wins over env var so admin-UI rotation takes effect
    without redeploying the Nomad job.
    """
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            stored = (store.get(_CREDENTIAL_KEY) or "").strip()
            if stored:
                return stored
    except Exception as exc:
        logger.debug("credential_store_unavailable err=%s", exc)

    env_token = os.environ.get("RADBOT_MCP_TOKEN", "").strip()
    return env_token or None


def is_auth_configured() -> bool:
    return _expected_token() is not None


def check_bearer(request: Request) -> JSONResponse | None:
    """Validate the Authorization header on `request`.

    Returns `None` on success, or a 401/503 JSONResponse on failure that the
    caller should return immediately.
    """
    expected = _expected_token()
    if expected is None:
        return JSONResponse(
            {"error": "MCP bridge disabled — RADBOT_MCP_TOKEN not set"},
            status_code=503,
        )
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return JSONResponse({"error": "Missing bearer token"}, status_code=401)
    if header[7:].strip() != expected:
        return JSONResponse({"error": "Invalid bearer token"}, status_code=401)
    return None
