"""WebSocket basic connectivity e2e tests."""

import json
import uuid

import pytest

from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session"), pytest.mark.timeout(30)]


class TestWebSocketBasic:
    async def test_ws_connect_receives_ready(self, live_server):
        """Connecting to WS should receive a 'ready' status."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # The connect method already waits for ready — if we get here, it worked
            assert len(ws.received) >= 1
            first = ws.received[0]
            assert first["type"] == "status"
            assert first["content"] == "ready"
        finally:
            await ws.close()

    async def test_ws_heartbeat(self, live_server):
        """Sending heartbeat should get a heartbeat response."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            resp = await ws.send_heartbeat()
            assert resp["type"] == "heartbeat"
        finally:
            await ws.close()

    async def test_ws_history_request(self, live_server):
        """Sending history_request should get a history response."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            resp = await ws.request_history(limit=10)
            assert resp["type"] == "history"
            assert "messages" in resp
        finally:
            await ws.close()

    async def test_ws_invalid_message(self, live_server):
        """Sending an invalid message format should return an error status."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            await ws.send_raw({"foo": "bar"})
            msg = await ws.recv_until("status", timeout=10.0)
            assert "error" in msg.get("content", "").lower()
        finally:
            await ws.close()

    async def test_ws_multiple_connections(self, live_server):
        """Two WS connections to the same session should both get ready."""
        session_id = str(uuid.uuid4())
        ws1 = await WSTestClient.connect(live_server, session_id)
        try:
            ws2 = await WSTestClient.connect(live_server, session_id)
            try:
                # Both should have received ready
                assert ws1.received[0]["content"] == "ready"
                assert ws2.received[0]["content"] == "ready"
            finally:
                await ws2.close()
        finally:
            await ws1.close()
