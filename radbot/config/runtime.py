"""Single place that derives live process state from the merged config.

### Why

Most integrations read config lazily (``get_integration_config()`` on every
call, singleton clients reset by ``ClientProvider.clear()``), so an admin
save takes effect on the next tool call. A handful of things do **not**:
they are derived from config once, at startup, and then cached in process
state that no singleton reset touches:

* the Gemini API key / Vertex settings pushed into ``os.environ`` by
  ``setup_vertex_environment()``
* agent model names on the live ADK agents
* the root logger level
* casa's Home Assistant tools (MCP tools bind a client + an HA-fetched tool
  list at build time)
* axel's dynamic MCP tools (same pattern, per configured MCP server)
* the TTS / STT service singletons (voice, language, model)
* the Gmail / Calendar service caches
* the Qdrant memory service

Each of those used to be a special case in ``web/api/admin.py`` (or simply
missing, which is why a new HA IP or Google key needed a restart). This
module replaces the special cases with one idempotent function that both
startup and every admin save call: ``apply_runtime_config()``.

### Cost gating

Every step is cheap and runs on every save, except the two that talk to the
network to rebuild agent tool lists (HA MCP, dynamic MCP) and the memory
service re-init. Those run only when their inputs can have changed (the
``integrations`` / ``vector_db`` section, or a related credential). Steps
are fail-soft: one broken step never blocks the rest, and the returned
status dict says what ran.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Credentials whose save should trigger the network-bound HA tool rebuild.
_HA_CREDENTIALS = {"ha_token"}
# Credentials whose save should trigger the dynamic MCP tool rebuild.
_MCP_CREDENTIAL_PREFIX = "mcp_"
# Credentials whose save should re-init the Qdrant memory service.
_MEMORY_CREDENTIALS = {"qdrant_api_key"}


class _Trigger:
    """What changed — lets expensive steps decide whether to run."""

    def __init__(
        self, reason: str, section: Optional[str], credential: Optional[str]
    ) -> None:
        self.reason = reason
        self.section = section
        self.credential = credential

    @property
    def integrations_changed(self) -> bool:
        return self.section == "integrations"

    @property
    def ha_changed(self) -> bool:
        return self.integrations_changed or self.credential in _HA_CREDENTIALS

    @property
    def mcp_changed(self) -> bool:
        return self.integrations_changed or bool(
            self.credential and self.credential.startswith(_MCP_CREDENTIAL_PREFIX)
        )

    @property
    def memory_changed(self) -> bool:
        return self.section == "vector_db" or self.credential in _MEMORY_CREDENTIALS


# ---------------------------------------------------------------------------
# Steps — each takes the trigger, returns a short status string.
# ---------------------------------------------------------------------------


def _step_genai_env(t: _Trigger) -> str:
    """Re-push the Gemini key / Vertex settings into ``os.environ``.

    ADK builds a fresh ``Gemini`` client per LLM call from the environment,
    so updating env is sufficient — no model-level cache to clear.
    """
    import os

    from radbot.config import config_manager
    from radbot.config.adk_config import setup_vertex_environment

    setup_vertex_environment()
    # setup_vertex_environment only *sets* GOOGLE_CLOUD_PROJECT; mirror the
    # admin path's old behaviour of dropping it when the config clears it.
    if not config_manager.get_google_cloud_project():
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
    return "ok"


def _step_agent_models(t: _Trigger) -> str:
    """Push DB model overrides onto the live agent tree."""
    from radbot.agent.assembly import _resolve_assembly
    from radbot.config import config_manager

    config_manager.apply_model_config(_resolve_assembly().root_agent)
    return "ok"


def _step_logging(t: _Trigger) -> str:
    """Reapply ``logging.level`` to the root logger (handlers untouched)."""
    from radbot.config.config_loader import config_loader
    from radbot.logging_config import setup_logging

    level = (config_loader.get_logging_config() or {}).get("level")
    if not level:
        return "skipped (no level configured)"
    setup_logging(level=str(level))
    return f"ok ({str(level).upper()})"


def _step_integration_clients(t: _Trigger) -> str:
    """Drop every cached integration client so the next call re-reads config."""
    from radbot.clients.provider import get_provider

    get_provider().clear()
    # Gmail / Calendar keep their own per-account service caches outside
    # the provider (OAuth + service-account objects). Clear them too so a
    # new ``gmail_oauth_client`` / ``google_service_account`` is honoured.
    try:
        from radbot.tools.gmail import gmail_auth, gmail_manager

        gmail_auth._gmail_services.clear()
        gmail_manager._gmail_managers.clear()
    except Exception as e:  # pragma: no cover - optional module
        logger.debug("gmail cache clear skipped: %s", e)
    try:
        from radbot.tools.calendar import calendar_auth

        calendar_auth._calendar_service = None
        calendar_auth._workspace_services.clear()
    except Exception as e:  # pragma: no cover - optional module
        logger.debug("calendar cache clear skipped: %s", e)
    return "ok"


def _step_filesystem(t: _Trigger) -> str:
    from radbot.filesystem.adapter import reload_filesystem_config

    reload_filesystem_config()
    return "ok"


def _step_ha_tools(t: _Trigger) -> str:
    """Rebuild casa's HA tool set (network: HA MCP ``tools/list``)."""
    if not t.ha_changed:
        return "skipped"
    from radbot.agent.home_agent.factory import refresh_home_assistant_tools

    n = refresh_home_assistant_tools()
    return f"ok ({n} tools)"


def _step_mcp_tools(t: _Trigger) -> str:
    """Rebuild axel's dynamic MCP tools (network: restarts MCP clients)."""
    if not t.mcp_changed:
        return "skipped"
    from radbot.agent.execution_agent.factory import refresh_axel_mcp_tools

    n = refresh_axel_mcp_tools()
    return f"ok ({n} tools)"


def _step_media_services(t: _Trigger) -> str:
    """Recreate the TTS / STT singletons from the current ``tts`` / ``stt`` sections."""
    from radbot.config.config_loader import config_loader
    from radbot.tools.stt.stt_service import STTService
    from radbot.tools.tts.tts_service import TTSService

    cfg = config_loader.get_config()
    tts_cfg = cfg.get("tts", {}) or {}
    stt_cfg = cfg.get("stt", {}) or {}

    TTSService.reset_instance()
    if tts_cfg.get("enabled", True):
        TTSService.create_instance(
            voice_name=tts_cfg.get("voice_name"),
            language_code=tts_cfg.get("language_code"),
            speaking_rate=tts_cfg.get("speaking_rate"),
            pitch=tts_cfg.get("pitch"),
        )
    STTService.reset_instance()
    if stt_cfg.get("enabled", True):
        STTService.create_instance(
            language_code=stt_cfg.get("language_code"),
            model=stt_cfg.get("model"),
            enable_automatic_punctuation=stt_cfg.get(
                "enable_automatic_punctuation", True
            ),
        )
    return "ok"


def _step_memory_service(t: _Trigger) -> str:
    """Re-init the Qdrant memory service and attach it to every root agent."""
    if not t.memory_changed:
        return "skipped"
    from radbot.agent.assembly import _resolve_assembly, initialize_memory_service

    mem_svc = initialize_memory_service()
    if not mem_svc:
        return "failed (memory service unavailable)"
    for agent in _resolve_assembly().root_agents.values():
        agent._memory_service = mem_svc
    return "ok"


# Ordered: env + models first (cheapest, most load-bearing), then caches,
# then the agent tool rebuilds that depend on fresh clients.
_STEPS: list[tuple[str, Callable[[_Trigger], str]]] = [
    ("genai_env", _step_genai_env),
    ("agent_models", _step_agent_models),
    ("logging", _step_logging),
    ("integration_clients", _step_integration_clients),
    ("filesystem", _step_filesystem),
    ("ha_tools", _step_ha_tools),
    ("mcp_tools", _step_mcp_tools),
    ("media_services", _step_media_services),
    ("memory_service", _step_memory_service),
]


def apply_runtime_config(
    reason: str = "startup",
    *,
    section: Optional[str] = None,
    credential: Optional[str] = None,
) -> Dict[str, str]:
    """Derive all config-dependent process state from the current merged config.

    Call after ``config_loader.load_db_config()`` — at startup (once the
    assembly is built) and after every admin save. Safe to call repeatedly.

    Args:
        reason: Free-text label for logs (``"startup"``, ``"admin"``).
        section: The ``config:<section>`` just saved, if any.
        credential: The credential name just saved, if any.

    Returns:
        ``{step_name: status}``; status is ``"ok…"``, ``"skipped…"`` or
        ``"error: <msg>"``. Never raises.

    Runs synchronously and may do network I/O for the gated steps, so call
    it from a worker thread inside async request handlers.
    """
    trigger = _Trigger(reason, section, credential)
    results: Dict[str, str] = {}
    for name, step in _STEPS:
        try:
            results[name] = step(trigger)
        except Exception as e:
            results[name] = f"error: {e}"
            logger.warning(
                "apply_runtime_config[%s] step %s failed: %s", reason, name, e
            )
    ran = [f"{k}={v}" for k, v in results.items() if not v.startswith("skipped")]
    logger.info(
        "apply_runtime_config reason=%s section=%s credential=%s → %s",
        reason,
        section,
        credential,
        ", ".join(ran),
    )
    return results
