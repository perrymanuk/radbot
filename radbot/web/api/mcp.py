"""REST endpoints for the MCP bridge: token rotation and project registry.

All endpoints require the admin bearer token (same mechanism as `admin.py`).
Used by the "MCP bridge" admin panel.

Note: the MCP HTTP transport itself (`/mcp/sse`, `/mcp/messages/`) is
mounted from `radbot.mcp_server.http_transport` and gated separately by
`RADBOT_MCP_TOKEN`. These admin routes are about *managing* that token
plus the project registry — not about serving MCP traffic.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

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
    """Report current MCP bridge state: auth configured?, token masked, wiki root, base_url."""
    token, source = _get_current_token()
    wiki_path = os.environ.get("RADBOT_WIKI_PATH", "/mnt/ai-intel")
    wiki_mounted = os.path.isdir(wiki_path)
    base_url = str(request.base_url).rstrip("/")
    return {
        "auth_configured": bool(token),
        "token_source": source,  # credential_store | env | "" (unconfigured)
        "token_masked": _mask(token),
        "wiki_path": wiki_path,
        "wiki_mounted": wiki_mounted,
        "sse_url": f"{base_url}/mcp/sse",
        "setup_url": f"{base_url}/setup/claude-code.md",
    }


@router.get("/token/reveal", dependencies=[Depends(_verify_admin)])
async def mcp_token_reveal() -> dict[str, str]:
    """Return the current token in cleartext.

    Deliberately a separate endpoint from `/status` so reveal is an explicit
    admin action (logged by access patterns) rather than implicit on any
    status fetch.
    """
    token, source = _get_current_token()
    if not token:
        raise HTTPException(404, "No MCP token configured (set RADBOT_MCP_TOKEN or rotate).")
    return {"token": token, "source": source}


@router.post("/token/rotate", dependencies=[Depends(_verify_admin)])
async def mcp_token_rotate() -> dict[str, str]:
    """Generate a new token, persist to credential store, return it once.

    After rotation, any client holding the previous token will 401. The UI
    shows this token in a one-time reveal modal — users must copy it into
    their shell profiles on each machine before dismissing.
    """
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
# Project registry CRUD
# ---------------------------------------------------------------------------


class ProjectIn(BaseModel):
    name: str = Field(..., min_length=1)
    path_patterns: list[str] = Field(default_factory=list)
    wiki_path: str | None = None


class ProjectPatch(BaseModel):
    path_patterns: list[str] | None = None
    wiki_path: str | None = None


def _project_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    name, patterns, wiki_path = row
    return {
        "name": name,
        "path_patterns": list(patterns or []),
        "wiki_path": wiki_path,
    }


@router.get("/projects", dependencies=[Depends(_verify_admin)])
async def list_projects() -> list[dict[str, Any]]:
    from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

    with get_db_connection() as conn, get_db_cursor(conn) as c:
        c.execute(
            "SELECT name, path_patterns, wiki_path FROM projects ORDER BY name"
        )
        return [_project_row_to_dict(r) for r in c.fetchall()]


@router.post("/projects", dependencies=[Depends(_verify_admin)])
async def upsert_project(body: ProjectIn) -> dict[str, Any]:
    from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

    clean_patterns = [p.strip() for p in body.path_patterns if p and p.strip()]

    with get_db_connection() as conn, get_db_cursor(conn, commit=True) as c:
        c.execute(
            """
            INSERT INTO projects (name, path_patterns, wiki_path)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE
              SET path_patterns = EXCLUDED.path_patterns,
                  wiki_path = EXCLUDED.wiki_path
            RETURNING name, path_patterns, wiki_path
            """,
            (body.name, clean_patterns, body.wiki_path),
        )
        row = c.fetchone()
    return _project_row_to_dict(row)


@router.patch("/projects/{name}", dependencies=[Depends(_verify_admin)])
async def patch_project(name: str, body: ProjectPatch) -> dict[str, Any]:
    from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

    sets = []
    params: list[Any] = []
    if body.path_patterns is not None:
        sets.append("path_patterns = %s")
        params.append([p.strip() for p in body.path_patterns if p and p.strip()])
    if body.wiki_path is not None:
        sets.append("wiki_path = %s")
        params.append(body.wiki_path or None)
    if not sets:
        raise HTTPException(400, "No fields to update")

    params.append(name)
    with get_db_connection() as conn, get_db_cursor(conn, commit=True) as c:
        c.execute(
            f"UPDATE projects SET {', '.join(sets)} "
            "WHERE name = %s RETURNING name, path_patterns, wiki_path",
            tuple(params),
        )
        row = c.fetchone()
    if row is None:
        raise HTTPException(404, f"No project named {name!r}")
    return _project_row_to_dict(row)


@router.delete("/projects/{name}", dependencies=[Depends(_verify_admin)])
async def delete_project(name: str) -> dict[str, str]:
    from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

    with get_db_connection() as conn, get_db_cursor(conn, commit=True) as c:
        c.execute("DELETE FROM projects WHERE name = %s", (name,))
        if c.rowcount == 0:
            raise HTTPException(404, f"No project named {name!r}")
    return {"deleted": name}
