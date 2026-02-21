"""WebSocket test client for e2e tests."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import websockets

logger = logging.getLogger(__name__)


class WSTestClient:
    """Lightweight WebSocket client for testing the RadBot WS endpoint."""

    def __init__(self, ws):
        self._ws = ws
        self.received: List[Dict[str, Any]] = []

    @classmethod
    async def connect(cls, base_url: str, session_id: str, timeout: float = 10.0) -> "WSTestClient":
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
            logger.warning(f"Expected ready status, got: {msg}")

        return client

    async def _recv(self, timeout: float = 30.0) -> Dict[str, Any]:
        """Receive and parse a single JSON message."""
        raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
        msg = json.loads(raw)
        self.received.append(msg)
        return msg

    async def send_message(self, text: str) -> None:
        """Send a chat message."""
        await self._ws.send(json.dumps({"message": text}))

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
                    # Capture error but don't raise — let the test decide
                    error_text = content
                    # The server loop continues after error, waiting for
                    # next message. We won't get a "ready" so break here.
                    break
                # 'thinking', 'reset' etc. — continue waiting

            elif msg.get("type") == "events":
                for event in msg.get("content", []):
                    events.append(event)
                    # Extract final text response
                    if event.get("is_final") and event.get("text"):
                        response_text = event["text"]
                    elif event.get("type") == "model_response" and event.get("text"):
                        response_text = event["text"]

            elif msg.get("type") == "message":
                response_text = msg.get("content", response_text)

        return {"events": events, "response_text": response_text, "error": error_text}

    async def send_heartbeat(self) -> Dict[str, Any]:
        """Send heartbeat and wait for response."""
        await self._ws.send(json.dumps({"type": "heartbeat"}))
        return await self._recv(timeout=5.0)

    async def request_history(self, limit: int = 50) -> Dict[str, Any]:
        """Request chat history."""
        await self._ws.send(json.dumps({"type": "history_request", "limit": limit}))
        return await self._recv(timeout=10.0)

    async def send_raw(self, data: dict) -> None:
        """Send raw JSON data."""
        await self._ws.send(json.dumps(data))

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

    async def close(self):
        """Close the WebSocket connection."""
        await self._ws.close()
