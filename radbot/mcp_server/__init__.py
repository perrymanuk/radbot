"""MCP server bridge — exposes radbot primitives to external MCP clients.

This is the *server* side of MCP (distinct from `radbot/tools/mcp/`, which is
the *consumer* side that lets radbot call external MCP servers).

Transports:

- **stdio** — `uv run python -m radbot.mcp_server` for local dev / subprocess use
- **HTTP/SSE** — mounted on the FastAPI app at `/mcp/sse` + `/mcp/messages/`
  via `http_transport.mount_mcp_on_app(app)` (called from `web/app.py`)

Auth (HTTP only): bearer token matching `RADBOT_MCP_TOKEN` env var.

Tool return format: markdown `TextContent` blocks. Single-primitive returns
(e.g. a bare project name) may use plain text. Never structured JSON to the
LLM — consumers of JSON should use the REST API at `/api/*`.
"""

from .server import create_server

__all__ = ["create_server"]
