"""HTTP/SSE transport for the radbot MCP server.

Mounts the MCP `SseServerTransport` on the existing FastAPI app at
`/mcp/sse` (GET, SSE stream) and `/mcp/messages/` (POST, client → server
messages). Both are gated by `auth.check_bearer`.

Usage from `web/app.py`::

    from radbot.mcp_server.http_transport import mount_mcp_on_app
    mount_mcp_on_app(app)

If `RADBOT_MCP_TOKEN` is unset, the routes still mount but return 503 —
this keeps the import path stable regardless of config.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from . import auth
from .server import create_server

logger = logging.getLogger(__name__)

SSE_PATH = "/mcp/sse"
MESSAGES_PATH = "/mcp/messages/"


def mount_mcp_on_app(app: FastAPI) -> None:
    """Attach MCP SSE + messages routes to the FastAPI app."""
    transport = SseServerTransport(MESSAGES_PATH)
    server = create_server()

    async def handle_sse(request: Request) -> Response:
        auth_err = auth.check_bearer(request)
        if auth_err is not None:
            return auth_err
        async with transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )
        return Response()

    async def handle_messages(scope, receive, send):
        # ASGI-level handler so we can still pre-check auth on the raw request
        request = Request(scope, receive=receive)
        auth_err = auth.check_bearer(request)
        if auth_err is not None:
            await auth_err(scope, receive, send)
            return
        await transport.handle_post_message(scope, receive, send)

    app.router.routes.append(Route(SSE_PATH, endpoint=handle_sse, methods=["GET"]))
    app.router.routes.append(Mount(MESSAGES_PATH, app=handle_messages))
    logger.info("mcp_http_mounted sse=%s messages=%s", SSE_PATH, MESSAGES_PATH)
