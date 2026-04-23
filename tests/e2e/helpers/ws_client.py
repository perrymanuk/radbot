"""WebSocket test client for e2e tests.

Supports two connection modes:

**External mode** — ``WSTestClient.connect(base_url, session_id)``
    Connects to a running server via the ``websockets`` library (original
    behaviour, used when ``RADBOT_TEST_URL`` is set).

**In-process mode** — ``WSTestClient.connect_inprocess(asgi_app, session_id)``
    Drives a ``starlette.testclient.TestClient`` WebSocket session from an
    async test via ``asyncio.to_thread``.  No external server required.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

import websockets

logger = logging.getLogger(__name__)


class WSTestClient:
    """Lightweight WebSocket client for testing the RadBot WS endpoint."""

    def __init__(self, ws=None, *, _inprocess_ws=None):
        self._ws = ws  # websockets connection (external)
        self._inprocess_ws = _inprocess_ws  # starlette WebSocketTestSession
        self.received: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # External-mode constructor
    # ------------------------------------------------------------------

    @classmethod
    async def connect(
        cls, base_url: str, session_id: str, timeout: float = 10.0
    ) -> "WSTestClient":
        """Connect to the WebSocket endpoint and wait for 'ready' status."""
        ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws/{session_id}"

        ws = await asyncio.wait_for(
            websockets.connect(ws_url),
            timeout=timeout,
        )
        client = cls(ws)

        # Wait for ready status
        msg = await client._recv(timeout=timeout)
        if msg.get("type") != "status" or msg.get("content") != "ready":
            logger.warning("Expected ready status, got: %s", msg)

        return client

    # ------------------------------------------------------------------
    # In-process constructor (Starlette TestClient)
    # ------------------------------------------------------------------

    @classmethod
    async def connect_inprocess(
        cls,
        asgi_app: Any,
        session_id: str,
        timeout: float = 10.0,
    ) -> "WSTestClient":
        """Connect to an in-process ASGI app WebSocket endpoint.

        Uses ``starlette.testclient.TestClient.websocket_connect()`` under
        the hood, running the blocking I/O in a thread pool so async tests
        are not blocked.
        """
        from starlette.testclient import TestClient  # noqa: PLC0415

        def _open() -> Any:
            tc = TestClient(asgi_app, raise_server_exceptions=False)
            ws_session = tc.websocket_connect(f"/ws/{session_id}")
            ws_session.__enter__()
            return ws_session

        ws_session = await asyncio.to_thread(_open)
        client = cls(_inprocess_ws=ws_session)

        # Wait for ready status
        msg = await client._recv(timeout=timeout)
        if msg.get("type") != "status" or msg.get("content") != "ready":
            logger.warning("Expected ready status, got: %s", msg)

        return client

    # ------------------------------------------------------------------
    # Internal receive
    # ------------------------------------------------------------------

    async def _recv(self, timeout: float = 30.0) -> Dict[str, Any]:
        """Receive and parse a single JSON message from either transport."""
        if self._inprocess_ws is not None:
            # Starlette TestClient is synchronous — run in thread to avoid
            # blocking the event loop.
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(self._inprocess_ws.receive_json),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Timed out waiting for WebSocket message after {timeout}s"
                )
            self.received.append(raw)
            return raw
        else:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            self.received.append(msg)
            return msg

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    async def send_message(self, text: str) -> None:
        """Send a chat message."""
        payload = {"message": text}
        if self._inprocess_ws is not None:
            await asyncio.to_thread(self._inprocess_ws.send_json, payload)
        else:
            await self._ws.send(json.dumps(payload))

    async def send_raw(self, data: dict) -> None:
        """Send raw JSON data."""
        if self._inprocess_ws is not None:
            await asyncio.to_thread(self._inprocess_ws.send_json, data)
        else:
            await self._ws.send(json.dumps(data))

    # ------------------------------------------------------------------
    # High-level interaction
    # ------------------------------------------------------------------

    async def send_and_wait_response(
        self,
        text: str,
        timeout: float = 90.0,
    ) -> Dict[str, Any]:
        """Send a message and collect all frames until 'ready' status.

        Returns a dict with 'events' list, 'response_text' string,
        and 'error' string (if the server sent an error status).
        """
        await self.send_message(text)

        events: List[Dict[str, Any]] = []
        response_text = ""
        error_text = ""

        deadline = asyncio.get_event_loop().time() + timeout

        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for response after {timeout}s")

            msg = await self._recv(timeout=remaining)

            if msg.get("type") == "status":
                content = msg.get("content", "")
                if content == "ready":
                    break
                elif content.startswith("error"):
                    error_text = content
                    break
                # 'thinking', 'reset' etc. — continue waiting

            elif msg.get("type") == "events":
                for event in msg.get("content", []):
                    events.append(event)
                    if event.get("is_final") and event.get("text"):
                        response_text = event["text"]
                    elif event.get("type") == "model_response" and event.get("text"):
                        response_text = event["text"]

            elif msg.get("type") == "message":
                response_text = msg.get("content", response_text)

        # If response is just a routing announcement, prefer the last sub-agent text
        _ROUTING_PATTERNS = (
            "transfer",
            "passing to",
            "sending to",
            "sent to",
            "catching that wave",
            "hang tight",
            "right on,",
            "over to casa",
            "over to planner",
            "over to tracker",
            "over to comms",
            "over to scout",
            "over to axel",
        )
        if response_text and any(p in response_text.lower() for p in _ROUTING_PATTERNS):
            for event in reversed(events):
                text_ev = event.get("text", "")
                agent = event.get("agent_name", "beto")
                if text_ev and agent != "beto":
                    response_text = text_ev
                    break

        return {"events": events, "response_text": response_text, "error": error_text}

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    async def send_heartbeat(self) -> Dict[str, Any]:
        """Send heartbeat and wait for response."""
        await self.send_raw({"type": "heartbeat"})
        return await self._recv(timeout=5.0)

    async def request_history(self, limit: int = 50) -> Dict[str, Any]:
        """Request chat history."""
        await self.send_raw({"type": "history_request", "limit": limit})
        return await self._recv(timeout=10.0)

    async def recv_until(self, msg_type: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Receive messages until one matches the given type."""
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for {msg_type}")
            msg = await self._recv(timeout=remaining)
            if msg.get("type") == msg_type:
                return msg

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._inprocess_ws is not None:
            try:
                await asyncio.to_thread(self._inprocess_ws.__exit__, None, None, None)
            except Exception:
                pass
        elif self._ws is not None:
            await self._ws.close()
