"""Tests for Picnic client singleton and configuration."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the Picnic client singleton before each test."""
    from radbot.tools.picnic import picnic_client

    picnic_client._client = None
    picnic_client._initialized = False
    yield
    picnic_client._client = None
    picnic_client._initialized = False


class TestGetConfig:
    """Tests for _get_config()."""

    def test_config_from_config_loader(self):
        from radbot.tools.picnic.picnic_client import _get_config

        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {
            "picnic": {
                "username": "user@test.com",
                "password": "secret",
                "country_code": "NL",
                "enabled": True,
                "default_list_project": "My Groceries",
            }
        }

        with patch.dict("sys.modules", {}):
            with patch(
                "radbot.config.config_loader.config_loader",
                mock_loader,
            ):
                cfg = _get_config()

        assert cfg["username"] == "user@test.com"
        assert cfg["password"] == "secret"
        assert cfg["country_code"] == "NL"
        assert cfg["enabled"] is True
        assert cfg["default_list_project"] == "My Groceries"

    @patch.dict(
        "os.environ",
        {
            "PICNIC_USERNAME": "env_user",
            "PICNIC_PASSWORD": "env_pass",
            "PICNIC_COUNTRY_CODE": "BE",
        },
    )
    def test_config_from_env_vars(self):
        from radbot.tools.picnic.picnic_client import _get_config

        # Make config_loader return empty so env vars are used
        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {}
        with patch(
            "radbot.config.config_loader.config_loader",
            mock_loader,
        ):
            cfg = _get_config()

        assert cfg["username"] == "env_user"
        assert cfg["password"] == "env_pass"
        assert cfg["country_code"] == "BE"

    @patch.dict("os.environ", {}, clear=False)
    def test_config_from_credential_store(self):
        from radbot.tools.picnic.picnic_client import _get_config

        mock_store = MagicMock()
        mock_store.available = True
        mock_store.get.side_effect = lambda k: {
            "picnic_username": "store_user",
            "picnic_password": "store_pass",
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

        assert cfg["username"] == "store_user"
        assert cfg["password"] == "store_pass"

    @patch.dict("os.environ", {}, clear=False)
    def test_defaults_when_unconfigured(self):
        from radbot.tools.picnic.picnic_client import _get_config

        mock_loader = MagicMock()
        mock_loader.get_integrations_config.return_value = {}

        # Make credential store return None for everything
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

        assert cfg["username"] is None
        assert cfg["password"] is None
        assert cfg["country_code"] == "DE"
        assert cfg["enabled"] is True
        assert cfg["default_list_project"] == "Groceries"


class TestSingleton:
    """Tests for get_picnic_client() / reset_picnic_client()."""

    def test_returns_none_when_disabled(self):
        from radbot.tools.picnic.picnic_client import get_picnic_client

        with patch(
            "radbot.tools.picnic.picnic_client._get_config",
            return_value={"enabled": False, "username": "u", "password": "p", "country_code": "DE"},
        ):
            assert get_picnic_client() is None

    def test_returns_none_when_no_credentials(self):
        from radbot.tools.picnic.picnic_client import get_picnic_client

        with patch(
            "radbot.tools.picnic.picnic_client._get_config",
            return_value={"enabled": True, "username": None, "password": None, "country_code": "DE"},
        ):
            assert get_picnic_client() is None

    def test_returns_none_on_connection_failure(self):
        from radbot.tools.picnic.picnic_client import get_picnic_client

        with patch(
            "radbot.tools.picnic.picnic_client._get_config",
            return_value={"enabled": True, "username": "u", "password": "p", "country_code": "DE"},
        ):
            with patch(
                "radbot.tools.picnic.picnic_client.PicnicClientWrapper",
                side_effect=Exception("auth failed"),
            ):
                assert get_picnic_client() is None

    def test_singleton_reuse(self):
        from radbot.tools.picnic.picnic_client import get_picnic_client

        mock_wrapper = MagicMock()
        mock_wrapper.get_cart.return_value = {}

        with patch(
            "radbot.tools.picnic.picnic_client._get_config",
            return_value={"enabled": True, "username": "u", "password": "p", "country_code": "DE"},
        ):
            with patch(
                "radbot.tools.picnic.picnic_client.PicnicClientWrapper",
                return_value=mock_wrapper,
            ):
                client1 = get_picnic_client()
                client2 = get_picnic_client()
                assert client1 is client2

    def test_reset_clears_singleton(self):
        from radbot.tools.picnic.picnic_client import (
            get_picnic_client,
            reset_picnic_client,
        )

        mock_wrapper = MagicMock()
        mock_wrapper.get_cart.return_value = {}

        with patch(
            "radbot.tools.picnic.picnic_client._get_config",
            return_value={"enabled": True, "username": "u", "password": "p", "country_code": "DE"},
        ):
            with patch(
                "radbot.tools.picnic.picnic_client.PicnicClientWrapper",
                return_value=mock_wrapper,
            ) as mock_cls:
                get_picnic_client()
                assert mock_cls.call_count == 1

                reset_picnic_client()
                get_picnic_client()
                assert mock_cls.call_count == 2


class TestAuthTokenCaching:
    """Tests for auth token cache/restore."""

    def test_caches_token_on_login(self):
        mock_store = MagicMock()
        mock_store.available = True
        mock_store.get.return_value = None  # No cached token

        mock_api = MagicMock()
        mock_api.session.auth_token = "new_token_123"
        mock_api.get_cart.return_value = {}

        with patch(
            "radbot.credentials.store.get_credential_store",
            return_value=mock_store,
        ):
            with patch(
                "python_picnic_api2.PicnicAPI",
                return_value=mock_api,
            ):
                from radbot.tools.picnic.picnic_client import PicnicClientWrapper

                PicnicClientWrapper("user", "pass", "DE")

                # Verify token was cached
                mock_store.set.assert_called_once_with(
                    "picnic_auth_token",
                    "new_token_123",
                    credential_type="auth_token",
                    description="Picnic API auth token (auto-cached)",
                )

    def test_uses_cached_token_when_valid(self):
        mock_store = MagicMock()
        mock_store.available = True
        mock_store.get.return_value = "cached_token_456"

        mock_api = MagicMock()
        mock_api.get_cart.return_value = {}  # Token works

        with patch(
            "radbot.credentials.store.get_credential_store",
            return_value=mock_store,
        ):
            with patch(
                "python_picnic_api2.PicnicAPI",
                return_value=mock_api,
            ) as mock_cls:
                from radbot.tools.picnic.picnic_client import PicnicClientWrapper

                PicnicClientWrapper("user", "pass", "DE")

                # Should have been called with auth_token, not username/password
                mock_cls.assert_called_once_with(
                    auth_token="cached_token_456",
                    country_code="DE",
                )
