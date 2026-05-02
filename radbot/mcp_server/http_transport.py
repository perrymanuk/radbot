"""HTTP transport for the radbot MCP server.

Uses the modern MCP streamable-HTTP transport in **stateless mode**: every
request to `POST /mcp` is handled by a fresh `StreamableHTTPServerTransport`
with no shared session state. This eliminates the entire class of
"Could not find session" 404s that the legacy SSE transport produced after
process restarts (Nomad health-check, deploy, OOM) — there is no session
dict that can fall out of sync with the client (PT109).

Migration: the old endpoints (`GET /mcp/sse` + `POST /mcp/messages/`) are
removed. Clients must point at `POST /mcp` with `"type": "http"`. See
`docs/implementation/claude_settings_migration_pt109.md`.

Usage from `web/app.py`::

    from radbot.mcp_server.http_transport import (
        mount_mcp_on_app,
        get_mcp_session_manager,
    )
    mount_mcp_on_app(app)
    # In the lifespan context manager:
    async with get_mcp_session_manager().run():
        yield

If `RADBOT_MCP_TOKEN` is unset, the route still mounts but returns 503 —
this keeps the import path stable regardless of config.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

from . import auth
from .server import create_server

logger = logging.getLogger(__name__)

MCP_PATH = "/mcp"

_manager: StreamableHTTPSessionManager | None = None


def get_mcp_session_manager() -> StreamableHTTPSessionManager:
    """Return the singleton MCP session manager (lazily constructed)."""
    global _manager
    if _manager is None:
        _manager = StreamableHTTPSessionManager(
            app=create_server(),
            stateless=True,
        )
    return _manager


def reset_mcp_session_manager() -> None:
    """Drop the singleton (test hook). The manager itself can only run once."""
    global _manager
    _manager = None


def mount_mcp_on_app(app: FastAPI) -> None:
    """Attach the MCP streamable-HTTP route to the FastAPI app."""

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive)
        auth_err = auth.check_bearer(request)
        if auth_err is not None:
            await auth_err(scope, receive, send)
            return
        manager = _manager
        if manager is None or manager._task_group is None:
            response = Response(
                "MCP bridge not running", status_code=503
            )
            await response(scope, receive, send)
            return
        await manager.handle_request(scope, receive, send)

    app.router.routes.append(Mount(MCP_PATH, app=handle_mcp))
    logger.info("mcp_http_mounted path=%s mode=stateless", MCP_PATH)
