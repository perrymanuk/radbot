"""
Home Assistant WebSocket API client for radbot.

Provides dashboard (Lovelace) management via the HA WebSocket API,
which is the only interface that exposes dashboard CRUD operations.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


def _derive_ws_url(rest_url: str) -> str:
    """Derive the WebSocket URL from a REST API URL.

    ``http://`` → ``ws://``, ``https://`` → ``wss://``, then append
    ``/api/websocket``.
    """
    url = rest_url.rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://"):]
    if not url.endswith("/api/websocket"):
        url += "/api/websocket"
    return url


class HomeAssistantWebSocketClient:
    """Async WebSocket client for the Home Assistant WebSocket API.

    Handles authentication, message ID tracking, and auto-reconnect.
    """

    def __init__(self, ws_url: str, token: str):
        self.ws_url = ws_url
        self._token = token
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._msg_id = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect and authenticate.  Raises on failure."""
        self._ws = await websockets.connect(self.ws_url)

        # Step 1: receive auth_required
        raw = await self._ws.recv()
        msg = json.loads(raw)
        if msg.get("type") != "auth_required":
            raise RuntimeError(f"Expected auth_required, got {msg.get('type')}")

        # Step 2: send auth
        await self._ws.send(json.dumps({
            "type": "auth",
            "access_token": self._token,
        }))

        # Step 3: receive auth_ok / auth_invalid
        raw = await self._ws.recv()
        msg = json.loads(raw)
        if msg.get("type") != "auth_ok":
            raise RuntimeError(
                f"Authentication failed: {msg.get('message', msg.get('type'))}"
            )

        logger.info(
            "HA WebSocket authenticated (version %s)", msg.get("ha_version", "?")
        )

    async def _ensure_connected(self) -> None:
        """Reconnect if the socket is closed or absent."""
        if self._ws is None or self._ws.closed:
            await self.connect()

    async def close(self) -> None:
        """Gracefully close the connection."""
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    # ------------------------------------------------------------------
    # Command transport
    # ------------------------------------------------------------------

    async def send_command(self, msg_type: str, **kwargs: Any) -> Any:
        """Send a command and return the result.

        Serialises concurrent callers with an async lock so message IDs
        don't collide.  Automatically reconnects once on ``ConnectionClosed``.
        """
        async with self._lock:
            return await self._send_command_locked(msg_type, **kwargs)

    async def _send_command_locked(
        self, msg_type: str, *, _retried: bool = False, **kwargs: Any
    ) -> Any:
        try:
            await self._ensure_connected()
            assert self._ws is not None

            self._msg_id += 1
            payload: Dict[str, Any] = {"id": self._msg_id, "type": msg_type}
            payload.update(kwargs)

            await self._ws.send(json.dumps(payload))

            # Read until we get the matching result
            while True:
                raw = await self._ws.recv()
                data = json.loads(raw)
                if data.get("id") == self._msg_id and data.get("type") == "result":
                    if data.get("success"):
                        return data.get("result")
                    error = data.get("error", {})
                    raise RuntimeError(
                        f"HA WS error ({error.get('code', '?')}): "
                        f"{error.get('message', 'unknown')}"
                    )
        except ConnectionClosed:
            if _retried:
                raise
            logger.warning("HA WebSocket connection lost, reconnecting …")
            self._ws = None
            return await self._send_command_locked(
                msg_type, _retried=True, **kwargs
            )

    # ------------------------------------------------------------------
    # Dashboard (Lovelace) methods
    # ------------------------------------------------------------------

    async def list_dashboards(self) -> List[Dict[str, Any]]:
        """List all Lovelace dashboards."""
        return await self.send_command("lovelace/dashboards/list")

    async def create_dashboard(
        self,
        url_path: str,
        title: str,
        icon: Optional[str] = None,
        require_admin: bool = False,
        show_in_sidebar: bool = True,
        mode: str = "storage",
    ) -> Any:
        """Create a new Lovelace dashboard."""
        kwargs: Dict[str, Any] = {
            "url_path": url_path,
            "title": title,
            "require_admin": require_admin,
            "show_in_sidebar": show_in_sidebar,
            "mode": mode,
        }
        if icon:
            kwargs["icon"] = icon
        return await self.send_command("lovelace/dashboards/create", **kwargs)

    async def update_dashboard(
        self, dashboard_id: int, **kwargs: Any
    ) -> Any:
        """Update dashboard metadata (title, icon, etc.)."""
        return await self.send_command(
            "lovelace/dashboards/update", dashboard_id=dashboard_id, **kwargs
        )

    async def delete_dashboard(self, dashboard_id: int) -> Any:
        """Delete a dashboard by its numeric ID."""
        return await self.send_command(
            "lovelace/dashboards/delete", dashboard_id=dashboard_id
        )

    async def get_dashboard_config(self, url_path: str = "") -> Dict[str, Any]:
        """Get the full Lovelace config (views/cards) for a dashboard.

        ``url_path=""`` returns the default dashboard config.
        """
        kwargs: Dict[str, Any] = {}
        if url_path:
            kwargs["url_path"] = url_path
        return await self.send_command("lovelace/config", **kwargs)

    async def save_dashboard_config(
        self, config: Dict[str, Any], url_path: str = ""
    ) -> Any:
        """Save a Lovelace config (views/cards) for a dashboard.

        ``url_path=""`` targets the default dashboard.
        """
        kwargs: Dict[str, Any] = {"config": config}
        if url_path:
            kwargs["url_path"] = url_path
        return await self.send_command("lovelace/config/save", **kwargs)
