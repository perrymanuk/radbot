"""Unit tests for `radbot.clients.provider` (EX44 / PT111).

Covers:
- Typed `@property` accessors delegate to the underlying integration's
  `get_X_client()` factory (verified by mocking the factory and asserting
  the property returns the mock).
- `clear()` calls every integration's `reset_X_client()` and is fail-soft:
  one broken integration does not prevent the rest from being cleared.
- `validate_secrets()` reports `ok` / `disabled` / `missing: ...` per
  integration and never raises.
- Module-level `get_provider()` returns a singleton; `reset_provider()`
  drops it and triggers `clear()` on the prior instance.

Async: `get_ha_ws()` is the only async accessor; tested explicitly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from radbot.clients.provider import (
    ClientProvider,
    get_provider,
    reset_provider,
)

# ---------------------------------------------------------------------------
# Property delegation — every accessor calls the right factory function
# ---------------------------------------------------------------------------


class TestClientProviderPropertyDelegation:
    """Each @property forwards to the integration's `get_X_client()` factory."""

    def test_overseerr_delegates(self) -> None:
        sentinel = object()
        with patch(
            "radbot.tools.overseerr.overseerr_client.get_overseerr_client",
            return_value=sentinel,
        ):
            assert ClientProvider().overseerr is sentinel

    def test_lidarr_delegates(self) -> None:
        sentinel = object()
        with patch(
            "radbot.tools.lidarr.lidarr_client.get_lidarr_client",
            return_value=sentinel,
        ):
            assert ClientProvider().lidarr is sentinel

    def test_jira_delegates(self) -> None:
        sentinel = object()
        with patch(
            "radbot.tools.jira.jira_client.get_jira_client",
            return_value=sentinel,
        ):
            assert ClientProvider().jira is sentinel

    def test_picnic_delegates(self) -> None:
        sentinel = object()
        with patch(
            "radbot.tools.picnic.picnic_client.get_picnic_client",
            return_value=sentinel,
        ):
            assert ClientProvider().picnic is sentinel

    def test_nomad_delegates(self) -> None:
        sentinel = object()
        with patch(
            "radbot.tools.nomad.nomad_client.get_nomad_client",
            return_value=sentinel,
        ):
            assert ClientProvider().nomad is sentinel

    def test_ntfy_delegates(self) -> None:
        sentinel = object()
        with patch(
            "radbot.tools.ntfy.ntfy_client.get_ntfy_client",
            return_value=sentinel,
        ):
            assert ClientProvider().ntfy is sentinel

    def test_github_delegates(self) -> None:
        sentinel = object()
        with patch(
            "radbot.tools.github.github_app_client.get_github_client",
            return_value=sentinel,
        ):
            assert ClientProvider().github is sentinel

    def test_ha_rest_delegates(self) -> None:
        sentinel = object()
        with patch(
            "radbot.tools.homeassistant.ha_client_singleton.get_ha_client",
            return_value=sentinel,
        ):
            assert ClientProvider().ha_rest is sentinel

    def test_ha_mcp_delegates(self) -> None:
        sentinel = object()
        with patch(
            "radbot.tools.homeassistant.ha_mcp_client.get_ha_mcp_client",
            return_value=sentinel,
        ):
            assert ClientProvider().ha_mcp is sentinel

    @pytest.mark.asyncio
    async def test_ha_ws_async_delegates(self) -> None:
        sentinel = object()

        async def fake_get_ha_ws_client():
            return sentinel

        with patch(
            "radbot.tools.homeassistant.ha_ws_singleton.get_ha_ws_client",
            new=fake_get_ha_ws_client,
        ):
            assert await ClientProvider().get_ha_ws() is sentinel


# ---------------------------------------------------------------------------
# clear() — fail-soft, calls every reset
# ---------------------------------------------------------------------------


class TestClientProviderClear:
    def test_clear_calls_every_reset(self) -> None:
        called: list[str] = []

        def make_recorder(name: str):
            def _record() -> None:
                called.append(name)

            return _record

        targets = {
            "radbot.tools.overseerr.overseerr_client.reset_overseerr_client": "overseerr",
            "radbot.tools.lidarr.lidarr_client.reset_lidarr_client": "lidarr",
            "radbot.tools.jira.jira_client.reset_jira_client": "jira",
            "radbot.tools.picnic.picnic_client.reset_picnic_client": "picnic",
            "radbot.tools.nomad.nomad_client.reset_nomad_client": "nomad",
            "radbot.tools.ntfy.ntfy_client.reset_ntfy_client": "ntfy",
            "radbot.tools.youtube.youtube_client.reset_youtube_client": "youtube",
            "radbot.tools.youtube.kideo_client.reset_kideo_client": "kideo",
            "radbot.tools.github.github_app_client.reset_github_client": "github",
            "radbot.tools.homeassistant.ha_client_singleton.reset_ha_client": "ha_rest",
            "radbot.tools.homeassistant.ha_ws_singleton.reset_ha_ws_client": "ha_ws",
            "radbot.tools.homeassistant.ha_mcp_client.reset_ha_mcp_client": "ha_mcp",
        }

        patches = [
            patch(target, new=make_recorder(name)) for target, name in targets.items()
        ]
        for p in patches:
            p.start()
        try:
            ClientProvider().clear()
        finally:
            for p in patches:
                p.stop()

        assert sorted(called) == sorted(targets.values())

    def test_clear_continues_when_one_reset_raises(self) -> None:
        """A broken reset must not prevent the rest from being cleared."""
        called: list[str] = []

        def boom() -> None:
            raise RuntimeError("simulated broken reset")

        def record_overseerr() -> None:
            called.append("overseerr")

        def record_jira() -> None:
            called.append("jira")

        with (
            patch(
                "radbot.tools.overseerr.overseerr_client.reset_overseerr_client",
                new=record_overseerr,
            ),
            patch(
                "radbot.tools.lidarr.lidarr_client.reset_lidarr_client",
                new=boom,
            ),
            patch(
                "radbot.tools.jira.jira_client.reset_jira_client",
                new=record_jira,
            ),
        ):
            # Should not raise.
            ClientProvider().clear()

        assert "overseerr" in called and "jira" in called


# ---------------------------------------------------------------------------
# validate_secrets() — never raises, classifies each integration
# ---------------------------------------------------------------------------


class TestValidateSecrets:
    def test_returns_dict_with_known_keys(self) -> None:
        # Without mocking, every integration is unconfigured in the test
        # environment — so the call must not raise and must return entries
        # for every registered integration.
        results = ClientProvider().validate_secrets()
        expected = {
            "overseerr",
            "lidarr",
            "jira",
            "picnic",
            "nomad",
            "ntfy",
            "youtube",
            "kideo",
            "github",
            "home_assistant",
        }
        assert expected <= set(results.keys())
        # Every value is a string.
        assert all(isinstance(v, str) for v in results.values())

    def test_ok_status_when_required_fields_present(self) -> None:
        with patch(
            "radbot.clients.provider._resolve_config",
            return_value={"url": "https://x", "api_key": "k", "enabled": True},
        ):
            results = ClientProvider().validate_secrets()
        assert results["overseerr"] == "ok"
        assert results["lidarr"] == "ok"

    def test_missing_status_when_required_field_absent(self) -> None:
        with patch(
            "radbot.clients.provider._resolve_config",
            return_value={"url": "https://x", "enabled": True},  # api_key missing
        ):
            results = ClientProvider().validate_secrets()
        assert "missing" in results["overseerr"]
        assert "api_key" in results["overseerr"]

    def test_disabled_status(self) -> None:
        with patch(
            "radbot.clients.provider._resolve_config",
            return_value={"enabled": False},
        ):
            results = ClientProvider().validate_secrets()
        assert results["overseerr"] == "disabled"

    def test_swallows_resolution_errors(self) -> None:
        def boom(_name: str) -> dict:
            raise RuntimeError("config layer down")

        with patch("radbot.clients.provider._resolve_config", new=boom):
            results = ClientProvider().validate_secrets()
        assert all(v.startswith("error:") for v in results.values())


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


class TestProviderSingleton:
    def test_get_provider_returns_same_instance(self) -> None:
        reset_provider()
        a = get_provider()
        b = get_provider()
        assert a is b

    def test_reset_provider_drops_instance(self) -> None:
        a = get_provider()
        reset_provider()
        b = get_provider()
        assert a is not b

    def test_reset_provider_calls_clear_on_prior_instance(self) -> None:
        called: list[str] = []

        with patch(
            "radbot.tools.overseerr.overseerr_client.reset_overseerr_client",
            new=lambda: called.append("overseerr"),
        ):
            get_provider()  # construct
            reset_provider()  # should fire clear() on it

        assert called == ["overseerr"]
