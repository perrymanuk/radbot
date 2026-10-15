"""Hot-reload regression tests: HA tool refresh on casa + Google key env push."""

import os
from types import SimpleNamespace
from unittest.mock import patch

from radbot.agent.home_agent import factory as home_factory


def _tool(name):
    return SimpleNamespace(name=name)


def test_refresh_home_assistant_tools_swaps_ha_tools_in_place():
    # Arrange: casa built with two REST HA tools followed by other tools
    old_ha = [_tool("list_ha_entities"), _tool("turn_on_ha_entity")]
    other = [_tool("search_overseerr_media_tool"), _tool("store_agent_memory")]
    casa = SimpleNamespace(name="casa", tools=old_ha + other)
    home_factory._installed_ha_tools[:] = old_ha
    new_ha = [_tool("HassTurnOn"), _tool("HassTurnOff"), _tool("HassLightSet")]

    # Act
    with patch.object(home_factory, "_build_ha_tools", return_value=new_ha):
        count = home_factory.refresh_home_assistant_tools(casa)

    # Assert: old HA tools gone, new ones first, other tools untouched
    assert count == 3
    assert casa.tools[:3] == new_ha
    assert casa.tools[3:] == other
    assert home_factory._installed_ha_tools == new_ha


def test_refresh_home_assistant_tools_returns_zero_without_assembly():
    with patch(
        "radbot.agent.assembly._resolve_assembly",
        side_effect=RuntimeError("not built"),
    ):
        assert home_factory.refresh_home_assistant_tools() == 0


def test_build_ha_tools_falls_back_to_rest_when_mcp_unreachable():
    fake_cfg = SimpleNamespace(
        get_home_assistant_config=lambda: {"use_mcp": True, "url": "http://x"}
    )
    fake_provider = SimpleNamespace(ha_mcp=None)
    with (
        patch("radbot.config.config_loader.config_loader", fake_cfg),
        patch("radbot.clients.provider.get_provider", return_value=fake_provider),
    ):
        tools = home_factory._build_ha_tools()
    names = {getattr(t, "name", None) or getattr(t, "__name__", "") for t in tools}
    assert "list_ha_entities" in names
    assert len(tools) == 6


def test_store_google_api_key_updates_process_env():
    import asyncio

    from radbot.web.api import admin

    class _Store:
        def set(self, *a, **k):
            pass

    class _Req:
        async def json(self):
            return {"name": "google_api_key", "value": "new-key-123"}

    async def _fake_apply(section=None, credential=None):
        return {"genai_env": "ok", "credential": credential}

    with (
        patch.object(admin, "_require_store", return_value=_Store()),
        patch.object(admin, "_apply_runtime_config", _fake_apply),
        patch.dict(os.environ, {"GOOGLE_API_KEY": "old"}),
    ):
        result = asyncio.run(admin.store_credential(_Req(), None))
        assert result["status"] == "ok"
        assert result["reload"]["credential"] == "google_api_key"
        assert os.environ["GOOGLE_API_KEY"] == "new-key-123"
