"""Unit tests for radbot.mcp_server.auth."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from starlette.requests import Request

from radbot.mcp_server import auth


def _fake_request(headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/mcp/sse",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


class TestExpectedToken:
    @patch.dict("os.environ", {"RADBOT_MCP_TOKEN": ""}, clear=False)
    def test_returns_none_when_neither_source_configured(self):
        with patch("radbot.credentials.store.get_credential_store") as gcs:
            gcs.side_effect = Exception("unavailable")
            assert auth._expected_token() is None

    @patch.dict("os.environ", {"RADBOT_MCP_TOKEN": "env-token"}, clear=False)
    def test_returns_env_when_no_credential_store(self):
        with patch("radbot.credentials.store.get_credential_store") as gcs:
            store = MagicMock()
            store.available = False
            gcs.return_value = store
            assert auth._expected_token() == "env-token"

    @patch.dict("os.environ", {"RADBOT_MCP_TOKEN": "env-token"}, clear=False)
    def test_credential_store_wins_over_env(self):
        # Credential store has priority per radbot config ordering
        with patch("radbot.credentials.store.get_credential_store") as gcs:
            store = MagicMock()
            store.available = True
            store.get.return_value = "store-token"
            gcs.return_value = store
            assert auth._expected_token() == "store-token"

    @patch.dict("os.environ", {"RADBOT_MCP_TOKEN": "env-token"}, clear=False)
    def test_falls_back_to_env_when_store_is_empty(self):
        with patch("radbot.credentials.store.get_credential_store") as gcs:
            store = MagicMock()
            store.available = True
            store.get.return_value = None  # no entry
            gcs.return_value = store
            assert auth._expected_token() == "env-token"


class TestCheckBearer:
    @patch("radbot.mcp_server.auth._expected_token", return_value=None)
    def test_returns_503_when_unconfigured(self, _):
        resp = auth.check_bearer(_fake_request())
        assert resp is not None
        assert resp.status_code == 503

    @patch("radbot.mcp_server.auth._expected_token", return_value="secret")
    def test_returns_401_when_header_missing(self, _):
        resp = auth.check_bearer(_fake_request())
        assert resp is not None
        assert resp.status_code == 401

    @patch("radbot.mcp_server.auth._expected_token", return_value="secret")
    def test_returns_401_when_token_mismatch(self, _):
        resp = auth.check_bearer(_fake_request({"authorization": "Bearer wrong"}))
        assert resp is not None
        assert resp.status_code == 401

    @patch("radbot.mcp_server.auth._expected_token", return_value="secret")
    def test_returns_none_when_token_matches(self, _):
        resp = auth.check_bearer(_fake_request({"authorization": "Bearer secret"}))
        assert resp is None

    @patch("radbot.mcp_server.auth._expected_token", return_value="secret")
    def test_rejects_non_bearer_scheme(self, _):
        resp = auth.check_bearer(_fake_request({"authorization": "Basic dXNlcjpwYXNz"}))
        assert resp is not None
        assert resp.status_code == 401
