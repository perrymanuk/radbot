"""Tests for Lidarr client singleton and configuration."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the Lidarr client singleton before each test."""
    from radbot.tools.lidarr import lidarr_client

    lidarr_client._client = None
    lidarr_client._initialized = False
    yield
    lidarr_client._client = None
    lidarr_client._initialized = False


class TestGetConfig:
    """Tests for _get_config()."""

    def test_config_from_config_loader(self):
        from radbot.tools.lidarr.lidarr_client import _get_config

        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {
            "lidarr": {
                "url": "http://lidarr:8686",
                "api_key": "test-key-123",
                "enabled": True,
            }
        }

        with patch(
            "radbot.config.config_loader.config_loader",
            mock_loader,
        ):
            cfg = _get_config()

        assert cfg["url"] == "http://lidarr:8686"
        assert cfg["api_key"] == "test-key-123"
        assert cfg["enabled"] is True

    @patch.dict(
        "os.environ",
        {
            "LIDARR_URL": "http://env-lidarr:8686",
            "LIDARR_API_KEY": "env-key-456",
        },
    )
    def test_config_from_env_vars(self):
        from radbot.tools.lidarr.lidarr_client import _get_config

        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {}
        with patch(
            "radbot.config.config_loader.config_loader",
            mock_loader,
        ):
            cfg = _get_config()

        assert cfg["url"] == "http://env-lidarr:8686"
        assert cfg["api_key"] == "env-key-456"

    @patch.dict("os.environ", {}, clear=False)
    def test_config_from_credential_store(self):
        from radbot.tools.lidarr.lidarr_client import _get_config

        mock_store = MagicMock()
        mock_store.available = True
        mock_store.get.side_effect = lambda k: {
            "lidarr_api_key": "store-key-789",
        }.get(k)

        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {}

        with patch(
            "radbot.config.config_loader.config_loader",
            mock_loader,
        ):
            with patch(
                "radbot.credentials.store.get_credential_store",
                return_value=mock_store,
            ):
                cfg = _get_config()

        assert cfg["api_key"] == "store-key-789"

    @patch.dict("os.environ", {}, clear=False)
    def test_defaults_when_unconfigured(self):
        from radbot.tools.lidarr.lidarr_client import _get_config

        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {}

        mock_store = MagicMock()
        mock_store.available = True
        mock_store.get.return_value = None

        with patch(
            "radbot.config.config_loader.config_loader",
            mock_loader,
        ):
            with patch(
                "radbot.credentials.store.get_credential_store",
                return_value=mock_store,
            ):
                cfg = _get_config()

        assert cfg["url"] is None
        assert cfg["api_key"] is None
        assert cfg["enabled"] is True


class TestSingleton:
    """Tests for get_lidarr_client() / reset_lidarr_client()."""

    def test_returns_none_when_disabled(self):
        from radbot.tools.lidarr.lidarr_client import get_lidarr_client

        with patch(
            "radbot.tools.lidarr.lidarr_client._get_config",
            return_value={"enabled": False, "url": "http://x", "api_key": "k"},
        ):
            assert get_lidarr_client() is None

    def test_returns_none_when_no_credentials(self):
        from radbot.tools.lidarr.lidarr_client import get_lidarr_client

        with patch(
            "radbot.tools.lidarr.lidarr_client._get_config",
            return_value={"enabled": True, "url": None, "api_key": None},
        ):
            assert get_lidarr_client() is None

    def test_returns_none_on_connection_failure(self):
        from radbot.tools.lidarr.lidarr_client import get_lidarr_client

        mock_client = MagicMock()
        mock_client.get_status.side_effect = Exception("connection refused")

        with patch(
            "radbot.tools.lidarr.lidarr_client._get_config",
            return_value={"enabled": True, "url": "http://x", "api_key": "k"},
        ):
            with patch(
                "radbot.tools.lidarr.lidarr_client.LidarrClient",
                return_value=mock_client,
            ):
                assert get_lidarr_client() is None

    def test_singleton_reuse(self):
        from radbot.tools.lidarr.lidarr_client import get_lidarr_client

        mock_client = MagicMock()
        mock_client.get_status.return_value = {"version": "1.0"}

        with patch(
            "radbot.tools.lidarr.lidarr_client._get_config",
            return_value={"enabled": True, "url": "http://x", "api_key": "k"},
        ):
            with patch(
                "radbot.tools.lidarr.lidarr_client.LidarrClient",
                return_value=mock_client,
            ):
                client1 = get_lidarr_client()
                client2 = get_lidarr_client()
                assert client1 is client2

    def test_reset_clears_singleton(self):
        from radbot.tools.lidarr.lidarr_client import (
            get_lidarr_client,
            reset_lidarr_client,
        )

        mock_client = MagicMock()
        mock_client.get_status.return_value = {"version": "1.0"}

        with patch(
            "radbot.tools.lidarr.lidarr_client._get_config",
            return_value={"enabled": True, "url": "http://x", "api_key": "k"},
        ):
            with patch(
                "radbot.tools.lidarr.lidarr_client.LidarrClient",
                return_value=mock_client,
            ) as mock_cls:
                get_lidarr_client()
                assert mock_cls.call_count == 1

                reset_lidarr_client()
                get_lidarr_client()
                assert mock_cls.call_count == 2
