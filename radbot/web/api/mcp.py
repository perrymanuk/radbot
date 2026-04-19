"""REST endpoints for the MCP bridge.

Two routers are exported:

- `router` — prefix `/api/mcp`, admin-token-gated. Manages the MCP token
  (view, reveal, rotate) and exposes operational status. Consumed by the
  React admin panel.
- `public_router` — prefix `/api/projects`, MCP-token-gated. Serves the
  endpoints the Claude Code `SessionStart` hook calls: `match?cwd=...`
  and `{ref_or_name}/context.md`. These mirror the MCP tools of the same
  name so shell scripts can consume them without an MCP client.

The MCP HTTP transport itself (`/mcp/sse`, `/mcp/messages/`) is mounted
from `radbot.mcp_server.http_transport` and handled separately.

Project listing/editing is **not** surfaced here anymore — projects live
in `telos_entries` (section `projects`) and are managed through
`/api/telos/*` and the Telos admin panel. The `wiki_path` and
`path_patterns` attached to each project are stored in Telos's JSONB
`metadata` field and edited via `PUT /api/telos/entry/projects/{ref}`
with `metadata_merge`.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])
public_router = APIRouter(prefix="/api/projects", tags=["mcp-public"])

_MCP_TOKEN_CREDENTIAL_KEY = "mcp_token"
_ADMIN_TOKEN_ENV = "RADBOT_ADMIN_TOKEN"

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _verify_admin(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    expected = os.environ.get(_ADMIN_TOKEN_ENV, "")
    if not expected:
        try:
            from radbot.config.config_loader import config_loader

            expected = config_loader.get_config().get("admin_token") or ""
        except Exception:
            pass
    if not expected:
        raise HTTPException(503, "Admin API disabled — RADBOT_ADMIN_TOKEN not set")
    if creds and creds.credentials == expected:
        return
    raise HTTPException(401, "Invalid or missing admin bearer token")


def _verify_mcp(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Auth the hook-facing endpoints against the same MCP bearer as /mcp/sse."""
    # Reuse the transport-side auth module so there's one source of truth
    from radbot.mcp_server import auth as mcp_auth

    expected = mcp_auth._expected_token()
    if expected is None:
        raise HTTPException(503, "MCP bridge disabled — RADBOT_MCP_TOKEN not set")
    if creds and creds.credentials == expected:
        return
    raise HTTPException(401, "Invalid or missing bearer token")


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------


def _mask(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "•" * len(token)
    return f"{token[:4]}…{token[-4:]}"


def _get_current_token() -> tuple[str, str]:
    """Return `(token, source)` where source is `credential_store` | `env` | ``."""
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            stored = (store.get(_MCP_TOKEN_CREDENTIAL_KEY) or "").strip()
            if stored:
                return stored, "credential_store"
    except Exception as exc:
        logger.debug("credential_store_unavailable err=%s", exc)
    env_token = os.environ.get("RADBOT_MCP_TOKEN", "").strip()
    if env_token:
        return env_token, "env"
    return "", ""


@router.get("/status", dependencies=[Depends(_verify_admin)])
async def mcp_status(request: Request) -> dict[str, Any]:
    """Report current MCP bridge state."""
    token, source = _get_current_token()
    wiki_path = os.environ.get("RADBOT_WIKI_PATH", "/mnt/ai-intel")
    wiki_mounted = os.path.isdir(wiki_path)
    base_url = str(request.base_url).rstrip("/")
    return {
        "auth_configured": bool(token),
        "token_source": source,
        "token_masked": _mask(token),
        "wiki_path": wiki_path,
        "wiki_mounted": wiki_mounted,
        "sse_url": f"{base_url}/mcp/sse",
        "setup_url": f"{base_url}/setup/claude-code.md",
    }


@router.get("/token/reveal", dependencies=[Depends(_verify_admin)])
async def mcp_token_reveal() -> dict[str, str]:
    """Return the current token in cleartext (explicit admin action)."""
    token, source = _get_current_token()
    if not token:
        raise HTTPException(404, "No MCP token configured (set RADBOT_MCP_TOKEN or rotate).")
    return {"token": token, "source": source}


@router.post("/token/rotate", dependencies=[Depends(_verify_admin)])
async def mcp_token_rotate() -> dict[str, str]:
    """Generate a new token, persist to credential store, return it once."""
    from radbot.credentials.store import get_credential_store

    store = get_credential_store()
    if not store.available:
        raise HTTPException(
            503, "Credential store unavailable — cannot rotate (set RADBOT_CREDENTIAL_KEY)"
        )

    new_token = secrets.token_urlsafe(32)
    store.set(
        _MCP_TOKEN_CREDENTIAL_KEY,
        new_token,
        credential_type="api_token",
    )
    logger.info("mcp_token_rotated token_prefix=%s", new_token[:6])
    return {"token": new_token, "source": "credential_store"}


# ---------------------------------------------------------------------------
# Hook-facing endpoints (MCP-token-gated)
#
# These mirror the `project_match` and `project_get_context` MCP tools so
# shell scripts (notably the SessionStart hook) can consume them without
# running a full MCP client.
# ---------------------------------------------------------------------------


@public_router.get("/match", dependencies=[Depends(_verify_mcp)])
async def project_match_rest(cwd: str = Query(...)) -> dict[str, str | None]:
    """Return `{"project": ref_code}` or `{"project": null}`."""
    # Delegate to the MCP tool to avoid logic drift
    from radbot.mcp_server.tools import projects as proj_tools

    content = proj_tools._do_match(cwd).text.strip()
    return {"project": content or None}


@public_router.get(
    "/{ref_or_name}/context.md",
    response_class=PlainTextResponse,
    dependencies=[Depends(_verify_mcp)],
)
async def project_context_rest(ref_or_name: str) -> str:
    from radbot.mcp_server.tools import projects as proj_tools

    result = proj_tools._do_get_context(ref_or_name)
    # `_do_get_context` always returns markdown (or an error block)
    return result.text
