"""Unit tests for the Home Assistant WebSocket client."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from radbot.tools.homeassistant.ha_websocket_client import (
    HomeAssistantWebSocketClient,
    _derive_ws_url,
)


# ---------------------------------------------------------------------------
# URL derivation
# ---------------------------------------------------------------------------

class TestDeriveWsUrl:
    def test_http_to_ws(self):
        assert _derive_ws_url("http://ha.local:8123") == "ws://ha.local:8123/api/websocket"

    def test_https_to_wss(self):
        assert _derive_ws_url("https://ha.example.com") == "wss://ha.example.com/api/websocket"

    def test_trailing_slash_stripped(self):
        assert _derive_ws_url("http://ha.local:8123/") == "ws://ha.local:8123/api/websocket"

    def test_already_has_api_websocket(self):
        assert _derive_ws_url("ws://ha.local/api/websocket") == "ws://ha.local/api/websocket"

    def test_no_scheme(self):
        result = _derive_ws_url("ha.local:8123")
        assert result.endswith("/api/websocket")


# ---------------------------------------------------------------------------
# Helpers to build mock websocket
# ---------------------------------------------------------------------------

def _make_mock_ws(responses):
    """Create a mock websocket that yields *responses* on recv()."""
    ws = AsyncMock()
    ws.closed = False
    ws.recv = AsyncMock(side_effect=[json.dumps(r) for r in responses])
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


def _patch_connect(ws):
    """Patch websockets.connect to return an awaitable that resolves to *ws*."""
    connect_mock = AsyncMock(return_value=ws)
    return patch(
        "radbot.tools.homeassistant.ha_websocket_client.websockets.connect",
        connect_mock,
    )


# ---------------------------------------------------------------------------
# Connection / auth
# ---------------------------------------------------------------------------

class TestConnect:
    def test_successful_auth(self):
        ws = _make_mock_ws([
            {"type": "auth_required"},
            {"type": "auth_ok", "ha_version": "2025.1.0"},
        ])
        with _patch_connect(ws):
            client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
            asyncio.run(client.connect())
            sent = json.loads(ws.send.call_args_list[0][0][0])
            assert sent["type"] == "auth"
            assert sent["access_token"] == "tok"

    def test_auth_invalid_raises(self):
        ws = _make_mock_ws([
            {"type": "auth_required"},
            {"type": "auth_invalid", "message": "bad token"},
        ])
        with _patch_connect(ws):
            client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "bad")
            with pytest.raises(RuntimeError, match="Authentication failed"):
                asyncio.run(client.connect())

    def test_unexpected_first_message_raises(self):
        ws = _make_mock_ws([{"type": "something_else"}])
        with _patch_connect(ws):
            client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
            with pytest.raises(RuntimeError, match="Expected auth_required"):
                asyncio.run(client.connect())


# ---------------------------------------------------------------------------
# send_command
# ---------------------------------------------------------------------------

class TestSendCommand:
    def test_successful_command(self):
        result_payload = [{"id": 1, "url_path": "dash"}]
        ws = _make_mock_ws([
            {"type": "auth_required"},
            {"type": "auth_ok", "ha_version": "2025.1.0"},
            {"id": 1, "type": "result", "success": True, "result": result_payload},
        ])
        with _patch_connect(ws):
            client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
            result = asyncio.run(client.send_command("lovelace/dashboards/list"))
            assert result == result_payload

    def test_error_response_raises(self):
        ws = _make_mock_ws([
            {"type": "auth_required"},
            {"type": "auth_ok", "ha_version": "2025.1.0"},
            {
                "id": 1, "type": "result", "success": False,
                "error": {"code": "not_found", "message": "Dashboard not found"},
            },
        ])
        with _patch_connect(ws):
            client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
            with pytest.raises(RuntimeError, match="Dashboard not found"):
                asyncio.run(client.send_command("lovelace/config", url_path="nope"))

    def test_reconnect_on_connection_closed(self):
        """After a ConnectionClosed, the client reconnects once and retries."""
        from websockets.exceptions import ConnectionClosed

        call_count = 0

        async def fake_connect(url):
            nonlocal call_count
            call_count += 1
            ws = AsyncMock()
            ws.closed = False
            ws.close = AsyncMock()
            if call_count == 1:
                # First connection: auth succeeds, command send raises ConnectionClosed
                ws.recv = AsyncMock(side_effect=[
                    json.dumps({"type": "auth_required"}),
                    json.dumps({"type": "auth_ok", "ha_version": "2025.1.0"}),
                ])
                ws.send = AsyncMock(side_effect=[
                    None,  # auth send OK
                    ConnectionClosed(None, None),  # command send fails
                ])
            else:
                # Second connection: auth + command succeed
                # msg_id will be 1 (same as first attempt, since retry
                # does NOT re-increment the counter)
                ws.recv = AsyncMock(side_effect=[
                    json.dumps({"type": "auth_required"}),
                    json.dumps({"type": "auth_ok", "ha_version": "2025.1.0"}),
                    json.dumps({"id": 2, "type": "result", "success": True, "result": []}),
                ])
                ws.send = AsyncMock()
            return ws

        with patch("radbot.tools.homeassistant.ha_websocket_client.websockets.connect", side_effect=fake_connect):
            client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
            result = asyncio.run(client.send_command("lovelace/dashboards/list"))
            assert result == []
            assert call_count == 2


# ---------------------------------------------------------------------------
# Dashboard convenience methods
# ---------------------------------------------------------------------------

class TestDashboardMethods:
    def test_list_dashboards(self):
        client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
        client.send_command = AsyncMock(return_value=[{"id": 1}])
        result = asyncio.run(client.list_dashboards())
        client.send_command.assert_called_once_with("lovelace/dashboards/list")
        assert result == [{"id": 1}]

    def test_create_dashboard(self):
        client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
        client.send_command = AsyncMock(return_value={"id": 2})
        asyncio.run(client.create_dashboard("test-dash", "Test", icon="mdi:test"))
        call_kwargs = client.send_command.call_args
        assert call_kwargs[0][0] == "lovelace/dashboards/create"
        assert call_kwargs[1]["url_path"] == "test-dash"
        assert call_kwargs[1]["title"] == "Test"
        assert call_kwargs[1]["icon"] == "mdi:test"

    def test_delete_dashboard(self):
        client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
        client.send_command = AsyncMock(return_value=None)
        asyncio.run(client.delete_dashboard(42))
        client.send_command.assert_called_once_with(
            "lovelace/dashboards/delete", dashboard_id=42
        )

    def test_get_dashboard_config_default(self):
        client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
        client.send_command = AsyncMock(return_value={"views": []})
        result = asyncio.run(client.get_dashboard_config())
        client.send_command.assert_called_once_with("lovelace/config")
        assert result == {"views": []}

    def test_get_dashboard_config_specific(self):
        client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
        client.send_command = AsyncMock(return_value={"views": [{"title": "Main"}]})
        asyncio.run(client.get_dashboard_config("energy"))
        client.send_command.assert_called_once_with("lovelace/config", url_path="energy")

    def test_save_dashboard_config(self):
        client = HomeAssistantWebSocketClient("ws://fake/api/websocket", "tok")
        client.send_command = AsyncMock(return_value=None)
        cfg = {"views": [{"title": "New"}]}
        asyncio.run(client.save_dashboard_config(cfg, "my-dash"))
        client.send_command.assert_called_once_with(
            "lovelace/config/save", config=cfg, url_path="my-dash"
        )
