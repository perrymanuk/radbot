"""Stdio entrypoint for local / subprocess use.

Usage::

    uv run python -m radbot.mcp_server

Intended for development, testing with MCP Inspector, and any Claude Code
config that prefers to launch the server as a subprocess instead of
connecting to the HTTP/SSE endpoint on the deployed instance.

Stdio transport does not use bearer auth — it's a local subprocess, so the
trust boundary is the OS user.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import mcp.server.stdio
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions

from .server import create_server

logger = logging.getLogger(__name__)


async def _run() -> None:
    server = create_server()
    async with mcp.server.stdio.stdio_server() as (read, write):
        init_options = InitializationOptions(
            server_name="radbot-mcp",
            server_version="0.1.0",
            capabilities=server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={},
            ),
        )
        await server.run(read, write, init_options)


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    try:
        asyncio.run(_run())
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
