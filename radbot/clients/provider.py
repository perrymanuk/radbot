"""Typed `ClientProvider` — single source of truth for integration client lifecycle.

Replaces the per-module `get_X_client()` / `reset_X_client()` lazy-singleton
pattern (and the parallel `_INTEGRATION_RESET_REGISTRY` in
`radbot/web/api/admin.py`). Callers get clients via typed `@property`
accessors on the provider instance returned from `get_provider()`.

Design choices (per EX44):

- **Strongly typed.** Each accessor is an explicit `@property` with a
  declared return type. mypy verifies static usage.
- **Test isolation.** `clear()` wipes every cached client. The autouse
  `_clear_client_provider` fixture in `tests/conftest.py` resets state
  between tests so leakage from one test cannot contaminate the next.
- **Stateless / resilient.** Cached clients are either stateless HTTP
  wrappers (per-call `httpx.AsyncClient`) or carry their own auto-reconnect
  logic (HA WebSocket). The provider does not manage socket health.
- **Fail-loud secrets.** `validate_secrets()` is invoked once at startup
  and reports per-integration status; missing required fields on enabled
  integrations log at `ERROR` so a SRE notices.

Async exception: HA WebSocket needs `await client.connect()` at factory
time, so the provider exposes it via `get_ha_ws()` (async method) rather
than a `@property`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from radbot.tools.github.github_app_client import GitHubAppClient
    from radbot.tools.homeassistant.ha_client_singleton import (
        HomeAssistantRESTClient,
    )
    from radbot.tools.homeassistant.ha_mcp_client import HAMcpClient
    from radbot.tools.homeassistant.ha_ws_singleton import (
        HomeAssistantWebSocketClient,
    )
    from radbot.tools.lidarr.lidarr_client import LidarrClient
    from radbot.tools.nomad.nomad_client import NomadClient
    from radbot.tools.ntfy.ntfy_client import NtfyClient
    from radbot.tools.overseerr.overseerr_client import OverseerrClient
    from radbot.tools.picnic.picnic_client import PicnicClientWrapper

logger = logging.getLogger(__name__)


class ClientProvider:
    """Process-wide registry of integration clients.

    Every accessor delegates to the integration's existing lazy-singleton
    factory (`get_X_client()`), which means the provider is a thin typed
    facade: a single import surface for callers, and a single `clear()`
    point for admin hot-reload + test isolation.
    """

    # ------------------------------------------------------------------
    # Sync clients (every typed @property accessor)
    # ------------------------------------------------------------------

    @property
    def overseerr(self) -> Optional["OverseerrClient"]:
        from radbot.tools.overseerr.overseerr_client import get_overseerr_client

        return get_overseerr_client()

    @property
    def lidarr(self) -> Optional["LidarrClient"]:
        from radbot.tools.lidarr.lidarr_client import get_lidarr_client

        return get_lidarr_client()

    @property
    def jira(self) -> Optional[Any]:
        """Atlassian `Jira` client. Typed as `Any` because the upstream
        `atlassian` package does not ship type stubs."""
        from radbot.tools.jira.jira_client import get_jira_client

        return get_jira_client()

    @property
    def picnic(self) -> Optional["PicnicClientWrapper"]:
        from radbot.tools.picnic.picnic_client import get_picnic_client

        return get_picnic_client()

    @property
    def nomad(self) -> Optional["NomadClient"]:
        from radbot.tools.nomad.nomad_client import get_nomad_client

        return get_nomad_client()

    @property
    def ntfy(self) -> Optional["NtfyClient"]:
        from radbot.tools.ntfy.ntfy_client import get_ntfy_client

        return get_ntfy_client()

    @property
    def github(self) -> Optional["GitHubAppClient"]:
        from radbot.tools.github.github_app_client import get_github_client

        return get_github_client()

    @property
    def ha_rest(self) -> Optional["HomeAssistantRESTClient"]:
        from radbot.tools.homeassistant.ha_client_singleton import get_ha_client

        return get_ha_client()

    @property
    def ha_mcp(self) -> Optional["HAMcpClient"]:
        from radbot.tools.homeassistant.ha_mcp_client import get_ha_mcp_client

        return get_ha_mcp_client()

    # YouTube + Kideo are not exposed as properties: callers use the
    # module-level helpers (e.g. `youtube_client.get_video_details`,
    # `kideo_client.get_collection`), not the underlying client object
    # directly. The provider still resets them in `clear()` so admin
    # hot-reload remains correct.

    # ------------------------------------------------------------------
    # Async clients (HA WebSocket needs `await connect()` at factory time)
    # ------------------------------------------------------------------

    async def get_ha_ws(self) -> Optional["HomeAssistantWebSocketClient"]:
        """Async accessor for the HA WebSocket client. Connects on first
        use; subsequent calls return the cached connection."""
        from radbot.tools.homeassistant.ha_ws_singleton import get_ha_ws_client

        return await get_ha_ws_client()

    # ------------------------------------------------------------------
    # One-shot constructors (admin "Test Connection" endpoints)
    # ------------------------------------------------------------------
    #
    # These bypass the cached singleton on purpose — admin test endpoints
    # validate *unsaved* form values before the user commits them. Direct
    # client-class imports are confined here so the rest of the codebase
    # only ever talks to clients through the cached `@property` accessors.

    def make_oneshot_ha_mcp(
        self, url: str, token: str, timeout: float = 8.0
    ) -> "HAMcpClient":
        from radbot.tools.homeassistant.ha_mcp_client import HAMcpClient

        return HAMcpClient(url, token, timeout=timeout)

    def make_oneshot_github(
        self, app_id: str, installation_id: str, private_key: str
    ) -> "GitHubAppClient":
        from radbot.tools.github.github_app_client import GitHubAppClient

        return GitHubAppClient(str(app_id), str(installation_id), private_key)

    def make_oneshot_nomad(self, addr: str, token: str = "") -> "NomadClient":
        from radbot.tools.nomad.nomad_client import NomadClient

        return NomadClient(addr=addr, token=token)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Wipe every cached client.

        Called from:
        - `tests/conftest.py` autouse fixture (test isolation).
        - `web/api/admin.py` config hot-reload (replaces the legacy
          `_INTEGRATION_RESET_REGISTRY` loop).

        Each reset is wrapped in a try/except so one broken client never
        prevents the rest from being cleared (matches the legacy admin
        loop's fail-open behavior, but logs a warning so drift doesn't
        stay silent).
        """
        resets = [
            (
                "overseerr",
                "radbot.tools.overseerr.overseerr_client",
                "reset_overseerr_client",
            ),
            ("lidarr", "radbot.tools.lidarr.lidarr_client", "reset_lidarr_client"),
            ("jira", "radbot.tools.jira.jira_client", "reset_jira_client"),
            ("picnic", "radbot.tools.picnic.picnic_client", "reset_picnic_client"),
            ("nomad", "radbot.tools.nomad.nomad_client", "reset_nomad_client"),
            ("ntfy", "radbot.tools.ntfy.ntfy_client", "reset_ntfy_client"),
            ("youtube", "radbot.tools.youtube.youtube_client", "reset_youtube_client"),
            ("kideo", "radbot.tools.youtube.kideo_client", "reset_kideo_client"),
            ("github", "radbot.tools.github.github_app_client", "reset_github_client"),
            (
                "ha_rest",
                "radbot.tools.homeassistant.ha_client_singleton",
                "reset_ha_client",
            ),
            (
                "ha_ws",
                "radbot.tools.homeassistant.ha_ws_singleton",
                "reset_ha_ws_client",
            ),
            (
                "ha_mcp",
                "radbot.tools.homeassistant.ha_mcp_client",
                "reset_ha_mcp_client",
            ),
        ]
        for name, module_path, fn_name in resets:
            try:
                module = __import__(module_path, fromlist=[fn_name])
                getattr(module, fn_name)()
            except Exception as exc:
                logger.warning("ClientProvider.clear: %s reset failed: %s", name, exc)

    # ------------------------------------------------------------------
    # Startup validation
    # ------------------------------------------------------------------

    def validate_secrets(self) -> dict[str, str]:
        """Verify required config for every enabled integration.

        Called once at app startup. Returns a `{name: status}` dict where
        status is one of:
        - `"ok"` — all required fields present.
        - `"disabled"` — integration explicitly disabled in config.
        - `"missing: <field>, <field>"` — required fields absent.
        - `"error: <message>"` — config lookup raised.

        Missing-field statuses are logged at `ERROR` so a SRE sees them in
        the startup banner. Disabled integrations log at `INFO`. The method
        never raises — a single misconfigured integration must not block
        startup of the rest of the app.
        """
        results: dict[str, str] = {}
        for name, required in _REQUIRED_FIELDS.items():
            try:
                cfg = _resolve_config(name)
            except Exception as exc:
                results[name] = f"error: {exc}"
                logger.error(
                    "validate_secrets: %s config resolution raised: %s",
                    name,
                    exc,
                )
                continue
            if cfg is None or not cfg.get("enabled", True):
                results[name] = "disabled"
                logger.info("validate_secrets: %s disabled", name)
                continue
            missing = [f for f in required if not cfg.get(f)]
            if missing:
                results[name] = f"missing: {', '.join(missing)}"
                logger.error(
                    "validate_secrets: %s enabled but missing required fields: %s",
                    name,
                    ", ".join(missing),
                )
            else:
                results[name] = "ok"
        return results


# ---------------------------------------------------------------------------
# Required-field map for validate_secrets() (subset; opt-in)
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "overseerr": ("url", "api_key"),
    "lidarr": ("url", "api_key"),
    "jira": ("url", "email", "api_token"),
    "picnic": ("username", "password"),
    "nomad": ("addr",),
    "ntfy": ("topic",),
    "youtube": ("api_key",),
    "kideo": ("url",),
    "github": ("app_id", "installation_id", "private_key"),
    "home_assistant": ("url", "token"),
}


def _resolve_config(name: str) -> Optional[dict]:
    """Resolve config for the named integration.

    Most integrations route through `tools.shared.config_helper.get_integration_config`;
    Home Assistant uses the bespoke `config_loader.get_home_assistant_config()`
    path because all three HA clients (REST/WS/MCP) share that single config
    block.
    """
    if name == "home_assistant":
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_home_assistant_config() or {}
        return dict(cfg) if cfg else None

    from radbot.tools.shared.config_helper import get_integration_config

    field_envs: dict[str, dict[str, str]] = {
        "overseerr": {"url": "OVERSEERR_URL", "api_key": "OVERSEERR_API_KEY"},
        "lidarr": {"url": "LIDARR_URL", "api_key": "LIDARR_API_KEY"},
        "jira": {
            "url": "JIRA_URL",
            "email": "JIRA_EMAIL",
            "api_token": "JIRA_API_TOKEN",
        },
        "picnic": {
            "username": "PICNIC_USERNAME",
            "password": "PICNIC_PASSWORD",
            "country_code": "PICNIC_COUNTRY_CODE",
        },
        "nomad": {"addr": "NOMAD_ADDR", "token": "NOMAD_TOKEN"},
        "ntfy": {"url": "NTFY_URL", "topic": "NTFY_TOPIC", "token": "NTFY_TOKEN"},
        "youtube": {"api_key": "YOUTUBE_API_KEY"},
        "kideo": {"url": "KIDEO_URL", "api_key": "KIDEO_API_KEY"},
        "github": {
            "app_id": "GITHUB_APP_ID",
            "installation_id": "GITHUB_INSTALLATION_ID",
            "private_key": "GITHUB_PRIVATE_KEY",
        },
    }
    return get_integration_config(name, fields=field_envs.get(name, {}))


# ---------------------------------------------------------------------------
# Module-level singleton accessors
# ---------------------------------------------------------------------------

_provider: Optional[ClientProvider] = None


def get_provider() -> ClientProvider:
    """Return the process-wide `ClientProvider` (constructed on first call)."""
    global _provider
    if _provider is None:
        _provider = ClientProvider()
    return _provider


def reset_provider() -> None:
    """Test/admin helper: drop the singleton AND clear cached clients.

    `clear()` flushes the integration-side singletons; resetting the
    provider itself ensures any future `get_provider()` call constructs a
    fresh instance (matters mainly if `ClientProvider` ever grows
    instance state — today it is stateless and forwards everything).
    """
    global _provider
    if _provider is not None:
        _provider.clear()
    _provider = None
