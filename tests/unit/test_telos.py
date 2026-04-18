"""Unit tests for the telos module.

Covers:
  * markdown round-trip (parse → render → parse)
  * loader anchor/full-block assembly + size caps
  * inject_telos_context callback session-start gating
  * callback no-op on empty DB
  * tool layer writes (silent + confirm-required both work)
  * has_identity sentinel derivation
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from radbot.tools.telos import loader as telos_loader
from radbot.tools.telos.callback import (
    _BOOTSTRAP_STATE_KEY,
    inject_telos_context,
)
from radbot.tools.telos.markdown_io import parse_telos_markdown, render_telos_markdown
from radbot.tools.telos.models import (
    IDENTITY_REF,
    Entry,
    Section,
)


# ---------------------------------------------------------------------------
# Markdown round-trip
# ---------------------------------------------------------------------------


class TestMarkdownRoundTrip:
    def test_basic_round_trip(self):
        src = (
            "# TELOS\n\n"
            "## IDENTITY\n\n"
            "Perry, based in Austin, builds agents.\n\n"
            "## PROBLEMS\n\n"
            "- P1: people waste time on busywork\n\n"
            "## GOALS\n\n"
            "- G1: ship radbot v1\n"
            "- G2: sleep more\n\n"
            "## WISDOM\n\n"
            "- the magic is in the work you're avoiding\n"
        )
        entries = parse_telos_markdown(src)
        rendered = render_telos_markdown(entries)
        entries2 = parse_telos_markdown(rendered)

        # Stable counts + ref_codes survive the round-trip.
        sections1 = sorted(e.section.value for e in entries)
        sections2 = sorted(e.section.value for e in entries2)
        assert sections1 == sections2

        refs1 = sorted(e.ref_code or "" for e in entries)
        refs2 = sorted(e.ref_code or "" for e in entries2)
        assert refs1 == refs2

        # Content preserved.
        by_ref = {e.ref_code: e.content for e in entries if e.ref_code}
        by_ref2 = {e.ref_code: e.content for e in entries2 if e.ref_code}
        for ref, content in by_ref.items():
            assert by_ref2.get(ref) == content

    def test_identity_single_entry(self):
        entries = parse_telos_markdown(
            "## IDENTITY\n\nLine one.\nLine two.\n"
        )
        idents = [e for e in entries if e.section == Section.IDENTITY]
        assert len(idents) == 1
        assert idents[0].ref_code == IDENTITY_REF
        assert "Line one." in idents[0].content
        assert "Line two." in idents[0].content

    def test_unknown_section_preserved(self):
        entries = parse_telos_markdown("## CUSTOM THING\n\n- something weird\n")
        assert len(entries) == 1
        assert entries[0].metadata.get("raw_section_name") == "CUSTOM THING"

        rendered = render_telos_markdown(entries)
        assert "## CUSTOM THING" in rendered
        assert "something weird" in rendered

    def test_empty_input(self):
        assert parse_telos_markdown("") == []

    def test_render_empty(self):
        assert render_telos_markdown([]).strip() == "# TELOS"


# ---------------------------------------------------------------------------
# Loader: build_telos_tiers()
# ---------------------------------------------------------------------------


def _fake_entry(
    section: Section,
    content: str,
    ref_code: str | None = None,
    metadata: dict | None = None,
    created_at: datetime | None = None,
) -> Entry:
    return Entry(
        entry_id="abcd",
        section=section,
        ref_code=ref_code,
        content=content,
        metadata=metadata or {},
        status="active",
        sort_order=0,
        created_at=created_at or datetime(2026, 4, 18, tzinfo=timezone.utc),
        updated_at=created_at or datetime(2026, 4, 18, tzinfo=timezone.utc),
    )


class TestLoader:
    def test_empty_db_returns_empty_strings(self):
        grouped = {s: [] for s in Section}
        with patch.object(telos_loader.telos_db, "list_all_active", return_value=grouped), \
             patch.object(telos_loader.telos_db, "recent_journal", return_value=[]):
            anchor, full_block = telos_loader.build_telos_tiers()
        assert anchor == ""
        assert full_block == ""

    def test_populated_db_builds_both_tiers(self):
        grouped = {s: [] for s in Section}
        grouped[Section.IDENTITY] = [
            _fake_entry(Section.IDENTITY, "Perry, Austin, builds agents", "ME")
        ]
        grouped[Section.MISSION] = [
            _fake_entry(Section.MISSION, "Make radbot self-aware", "M1")
        ]
        grouped[Section.PROBLEMS] = [
            _fake_entry(Section.PROBLEMS, "agents forget who the user is", "P1"),
        ]
        grouped[Section.GOALS] = [
            _fake_entry(Section.GOALS, "Ship telos", "G1"),
            _fake_entry(Section.GOALS, "Sleep 8h", "G2"),
        ]
        journal = [
            _fake_entry(Section.JOURNAL, "Wrote the Telos spec"),
        ]
        with patch.object(telos_loader.telos_db, "list_all_active", return_value=grouped), \
             patch.object(telos_loader.telos_db, "recent_journal", return_value=journal):
            anchor, full_block = telos_loader.build_telos_tiers()

        assert anchor
        assert full_block
        assert "Perry" in anchor
        assert "Make radbot self-aware" in anchor
        assert "IDENTITY" in full_block
        assert "G1" in full_block
        assert "G2" in full_block
        assert "Wrote the Telos spec" in full_block

    def test_anchor_size_cap(self):
        # Pathological: long identity + long mission → anchor still under cap.
        grouped = {s: [] for s in Section}
        grouped[Section.IDENTITY] = [
            _fake_entry(Section.IDENTITY, "x" * 2000, "ME")
        ]
        grouped[Section.MISSION] = [
            _fake_entry(Section.MISSION, "y" * 2000, "M1")
        ]
        grouped[Section.GOALS] = [
            _fake_entry(Section.GOALS, f"goal {i}", f"G{i}") for i in range(20)
        ]
        with patch.object(telos_loader.telos_db, "list_all_active", return_value=grouped), \
             patch.object(telos_loader.telos_db, "recent_journal", return_value=[]):
            anchor, _ = telos_loader.build_telos_tiers()
        assert len(anchor.encode("utf-8")) <= telos_loader.ANCHOR_CAP_BYTES

    def test_full_block_size_cap(self):
        grouped = {s: [] for s in Section}
        grouped[Section.IDENTITY] = [_fake_entry(Section.IDENTITY, "Perry", "ME")]
        grouped[Section.MISSION] = [_fake_entry(Section.MISSION, "Mission text", "M1")]
        grouped[Section.GOALS] = [
            _fake_entry(Section.GOALS, "A" * 200, f"G{i}") for i in range(30)
        ]
        journal = [
            _fake_entry(Section.JOURNAL, "J" * 150) for _ in range(30)
        ]
        with patch.object(telos_loader.telos_db, "list_all_active", return_value=grouped), \
             patch.object(telos_loader.telos_db, "recent_journal", return_value=journal):
            _, full_block = telos_loader.build_telos_tiers()
        assert len(full_block.encode("utf-8")) <= telos_loader.FULL_BLOCK_CAP_BYTES


# ---------------------------------------------------------------------------
# Callback: session-start gating
# ---------------------------------------------------------------------------


def _make_ctx(state: dict | None = None):
    ctx = MagicMock()
    ctx.state = state if state is not None else {}
    return ctx


def _make_req(existing_system_instruction: str | None = None):
    req = MagicMock()
    req.config = MagicMock()
    req.config.system_instruction = existing_system_instruction
    return req


class TestInjectTelosContext:
    def test_noop_on_empty_db(self):
        with patch(
            "radbot.tools.telos.callback.build_telos_tiers",
            return_value=("", ""),
        ):
            ctx = _make_ctx()
            req = _make_req("original")
            result = inject_telos_context(ctx, req)
        assert result is None
        assert req.config.system_instruction == "original"

    def test_first_turn_injects_anchor_plus_full_block(self):
        with patch(
            "radbot.tools.telos.callback.build_telos_tiers",
            return_value=("ANCHOR_TEXT", "FULL_BLOCK_TEXT"),
        ):
            ctx = _make_ctx(state={})
            req = _make_req("base_instruction")
            inject_telos_context(ctx, req)

        si = req.config.system_instruction
        assert "base_instruction" in si
        assert "ANCHOR_TEXT" in si
        assert "FULL_BLOCK_TEXT" in si
        assert ctx.state[_BOOTSTRAP_STATE_KEY] is True

    def test_subsequent_turn_injects_anchor_only(self):
        with patch(
            "radbot.tools.telos.callback.build_telos_tiers",
            return_value=("ANCHOR_TEXT", "FULL_BLOCK_TEXT"),
        ):
            ctx = _make_ctx(state={_BOOTSTRAP_STATE_KEY: True})
            req = _make_req("base_instruction")
            inject_telos_context(ctx, req)

        si = req.config.system_instruction
        assert "ANCHOR_TEXT" in si
        assert "FULL_BLOCK_TEXT" not in si

    def test_first_turn_with_no_full_block_still_injects_anchor(self):
        with patch(
            "radbot.tools.telos.callback.build_telos_tiers",
            return_value=("ANCHOR_TEXT", ""),
        ):
            ctx = _make_ctx(state={})
            req = _make_req(None)
            inject_telos_context(ctx, req)
        assert "ANCHOR_TEXT" in req.config.system_instruction
        # With no full block, we still don't flip the bootstrap flag (so next
        # time a full block becomes available it'll inject).
        assert not ctx.state.get(_BOOTSTRAP_STATE_KEY)

    def test_handles_none_system_instruction(self):
        with patch(
            "radbot.tools.telos.callback.build_telos_tiers",
            return_value=("ANCHOR_TEXT", ""),
        ):
            ctx = _make_ctx()
            req = _make_req(None)
            inject_telos_context(ctx, req)
        assert req.config.system_instruction == "ANCHOR_TEXT"

    def test_handles_db_failure_gracefully(self):
        with patch(
            "radbot.tools.telos.callback.build_telos_tiers",
            side_effect=RuntimeError("db down"),
        ):
            ctx = _make_ctx()
            req = _make_req("base")
            result = inject_telos_context(ctx, req)
        # Should not raise; system_instruction left unchanged.
        assert result is None
        assert req.config.system_instruction == "base"


# ---------------------------------------------------------------------------
# Agent wiring: callback attached to beto only, NOT to sub-agents
# ---------------------------------------------------------------------------


class TestAgentWiring:
    def test_callback_on_beto_only(self):
        """inject_telos_context should be in root agent's before_model_callback,
        and absent from the shared sub-agent _before_cbs."""
        import radbot.agent.agent_core as core

        assert inject_telos_context in core.root_agent.before_model_callback

        # Sub-agents use _before_cbs (name is module-private but stable).
        # Each sub-agent's before_model_callback should not contain our callback.
        for sa in core.root_agent.sub_agents:
            before = sa.before_model_callback or []
            assert inject_telos_context not in before, (
                f"inject_telos_context leaked into sub-agent {sa.name}"
            )

    def test_telos_tools_on_beto(self):
        """Telos tools should be registered on beto's tool list."""
        import radbot.agent.agent_core as core
        from radbot.tools.telos import TELOS_TOOLS

        beto_tool_fns = set()
        for t in core.root_agent.tools:
            fn = getattr(t, "func", None)
            if fn:
                beto_tool_fns.add(fn.__name__)

        for tool in TELOS_TOOLS:
            fn = getattr(tool, "func", None)
            if fn:
                assert fn.__name__ in beto_tool_fns, (
                    f"Telos tool {fn.__name__} missing from beto"
                )


# ---------------------------------------------------------------------------
# Tool layer (with DB mocked)
# ---------------------------------------------------------------------------


class TestToolsLayer:
    def test_silent_add_journal(self):
        from radbot.tools.telos import telos_tools

        fake_row = _fake_entry(Section.JOURNAL, "Did a thing")
        with patch.object(telos_tools.telos_db, "add_entry", return_value=fake_row) as mock_add:
            out = telos_tools.telos_add_journal("Did a thing", event_type="decision")
        assert out["status"] == "success"
        assert out["entry"]["content"] == "Did a thing"
        _, kwargs = mock_add.call_args
        assert kwargs["metadata"]["event_type"] == "decision"

    def test_confirm_required_add_goal(self):
        from radbot.tools.telos import telos_tools

        fake_row = _fake_entry(
            Section.GOALS, "Ship telos", "G1",
            metadata={"deadline": "2026-12-31"},
        )
        with patch.object(telos_tools.telos_db, "add_entry", return_value=fake_row):
            out = telos_tools.telos_add_goal(
                "Ship telos", deadline="2026-12-31", kpi="v1 tagged"
            )
        assert out["status"] == "success"
        assert out["entry"]["ref_code"] == "G1"

    def test_get_section_filters_inactive_by_default(self):
        from radbot.tools.telos import telos_tools

        fake = [_fake_entry(Section.GOALS, "x", "G1")]
        with patch.object(telos_tools.telos_db, "list_section", return_value=fake) as mock_list:
            out = telos_tools.telos_get_section("goals")
        assert out["status"] == "success"
        # list_section called with status='active' by default.
        _, kwargs = mock_list.call_args
        assert kwargs["status"] == "active"

    def test_unknown_section_returns_error(self):
        from radbot.tools.telos import telos_tools

        out = telos_tools.telos_get_section("not_a_real_section")
        assert out["status"] == "error"

    def test_resolve_prediction_adds_wrong_about_on_miscalibration(self):
        from radbot.tools.telos import telos_tools

        pred = _fake_entry(
            Section.PREDICTIONS, "X will happen", "PRED1",
            metadata={"probability": 0.9},
        )
        resolved = _fake_entry(
            Section.PREDICTIONS, "X will happen", "PRED1",
            metadata={"probability": 0.9, "resolution": "false"},
        )
        wrong = _fake_entry(Section.WRONG_ABOUT, "Miscalibrated on PRED1")

        add_entry_calls = []

        def fake_add_entry(section, content, **kwargs):
            add_entry_calls.append((section, content, kwargs))
            return wrong

        with patch.object(telos_tools.telos_db, "get_entry", return_value=pred), \
             patch.object(telos_tools.telos_db, "update_entry", return_value=resolved), \
             patch.object(telos_tools.telos_db, "add_entry", side_effect=fake_add_entry):
            out = telos_tools.telos_resolve_prediction("PRED1", outcome=False)

        assert out["status"] == "success"
        assert out["miscalibrated"] is True
        # One add_entry call for wrong_about.
        assert any(sec == Section.WRONG_ABOUT for sec, _, _ in add_entry_calls)

    def test_resolve_prediction_no_wrong_about_when_calibrated(self):
        from radbot.tools.telos import telos_tools

        pred = _fake_entry(
            Section.PREDICTIONS, "X will happen", "PRED1",
            metadata={"probability": 0.5},
        )
        resolved = _fake_entry(
            Section.PREDICTIONS, "X will happen", "PRED1",
            metadata={"probability": 0.5, "resolution": "true"},
        )

        add_entry_calls = []

        def fake_add_entry(section, content, **kwargs):
            add_entry_calls.append((section, content, kwargs))
            return _fake_entry(section, content)

        with patch.object(telos_tools.telos_db, "get_entry", return_value=pred), \
             patch.object(telos_tools.telos_db, "update_entry", return_value=resolved), \
             patch.object(telos_tools.telos_db, "add_entry", side_effect=fake_add_entry):
            out = telos_tools.telos_resolve_prediction("PRED1", outcome=True)

        assert out["status"] == "success"
        assert out["miscalibrated"] is False
        assert not any(sec == Section.WRONG_ABOUT for sec, _, _ in add_entry_calls)
