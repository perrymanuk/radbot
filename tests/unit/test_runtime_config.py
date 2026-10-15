"""Tests for the universal hot-reload entry point (config/runtime.py)."""

from unittest.mock import patch

from radbot.config import runtime


def _ok(name):
    def step(t):
        return "ok"

    step.__name__ = name
    return step


def test_apply_runtime_config_is_fail_soft_and_runs_every_step():
    calls = []

    def boom(t):
        calls.append("boom")
        raise RuntimeError("kaboom")

    def fine(t):
        calls.append("fine")
        return "ok"

    with patch.object(runtime, "_STEPS", [("boom", boom), ("fine", fine)]):
        results = runtime.apply_runtime_config("test")

    assert calls == ["boom", "fine"]
    assert results["boom"].startswith("error: kaboom")
    assert results["fine"] == "ok"


def test_network_bound_steps_gate_on_trigger():
    # Arrange: stub the expensive rebuilds so no network is touched
    with (
        patch(
            "radbot.agent.home_agent.factory.refresh_home_assistant_tools",
            return_value=3,
        ) as ha,
        patch(
            "radbot.agent.execution_agent.factory.refresh_axel_mcp_tools",
            return_value=2,
        ) as mcp,
    ):
        # Act: an unrelated section save must not rebuild agent tools
        assert runtime._step_ha_tools(runtime._Trigger("t", "tts", None)) == "skipped"
        assert runtime._step_mcp_tools(runtime._Trigger("t", "tts", None)) == "skipped"
        ha.assert_not_called()
        mcp.assert_not_called()

        # Act: HA token / integrations section / mcp credential do
        assert "3 tools" in runtime._step_ha_tools(
            runtime._Trigger("t", None, "ha_token")
        )
        assert "2 tools" in runtime._step_mcp_tools(
            runtime._Trigger("t", "integrations", None)
        )
        assert "2 tools" in runtime._step_mcp_tools(
            runtime._Trigger("t", None, "mcp_ctx7_auth_token")
        )


def test_memory_step_gates_on_vector_db_or_qdrant_key():
    assert runtime._Trigger("t", "vector_db", None).memory_changed
    assert runtime._Trigger("t", None, "qdrant_api_key").memory_changed
    assert not runtime._Trigger("t", "integrations", None).memory_changed


def test_media_services_step_recreates_singletons_from_config():
    from types import SimpleNamespace

    from radbot.tools.stt.stt_service import STTService
    from radbot.tools.tts.tts_service import TTSService

    fake_cfg = SimpleNamespace(
        get_config=lambda: {
            "tts": {"enabled": True, "voice_name": "en-US-Neural2-D"},
            "stt": {"enabled": False},
        }
    )
    with patch("radbot.config.config_loader.config_loader", fake_cfg):
        assert runtime._step_media_services(runtime._Trigger("t", "tts", None)) == "ok"
    assert TTSService.get_instance().voice_name == "en-US-Neural2-D"
    assert STTService.get_instance() is None
    TTSService.reset_instance()
