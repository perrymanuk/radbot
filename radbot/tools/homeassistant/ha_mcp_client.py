"""Minimal Streamable-HTTP Model Context Protocol client for Home Assistant.

HA ships an `mcp_server` core integration (since 2025.2) that exposes the
Assist LLM API — every built-in intent (`HassTurnOn`, `HassLightSet`,
`HassClimateSetTemperature`, `HassMediaSearchAndPlay`, etc.) plus every
user-exposed script — as MCP tools. Radbot talks to it over MCP's
streamable-HTTP transport at ``POST /api/mcp``.

### Why a custom client instead of ADK's ``McpToolset``

ADK's bundled ``McpToolset`` targets SSE transport and returns an
``AsyncExitStack`` the caller must keep alive for the lifetime of the
tools. That's awkward from the sync factory path used at agent
construction and creates lifetime-management traps (the throwaway
event-loop pattern in ``radbot/tools/mcp/mcp_homeassistant.py`` closes
the stack before tools are called).

HA's streamable-HTTP endpoint is **stateless** — each JSON-RPC request is
independent, no session id, no persistent stream. httpx (already a
project dep) is the right client, and each tool invocation is a plain
POST. Tool discovery is done once at factory time via the sync client;
per-call invocation uses the async client so it runs inside ADK's event
loop without extra plumbing.

### Auth

Bearer token — the same long-lived access token (LLAT) used for the
REST API. Configured in ``integrations.home_assistant.token`` or the
``ha_token`` credential-store entry (see
``radbot/tools/homeassistant/ha_client_singleton.py``).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from radbot.config.config_loader import config_loader

logger = logging.getLogger(__name__)


# MCP protocol version — latest HA server (1.26.0) advertises 2024-11-05.
# Sending this version keeps the negotiated protocol stable.
_MCP_PROTOCOL_VERSION = "2024-11-05"


def _normalize_mcp_url(base_url: str) -> str:
    """Derive the streamable-HTTP MCP endpoint from HA's REST base URL."""
    return urljoin(base_url.rstrip("/") + "/", "api/mcp")


class HAMcpClient:
    """Stateless streamable-HTTP MCP client for a single HA instance.

    The client is thread-safe for concurrent async calls — each request
    is independent and httpx's AsyncClient is safe to share.
    """

    def __init__(self, base_url: str, token: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoint = _normalize_mcp_url(self.base_url)
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._timeout = timeout
        self._next_id = 0
        self._initialized = False

    def _alloc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    # ------------------------------------------------------------------
    # Protocol helpers
    # ------------------------------------------------------------------

    def _init_request(self) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": self._alloc_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "clientInfo": {"name": "radbot", "version": "1.0"},
                "capabilities": {},
            },
        }

    @staticmethod
    def _initialized_notification() -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "method": "notifications/initialized"}

    def _tools_list_request(self) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": self._alloc_id(),
            "method": "tools/list",
        }

    def _tools_call_request(
        self, name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": self._alloc_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }

    @staticmethod
    def _raise_on_error(payload: Dict[str, Any]) -> Dict[str, Any]:
        err = payload.get("error")
        if err:
            raise RuntimeError(
                f"MCP error {err.get('code', '?')}: {err.get('message', 'unknown')}"
            )
        result = payload.get("result", {})
        # tools/call wraps results with isError=true on runtime errors
        if isinstance(result, dict) and result.get("isError"):
            content = result.get("content") or []
            text = content[0].get("text") if content else "unknown tool error"
            raise RuntimeError(f"MCP tool error: {text}")
        return result

    # ------------------------------------------------------------------
    # Sync path — used at factory time for tool discovery
    # ------------------------------------------------------------------

    def list_tools_sync(self) -> List[Dict[str, Any]]:
        """Fetch the tool catalog via a short-lived sync httpx.Client.

        Used during agent construction where spinning an event loop is
        awkward. Also serves as a connectivity probe for the admin test
        endpoint.
        """
        with httpx.Client(timeout=self._timeout) as client:
            init_resp = client.post(
                self.endpoint, headers=self._headers, json=self._init_request()
            )
            init_resp.raise_for_status()
            self._raise_on_error(init_resp.json())

            # Fire-and-forget the initialized notification; HA returns 202.
            client.post(
                self.endpoint,
                headers=self._headers,
                json=self._initialized_notification(),
            )

            list_resp = client.post(
                self.endpoint, headers=self._headers, json=self._tools_list_request()
            )
            list_resp.raise_for_status()
            result = self._raise_on_error(list_resp.json())
            tools = result.get("tools", [])
        self._initialized = True
        return tools

    # ------------------------------------------------------------------
    # Async path — used for tool invocation at LLM runtime
    # ------------------------------------------------------------------

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke an MCP tool. Returns the text payload of the first content
        part (HA always responds with a single text block whose body is a
        JSON-encoded ``{"success": bool, "result": ...}`` envelope).
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self.endpoint,
                headers=self._headers,
                json=self._tools_call_request(name, arguments),
            )
            resp.raise_for_status()
            result = self._raise_on_error(resp.json())
        content = result.get("content") or []
        if not content:
            return None
        return content[0].get("text")


# ──────────────────────────────────────────────────────────────────────
# Singleton + config resolution
# ──────────────────────────────────────────────────────────────────────


_mcp_client: Optional[HAMcpClient] = None


def reset_ha_mcp_client() -> None:
    """Reset the singleton so the next call re-reads config (admin hot-reload)."""
    global _mcp_client
    _mcp_client = None


def get_ha_mcp_client() -> Optional[HAMcpClient]:
    """Return a cached HA MCP client, or None if HA isn't configured.

    Resolves URL + token via the same priority chain as the REST client:
    merged config → credential store → env vars. Token lookup mirrors
    ``ha_client_singleton.get_ha_client``.
    """
    global _mcp_client
    if _mcp_client is not None:
        return _mcp_client

    ha_config = config_loader.get_home_assistant_config()
    ha_url = ha_config.get("url") or os.getenv("HA_URL")
    ha_token = ha_config.get("token")

    if not ha_token:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                ha_token = store.get("ha_token") or ""
        except Exception as e:
            logger.debug("Could not read ha_token from credential store: %s", e)

    if not ha_token:
        ha_token = os.getenv("HA_TOKEN")

    if not ha_url or not ha_token:
        logger.debug("HA MCP client: URL or token not configured")
        return None

    _mcp_client = HAMcpClient(ha_url, ha_token)
    return _mcp_client
