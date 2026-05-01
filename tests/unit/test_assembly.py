"""Unit tests for `radbot.agent.assembly`.

These tests use minimal stub agents and `build_assembly(custom_defs)` to
exercise the manifest walker without spinning up the full sub-agent stack.
That seam was the missing test surface flagged in EX38 finding #3.
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

from radbot.agent.assembly import (
    AGENT_DEFS,
    AgentDef,
    _resolve_assembly,
    build_assembly,
    reset_cached_assembly,
)
from radbot.callbacks.terse_protocol import (
    terse_protocol_after_model_callback,
    terse_protocol_before_model_callback,
)


def _stub_agent(name: str, *, sub_agents=None, tools=None) -> Any:
    """Build a SimpleNamespace-shaped stub that quacks like an Agent."""
    agent = MagicMock(name=f"Agent({name})", spec=[])
    agent.name = name
    agent.sub_agents = sub_agents or []
    agent.tools = tools or []
    agent.before_model_callback = None
    agent.after_model_callback = None
    return agent


def _stub_factory(name: str):
    return lambda: _stub_agent(name)


def _stub_failing_factory(name: str, exc: Exception):
    def _f():
        raise exc

    return _f


def _stub_returning_none():
    return None


@pytest.fixture(autouse=True)
def _reset_between_tests():
    """Each test starts with no cached assembly."""
    reset_cached_assembly()
    yield
    reset_cached_assembly()


@pytest.fixture
def beto_only_defs():
    """Manifest with no sub-agents — `_build_beto` still constructs the root."""
    return []


def _patch_beto(monkeypatch, *, sub_agents=None):
    """Replace `_build_beto` with a stub so we don't pull the full Agent stack."""
    fake_root = _stub_agent("beto", sub_agents=sub_agents or [])
    monkeypatch.setattr(
        "radbot.agent.assembly._build_beto",
        lambda subs: (fake_root.__setattr__("sub_agents", subs) or fake_root),
    )
    return fake_root


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_resolve_assembly_raises_before_build(self):
        """Pre-build access should fail loudly, not return a stub."""
        with pytest.raises(RuntimeError, match="has not been built"):
            _resolve_assembly()

    def test_build_default_assembly_caches(self, monkeypatch):
        """Repeated calls return the same Assembly without rebuilding."""
        _patch_beto(monkeypatch)
        monkeypatch.setattr("radbot.agent.assembly.AGENT_DEFS", [])

        from radbot.agent.assembly import build_default_assembly

        a1 = build_default_assembly()
        a2 = build_default_assembly()
        assert a1 is a2


# ---------------------------------------------------------------------------
# Sub-agent assembly + callback wiring
# ---------------------------------------------------------------------------


class TestCallbackWiring:
    def test_terse_callbacks_attached_only_to_marked_agents(self, monkeypatch):
        """`terse_protocol=True` agents get the terse callbacks; others don't."""
        _patch_beto(monkeypatch)

        defs = [
            AgentDef(
                name="planner",
                factory=_stub_factory("planner"),
                role="subagent",
                terse_protocol=True,
            ),
            AgentDef(
                name="casa",
                factory=_stub_factory("casa"),
                role="subagent",
                terse_protocol=False,
            ),
        ]

        assembly = build_assembly(defs)

        sub_by_name = {sa.name: sa for sa in assembly.root_agent.sub_agents}

        planner_before = sub_by_name["planner"].before_model_callback
        assert terse_protocol_before_model_callback in planner_before

        planner_after = sub_by_name["planner"].after_model_callback
        assert terse_protocol_after_model_callback in planner_after

        casa_before = sub_by_name["casa"].before_model_callback
        assert terse_protocol_before_model_callback not in casa_before

        casa_after = sub_by_name["casa"].after_model_callback
        assert terse_protocol_after_model_callback not in casa_after


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


class TestFailureModes:
    def test_subagent_factory_failure_raises(self, monkeypatch):
        """A `role='subagent'` factory that raises is a deploy-blocker."""
        _patch_beto(monkeypatch)

        defs = [
            AgentDef(
                name="broken",
                factory=_stub_failing_factory("broken", RuntimeError("bad model")),
                role="subagent",
            ),
        ]

        with pytest.raises(RuntimeError, match="bad model"):
            build_assembly(defs)

    def test_subagent_factory_returning_none_raises(self, monkeypatch):
        """A factory that silently returns None still breaks routing."""
        _patch_beto(monkeypatch)

        defs = [
            AgentDef(name="empty", factory=_stub_returning_none, role="subagent"),
        ]

        with pytest.raises(RuntimeError, match="returned None"):
            build_assembly(defs)

    def test_alternate_root_failure_logged_and_omitted(self, monkeypatch, caplog):
        """A non-beto root failure logs ERROR and is omitted from `root_agents`."""
        _patch_beto(monkeypatch)

        defs = [
            AgentDef(
                name="scout_root",
                factory=_stub_failing_factory("scout", RuntimeError("nope")),
                role="root",
            ),
        ]

        with caplog.at_level("ERROR", logger="radbot.agent.assembly"):
            assembly = build_assembly(defs)

        assert "scout_root" not in assembly.root_agents
        assert "beto" in assembly.root_agents
        # Make sure we logged the failure rather than swallowing it silently.
        assert any("scout_root" in rec.message for rec in caplog.records)

    def test_beto_in_manifest_root_role_raises(self, monkeypatch):
        """Beto is constructed by `_build_beto`, not via `AGENT_DEFS` root."""
        _patch_beto(monkeypatch)

        defs = [
            AgentDef(name="beto", factory=_stub_factory("beto"), role="root"),
        ]

        with pytest.raises(RuntimeError, match="must be assembled"):
            build_assembly(defs)


# ---------------------------------------------------------------------------
# Memory service propagation
# ---------------------------------------------------------------------------


class TestMemoryService:
    def test_memory_service_attached_to_all_roots(self, monkeypatch):
        """`build_assembly(memory_service=…)` should attach to beto + alternate roots."""
        _patch_beto(monkeypatch)

        scout_root_stub = _stub_agent("scout")
        defs = [
            AgentDef(
                name="scout_root",
                factory=lambda: scout_root_stub,
                role="root",
            ),
        ]

        fake_memory = MagicMock(name="QdrantMemoryService")
        assembly = build_assembly(defs, memory_service=fake_memory)

        assert assembly.root_agent._memory_service is fake_memory
        assert assembly.root_agents["scout"]._memory_service is fake_memory


# ---------------------------------------------------------------------------
# Default manifest sanity
# ---------------------------------------------------------------------------


class TestDefaultManifest:
    def test_manifest_includes_expected_agents(self):
        names = {d.name for d in AGENT_DEFS}
        # Must contain the active named sub-agents and at least one alternate
        # root (scout_root).
        assert "casa" in names
        assert "planner" in names
        assert "comms" in names
        assert "axel" in names
        assert "kidsvid" in names
        assert "scout" in names
        assert "search_agent" in names
        assert "code_execution_agent" in names
        assert "scout_root" in names

    def test_terse_protocol_marked_only_on_axel_and_planner(self):
        """EX38 locked decision: terse protocol applies to axel + planner."""
        terse = {d.name for d in AGENT_DEFS if d.terse_protocol}
        assert terse == {"axel", "planner"}


# ---------------------------------------------------------------------------
# Schema init centralization
# ---------------------------------------------------------------------------


class TestSchemaInit:
    def test_init_all_schemas_calls_every_module(self):
        """Each registered (module, fn) pair should be invoked exactly once."""
        from radbot.tools.schemas import SCHEMA_INITS, init_all_schemas

        invoked: List[str] = []

        def _make_recorder(label: str):
            def _r(*args, **kwargs):
                invoked.append(label)
                return True

            return _r

        with patch(
            "radbot.tools.schemas._resolve",
            side_effect=lambda mod, fn: _make_recorder(f"{mod}.{fn}"),
        ):
            init_all_schemas()

        assert len(invoked) == len(SCHEMA_INITS)
        # Every label corresponds to one of the manifest entries
        labels = {f"{m}.{f}" for _, m, f in SCHEMA_INITS}
        assert set(invoked) == labels
