"""Smoke tests for `radbot.web.app` lifespan startup.

The v0.164 production incident on 2026-05-01 was caused by the deprecated
`@app.on_event("startup")` decorator silently no-op'ing under the new
runtime, so `build_default_assembly()` never ran and every request 500'd.

These tests close the gap by importing `radbot.web.app`, driving the ASGI
lifespan from a stub manifest, and asserting the cached assembly exists
and the static-file mount executed.

We can't run the full lifespan (DB / MCP / scheduler / ntfy require live
infra), so we mock at the seams that are pure infra (`init_all_schemas`,
`SchedulerEngine`, `start_ntfy_subscriber`, `mount_static_files`,
`reload_filesystem_config`, `setup_vertex_environment`, the migration
script) and let the actual `_startup` body run for the parts that matter
(building the assembly, applying model overrides).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def patched_startup_seams():
    """Patch the heavy-infra seams of `_startup` so we can run it offline."""
    with (
        patch("radbot.tools.schemas.init_all_schemas") as p_schema,
        patch("scripts.migrate_todo_to_telos.main"),
        patch("radbot.filesystem.adapter.reload_filesystem_config"),
        patch("radbot.config.adk_config.setup_vertex_environment"),
        patch("radbot.web.app.mount_static_files") as p_static,
        patch("radbot.tools.scheduler.engine.SchedulerEngine") as p_engine,
        patch(
            "radbot.tools.ntfy.ntfy_subscriber.start_ntfy_subscriber",
            new_callable=AsyncMock,
        ) as p_ntfy,
        patch("radbot.tools.tts.tts_service.TTSService"),
        patch("radbot.tools.stt.stt_service.STTService"),
        patch("radbot.tools.mcp.mcp_client_factory.MCPClientFactory"),
        patch("radbot.config.config_loader.config_loader.load_db_config") as p_db_cfg,
        patch(
            "radbot.config.config_loader.config_loader.get_enabled_mcp_servers",
            return_value=[],
        ),
        patch(
            "radbot.config.config_loader.config_loader.get_mcp_servers",
            return_value=[],
        ),
    ):
        # Make scheduler engine async no-ops
        engine = MagicMock()
        engine.start = AsyncMock()
        engine.shutdown = AsyncMock()
        p_engine.create_instance.return_value = engine
        p_engine.get_instance.return_value = engine

        yield {
            "schema": p_schema,
            "static": p_static,
            "engine": p_engine,
            "load_db_config": p_db_cfg,
            "ntfy": p_ntfy,
        }


def _reset_assembly_cache():
    from radbot.agent import assembly

    assembly._cached_assembly = None


@pytest.mark.asyncio
async def test_lifespan_startup_runs_init_all_schemas_and_builds_assembly(
    patched_startup_seams,
):
    """The ASGI lifespan must invoke `init_all_schemas` and build the assembly.

    This is the precise failure mode the v0.164 incident exhibited: lifespan
    completed silently, schemas were not initialized, and assembly was never
    built. Asserting on the call counts ensures the lifespan body actually
    runs end-to-end.
    """
    _reset_assembly_cache()
    seams = patched_startup_seams

    from radbot.web.app import lifespan

    app = MagicMock()  # the lifespan only uses app for typing
    async with lifespan(app):
        # Inside the lifespan: startup completed, app would be serving.
        seams["schema"].assert_called()
        seams["load_db_config"].assert_called()
        seams["static"].assert_called_once()

        # Most important assertion: the agent assembly was actually built
        # and cached. If this fails, the production incident recurs.
        from radbot.agent.assembly import _resolve_assembly

        assembly = _resolve_assembly()
        assert assembly.root_agent.name == "beto"
        assert len(assembly.root_agent.sub_agents) >= 1


@pytest.mark.asyncio
async def test_lifespan_startup_failure_propagates(patched_startup_seams):
    """If schema init raises, the lifespan must surface it (not swallow).

    Pre-fix, `_startup` swallowed exceptions in a bare `except` and let the
    app boot in a half-initialized state. The fix re-raises, so a busted
    deploy refuses to bind the port and the orchestrator reschedules.
    """
    _reset_assembly_cache()
    seams = patched_startup_seams
    seams["schema"].side_effect = RuntimeError("simulated schema failure")

    from radbot.web.app import lifespan

    app = MagicMock()

    with pytest.raises(RuntimeError, match="simulated schema failure"):
        async with lifespan(app):
            pass  # should not be reached
