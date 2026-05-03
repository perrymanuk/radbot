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
        entries = parse_telos_markdown("## IDENTITY\n\nLine one.\nLine two.\n")
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
        with (
            patch.object(
                telos_loader.telos_db, "list_all_active", return_value=grouped
            ),
            patch.object(telos_loader.telos_db, "recent_journal", return_value=[]),
        ):
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
        with (
            patch.object(
                telos_loader.telos_db, "list_all_active", return_value=grouped
            ),
            patch.object(telos_loader.telos_db, "recent_journal", return_value=journal),
        ):
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
        grouped[Section.IDENTITY] = [_fake_entry(Section.IDENTITY, "x" * 2000, "ME")]
        grouped[Section.MISSION] = [_fake_entry(Section.MISSION, "y" * 2000, "M1")]
        grouped[Section.GOALS] = [
            _fake_entry(Section.GOALS, f"goal {i}", f"G{i}") for i in range(20)
        ]
        with (
            patch.object(
                telos_loader.telos_db, "list_all_active", return_value=grouped
            ),
            patch.object(telos_loader.telos_db, "recent_journal", return_value=[]),
        ):
            anchor, _ = telos_loader.build_telos_tiers()
        assert len(anchor.encode("utf-8")) <= telos_loader.ANCHOR_CAP_BYTES

    def test_full_block_size_cap(self):
        grouped = {s: [] for s in Section}
        grouped[Section.IDENTITY] = [_fake_entry(Section.IDENTITY, "Perry", "ME")]
        grouped[Section.MISSION] = [_fake_entry(Section.MISSION, "Mission text", "M1")]
        grouped[Section.GOALS] = [
            _fake_entry(Section.GOALS, "A" * 200, f"G{i}") for i in range(30)
        ]
        journal = [_fake_entry(Section.JOURNAL, "J" * 150) for _ in range(30)]
        with (
            patch.object(
                telos_loader.telos_db, "list_all_active", return_value=grouped
            ),
            patch.object(telos_loader.telos_db, "recent_journal", return_value=journal),
        ):
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
            "radbot.tools.telos.loader.build_telos_tiers",
            return_value=("", ""),
        ):
            ctx = _make_ctx()
            req = _make_req("original")
            result = inject_telos_context(ctx, req)
        assert result is None
        assert req.config.system_instruction == "original"

    def test_first_turn_injects_anchor_plus_full_block(self):
        with patch(
            "radbot.tools.telos.loader.build_telos_tiers",
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
            "radbot.tools.telos.loader.build_telos_tiers",
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
            "radbot.tools.telos.loader.build_telos_tiers",
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
            "radbot.tools.telos.loader.build_telos_tiers",
            return_value=("ANCHOR_TEXT", ""),
        ):
            ctx = _make_ctx()
            req = _make_req(None)
            inject_telos_context(ctx, req)
        assert req.config.system_instruction == "ANCHOR_TEXT"

    def test_handles_db_failure_gracefully(self):
        with patch(
            "radbot.tools.telos.loader.build_telos_tiers",
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
    """Item 6 (2026-05-03) — `inject_telos_context` is retired from beto's
    callback chain. Only scout-as-root receives it. No sub-agent receives it.

    Producer-side marker pinning anchored to the ACTUAL markers emitted by
    `build_telos_tiers()` (`"TELOS ANCHOR"` for the anchor, `"USER CONTEXT
    (Telos)"` for the full block) — the spec's hypothetical `"## Mission"` /
    `"## Identity"` / `"ME:"` literals never existed in `loader.py`.
    Anchoring to real markers means a future rename of either the producer
    headers OR the consumer absence checks fails the same test, alerting
    the implementer that the two sides drifted.
    """

    def test_inject_telos_context_NOT_on_beto(self):
        """beto.before_model_callback must not contain inject_telos_context."""
        from radbot.agent.assembly import build_default_assembly

        core_root = build_default_assembly().root_agent
        before = core_root.before_model_callback or []
        assert (
            inject_telos_context not in before
        ), "inject_telos_context regressed back onto beto — Item 6 retirement"

    def test_inject_telos_context_on_scout_as_root(self):
        """scout-as-root is the SOLE consumer of inject_telos_context."""
        from radbot.agent.assembly import build_default_assembly

        assembly = build_default_assembly()
        scout_root = assembly.root_agents.get("scout")
        assert (
            scout_root is not None
        ), "scout-as-root not registered in assembly.root_agents"
        before = scout_root.before_model_callback or []
        assert inject_telos_context in before, (
            "inject_telos_context missing from scout-as-root's callback chain — "
            "see radbot/agent/research_agent/factory.py:217-242"
        )

    def test_no_subagent_receives_inject_telos_context(self):
        """Sub-agents are tool executors — they should never receive Telos context."""
        from radbot.agent.assembly import build_default_assembly

        core_root = build_default_assembly().root_agent
        for sa in core_root.sub_agents:
            before = sa.before_model_callback or []
            assert (
                inject_telos_context not in before
            ), f"inject_telos_context leaked into sub-agent {sa.name}"

    def test_producer_emits_consumer_check_markers(self):
        """build_telos_tiers() must emit literal markers the consumer absence
        tests rely on. If a future rename moves these in `loader.py`, this
        test fails first — alerting the implementer that the consumer-side
        AC checks must be updated in the same PR.
        """
        grouped = {s: [] for s in Section}
        grouped[Section.IDENTITY] = [
            _fake_entry(Section.IDENTITY, "Perry, Austin, builds agents", "ME")
        ]
        grouped[Section.MISSION] = [
            _fake_entry(Section.MISSION, "Make radbot self-aware", "M1")
        ]
        grouped[Section.GOALS] = [_fake_entry(Section.GOALS, "Ship telos", "G1")]
        with (
            patch.object(
                telos_loader.telos_db, "list_all_active", return_value=grouped
            ),
            patch.object(telos_loader.telos_db, "recent_journal", return_value=[]),
        ):
            anchor, full_block = telos_loader.build_telos_tiers()

        # Anchor markers
        assert "TELOS ANCHOR" in anchor, "anchor lost the 'TELOS ANCHOR' header literal"
        # Full-block markers
        assert (
            "USER CONTEXT (Telos)" in full_block
        ), "full block lost the 'USER CONTEXT (Telos)' header literal"
        assert "IDENTITY:" in full_block, "full block lost 'IDENTITY:' section header"
        assert "MISSION:" in full_block, "full block lost 'MISSION:' section header"

    def test_telos_tools_on_beto(self):
        """Telos tools should be registered on beto's tool list."""
        from radbot.agent.assembly import build_default_assembly

        core_assembly = build_default_assembly()
        core_root = core_assembly.root_agent
        from radbot.tools.telos import TELOS_TOOLS

        beto_tool_fns = set()
        for t in core_root.tools:
            fn = getattr(t, "func", None)
            if fn:
                beto_tool_fns.add(fn.__name__)

        for tool in TELOS_TOOLS:
            fn = getattr(tool, "func", None)
            if fn:
                assert (
                    fn.__name__ in beto_tool_fns
                ), f"Telos tool {fn.__name__} missing from beto"


# ---------------------------------------------------------------------------
# Tool layer (with DB mocked)
# ---------------------------------------------------------------------------


class TestToolsLayer:
    def test_silent_add_journal(self):
        from radbot.tools.telos import telos_tools

        fake_row = _fake_entry(Section.JOURNAL, "Did a thing")
        with patch.object(
            telos_tools.telos_db, "add_entry", return_value=fake_row
        ) as mock_add:
            out = telos_tools.telos_add_journal("Did a thing", event_type="decision")
        assert out["status"] == "success"
        assert out["entry"]["content"] == "Did a thing"
        _, kwargs = mock_add.call_args
        assert kwargs["metadata"]["event_type"] == "decision"

    def test_confirm_required_add_goal(self):
        from radbot.tools.telos import telos_tools

        fake_row = _fake_entry(
            Section.GOALS,
            "Ship telos",
            "G1",
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
        with patch.object(
            telos_tools.telos_db, "list_section", return_value=fake
        ) as mock_list:
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
            Section.PREDICTIONS,
            "X will happen",
            "PRED1",
            metadata={"probability": 0.9},
        )
        resolved = _fake_entry(
            Section.PREDICTIONS,
            "X will happen",
            "PRED1",
            metadata={"probability": 0.9, "resolution": "false"},
        )
        wrong = _fake_entry(Section.WRONG_ABOUT, "Miscalibrated on PRED1")

        add_entry_calls = []

        def fake_add_entry(section, content, **kwargs):
            add_entry_calls.append((section, content, kwargs))
            return wrong

        with (
            patch.object(telos_tools.telos_db, "get_entry", return_value=pred),
            patch.object(telos_tools.telos_db, "update_entry", return_value=resolved),
            patch.object(telos_tools.telos_db, "add_entry", side_effect=fake_add_entry),
        ):
            out = telos_tools.telos_resolve_prediction("PRED1", outcome=False)

        assert out["status"] == "success"
        assert out["miscalibrated"] is True
        # One add_entry call for wrong_about.
        assert any(sec == Section.WRONG_ABOUT for sec, _, _ in add_entry_calls)

    def test_resolve_prediction_no_wrong_about_when_calibrated(self):
        from radbot.tools.telos import telos_tools

        pred = _fake_entry(
            Section.PREDICTIONS,
            "X will happen",
            "PRED1",
            metadata={"probability": 0.5},
        )
        resolved = _fake_entry(
            Section.PREDICTIONS,
            "X will happen",
            "PRED1",
            metadata={"probability": 0.5, "resolution": "true"},
        )

        add_entry_calls = []

        def fake_add_entry(section, content, **kwargs):
            add_entry_calls.append((section, content, kwargs))
            return _fake_entry(section, content)

        with (
            patch.object(telos_tools.telos_db, "get_entry", return_value=pred),
            patch.object(telos_tools.telos_db, "update_entry", return_value=resolved),
            patch.object(telos_tools.telos_db, "add_entry", side_effect=fake_add_entry),
        ):
            out = telos_tools.telos_resolve_prediction("PRED1", outcome=True)

        assert out["status"] == "success"
        assert out["miscalibrated"] is False
        assert not any(sec == Section.WRONG_ABOUT for sec, _, _ in add_entry_calls)

    # --- telos_update_entry ---

    def test_update_entry_success(self):
        from radbot.tools.telos import telos_tools

        updated = _fake_entry(Section.EXPLORATIONS, "Updated topic", "EX1")
        with patch.object(
            telos_tools.telos_db, "update_entry", return_value=updated
        ) as mock_update:
            out = telos_tools.telos_update_entry(
                "explorations", "EX1", content="Updated topic"
            )
        assert out["status"] == "success"
        assert out["entry"]["content"] == "Updated topic"
        mock_update.assert_called_once()

    def test_update_entry_not_found(self):
        from radbot.tools.telos import telos_tools

        with patch.object(telos_tools.telos_db, "update_entry", return_value=None):
            out = telos_tools.telos_update_entry("explorations", "EX999")
        assert out["status"] == "error"
        assert "EX999" in out["message"]

    def test_update_entry_invalid_status(self):
        from radbot.tools.telos import telos_tools

        out = telos_tools.telos_update_entry("explorations", "EX1", status="flying")
        assert out["status"] == "error"
        assert "flying" in out["message"]

    def test_update_entry_invalid_section(self):
        from radbot.tools.telos import telos_tools

        out = telos_tools.telos_update_entry("not_real", "X1")
        assert out["status"] == "error"

    # --- telos_delete_entry ---

    def test_delete_entry_success_exploration(self):
        from radbot.tools.telos import telos_tools

        with patch.object(
            telos_tools.telos_db, "archive_entry", return_value=True
        ) as mock_arch:
            out = telos_tools.telos_delete_entry("explorations", "EX3", reason="stale")
        assert out["status"] == "success"
        assert out["deleted"] == "explorations:EX3"
        mock_arch.assert_called_once_with(
            telos_tools.Section.EXPLORATIONS, "EX3", reason="stale"
        )

    def test_delete_entry_success_project_task(self):
        from radbot.tools.telos import telos_tools

        with patch.object(telos_tools.telos_db, "archive_entry", return_value=True):
            out = telos_tools.telos_delete_entry("project_tasks", "PT7")
        assert out["status"] == "success"
        assert "project_tasks:PT7" in out["deleted"]

    def test_delete_entry_not_found(self):
        from radbot.tools.telos import telos_tools

        with patch.object(telos_tools.telos_db, "archive_entry", return_value=False):
            out = telos_tools.telos_delete_entry("explorations", "EX99")
        assert out["status"] == "error"
        assert "EX99" in out["message"]

    def test_delete_entry_blocked_for_restricted_section(self):
        from radbot.tools.telos import telos_tools

        # Goals are beto-only; Scout must not be able to delete them.
        out = telos_tools.telos_delete_entry("goals", "G1")
        assert out["status"] == "error"
        assert "Scout" in out["message"]

    def test_delete_entry_blocked_for_identity(self):
        from radbot.tools.telos import telos_tools

        out = telos_tools.telos_delete_entry("identity", "ME")
        assert out["status"] == "error"
        assert "Scout" in out["message"]

    def test_delete_entry_invalid_section(self):
        from radbot.tools.telos import telos_tools

        out = telos_tools.telos_delete_entry("not_real", "X1")
        assert out["status"] == "error"


# ---------------------------------------------------------------------------
# SCOUT_TELOS_TOOLS list completeness
# ---------------------------------------------------------------------------


class TestScoutTelosTools:
    def test_scout_tools_include_update_and_delete(self):
        from radbot.tools.telos.telos_tools import (
            SCOUT_TELOS_TOOLS,
            telos_delete_entry_tool,
            telos_update_entry_tool,
        )

        tool_fns = {
            getattr(t, "func", None).__name__
            for t in SCOUT_TELOS_TOOLS
            if getattr(t, "func", None)
        }
        assert (
            "telos_update_entry" in tool_fns
        ), "telos_update_entry missing from SCOUT_TELOS_TOOLS"
        assert (
            "telos_delete_entry" in tool_fns
        ), "telos_delete_entry missing from SCOUT_TELOS_TOOLS"

        # FunctionTool objects are present by identity.
        assert telos_update_entry_tool in SCOUT_TELOS_TOOLS
        assert telos_delete_entry_tool in SCOUT_TELOS_TOOLS

    def test_scout_tools_count(self):
        from radbot.tools.telos.telos_tools import SCOUT_TELOS_TOOLS

        # 13 → 14 after adding telos_list_archived_tasks (EX46 / PT115).
        assert len(SCOUT_TELOS_TOOLS) == 14

    def test_scout_delete_not_in_telos_tools(self):
        """telos_delete_entry is scout-scoped; it should NOT appear in the full beto list."""
        from radbot.tools.telos.telos_tools import TELOS_TOOLS, telos_delete_entry_tool

        assert telos_delete_entry_tool not in TELOS_TOOLS


# ---------------------------------------------------------------------------
# EX46 / PT115 — list_tasks read-path bloat reduction
# ---------------------------------------------------------------------------


class TestListTasksBloatReduction:
    def test_serialize_entry_slim_drops_timestamps_and_full_metadata(self):
        from radbot.tools.telos import telos_tools

        entry = _fake_entry(
            Section.PROJECT_TASKS,
            "Build the thing",
            "PT99",
            metadata={
                "task_status": "backlog",
                "parent_project": "PRJ1",
                "title": "Build",
                "internal_debug_blob": "x" * 200,  # noisy, not in slim allow-list
            },
        )

        slim = telos_tools._serialize_entry(entry)

        assert "entry_id" not in slim
        assert "created_at" not in slim
        assert "updated_at" not in slim
        assert "sort_order" not in slim
        # Curated metadata subset is preserved; noise is dropped.
        assert slim["metadata"]["task_status"] == "backlog"
        assert slim["metadata"]["parent_project"] == "PRJ1"
        assert slim["metadata"]["title"] == "Build"
        assert "internal_debug_blob" not in slim["metadata"]
        # Core identifiers stay.
        assert slim["ref_code"] == "PT99"
        assert slim["content"] == "Build the thing"
        assert slim["status"] == "active"

    def test_serialize_entry_full_preserves_all_fields(self):
        from radbot.tools.telos import telos_tools

        entry = _fake_entry(
            Section.GOALS, "x", "G1", metadata={"deadline": "2026-12-31"}
        )

        full = telos_tools._serialize_entry(entry, full=True)

        assert "entry_id" in full
        assert "created_at" in full
        assert "updated_at" in full
        assert full["metadata"] == {"deadline": "2026-12-31"}

    def test_list_tasks_excludes_done_by_default(self):
        from radbot.tools.telos import telos_tools

        rows = [
            _fake_entry(
                Section.PROJECT_TASKS,
                "ship feature",
                "PT1",
                metadata={"task_status": "backlog", "parent_project": "PRJ1"},
            ),
            _fake_entry(
                Section.PROJECT_TASKS,
                "old work",
                "PT2",
                metadata={"task_status": "done", "parent_project": "PRJ1"},
            ),
        ]
        with patch.object(telos_tools.telos_db, "list_section", return_value=rows):
            out = telos_tools.telos_list_tasks()

        refs = [e["ref_code"] for e in out["entries"]]
        assert "PT1" in refs
        assert "PT2" not in refs

    def test_list_tasks_include_done_returns_completed(self):
        from radbot.tools.telos import telos_tools

        rows = [
            _fake_entry(
                Section.PROJECT_TASKS,
                "ship feature",
                "PT1",
                metadata={"task_status": "backlog", "parent_project": "PRJ1"},
            ),
            _fake_entry(
                Section.PROJECT_TASKS,
                "old work",
                "PT2",
                metadata={"task_status": "done", "parent_project": "PRJ1"},
            ),
        ]
        with patch.object(telos_tools.telos_db, "list_section", return_value=rows):
            out = telos_tools.telos_list_tasks(include_done=True)

        refs = [e["ref_code"] for e in out["entries"]]
        assert refs == ["PT1", "PT2"]

    def test_list_tasks_explicit_done_filter_returns_only_done(self):
        from radbot.tools.telos import telos_tools

        rows = [
            _fake_entry(
                Section.PROJECT_TASKS,
                "ship feature",
                "PT1",
                metadata={"task_status": "backlog", "parent_project": "PRJ1"},
            ),
            _fake_entry(
                Section.PROJECT_TASKS,
                "old work",
                "PT2",
                metadata={"task_status": "done", "parent_project": "PRJ1"},
            ),
        ]
        with patch.object(telos_tools.telos_db, "list_section", return_value=rows):
            out = telos_tools.telos_list_tasks(task_status="done")

        refs = [e["ref_code"] for e in out["entries"]]
        assert refs == ["PT2"]

    def test_list_archived_tasks_queries_archived_status(self):
        from radbot.tools.telos import telos_tools

        archived = _fake_entry(
            Section.PROJECT_TASKS,
            "old shipped work",
            "PT9",
            metadata={"task_status": "done", "parent_project": "PRJ1"},
        )
        with patch.object(
            telos_tools.telos_db, "list_section", return_value=[archived]
        ) as mock_list:
            out = telos_tools.telos_list_archived_tasks(parent_project="PRJ1")

        _, kwargs = mock_list.call_args
        assert kwargs["status"] == "archived"
        assert kwargs["order_by"] == "created_at_desc"
        assert out["status"] == "success"
        assert out["entries"][0]["ref_code"] == "PT9"

    def test_archive_stale_done_tasks_executes_sql_and_returns_rowcount(self):
        from radbot.tools.telos import db as telos_db

        # Mock the connection-context-manager chain. archive_stale_done_tasks
        # uses `with get_db_connection() as conn: with conn.cursor() as cursor`.
        cursor = MagicMock()
        cursor.rowcount = 7
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = cursor
        cursor_cm.__exit__.return_value = False
        conn = MagicMock()
        conn.cursor.return_value = cursor_cm
        conn_cm = MagicMock()
        conn_cm.__enter__.return_value = conn
        conn_cm.__exit__.return_value = False

        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            count = telos_db.archive_stale_done_tasks(since_days=30)

        assert count == 7
        executed_sql = cursor.execute.call_args[0][0]
        assert "section = 'project_tasks'" in executed_sql
        assert "metadata->>'task_status' = 'done'" in executed_sql
        assert "INTERVAL '30 days'" in executed_sql
        assert "auto_stale_done" in executed_sql
        conn.commit.assert_called_once()

    def test_archive_stale_done_tasks_rejects_negative_days(self):
        import pytest

        from radbot.tools.telos import db as telos_db

        with pytest.raises(ValueError):
            telos_db.archive_stale_done_tasks(since_days=-1)
