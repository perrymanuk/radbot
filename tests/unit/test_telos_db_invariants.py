"""Unit tests for db.py changes from EX_DRAFT_council_loop_polish (Item 0.c +
Item 1.a + Item 3 invariant).

Covers:
  * STATUS_VALUES extension + ACTIVE_EQUIVALENT contents
  * db.add_entry postmortem invariant (raises ValueError when missing
    `processed_at` on a journal entry flagged as a postmortem)
  * db.add_entry defensive metadata normalization (None → {} before access)
  * db.list_section sentinel pattern (mutual-exclusion + back-compat
    semantics + ACTIVE_EQUIVALENT default)
  * _extract_constraint_status_set parses all three PG normalization shapes
  * _apply_status_check_constraint preflight + add + replace flows

The DB-layer tests mock the psycopg2 connection chain rather than hitting
a real database — matches the pattern used elsewhere in tests/unit.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# STATUS_VALUES + ACTIVE_EQUIVALENT
# ---------------------------------------------------------------------------


class TestStatusValues:
    def test_status_values_contains_legacy_and_lifecycle(self):
        from radbot.tools.telos.models import STATUS_VALUES

        assert STATUS_VALUES == {
            "active",
            "completed",
            "archived",
            "superseded",
            "proposed",
            "in_review",
            "approved",
            "executing",
        }

    def test_active_equivalent_excludes_terminal_states(self):
        from radbot.tools.telos.models import ACTIVE_EQUIVALENT

        assert ACTIVE_EQUIVALENT == frozenset(
            {"active", "proposed", "in_review", "approved", "executing"}
        )
        for terminal in ("completed", "archived", "superseded"):
            assert terminal not in ACTIVE_EQUIVALENT


# ---------------------------------------------------------------------------
# db.add_entry postmortem invariant + defensive normalize
# ---------------------------------------------------------------------------


def _mock_db_chain():
    """Build a (conn_cm, cursor) pair matching `with get_db_connection() ...`
    + `with conn.cursor(cursor_factory=...) ...` shape used by db.add_entry."""
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "entry_id": "fake-uuid",
        "section": "journal",
        "ref_code": "JR1",
        "content": "x",
        "metadata": {"type": "postmortem", "processed_at": None},
        "status": "active",
        "sort_order": 0,
        "created_at": None,
        "updated_at": None,
    }
    cursor_cm = MagicMock()
    cursor_cm.__enter__.return_value = cursor
    cursor_cm.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor_cm
    conn_cm = MagicMock()
    conn_cm.__enter__.return_value = conn
    conn_cm.__exit__.return_value = False
    return conn_cm, cursor


class TestAddEntryPostmortemInvariant:
    def test_postmortem_journal_without_processed_at_raises(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        with pytest.raises(ValueError, match="processed_at"):
            telos_db.add_entry(
                Section.JOURNAL,
                "x",
                metadata={"type": "postmortem"},
            )

    def test_postmortem_via_legacy_event_type_also_raises(self):
        """Closes the agent-side bypass: telos_add_journal historically used
        `event_type` (not `type`) for the postmortem flag."""
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        with pytest.raises(ValueError, match="processed_at"):
            telos_db.add_entry(
                Section.JOURNAL,
                "x",
                metadata={"event_type": "postmortem"},
            )

    def test_postmortem_with_explicit_null_processed_at_succeeds(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        conn_cm, _ = _mock_db_chain()
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            with patch.object(telos_db, "next_ref_code", return_value="JR1"):
                row = telos_db.add_entry(
                    Section.JOURNAL,
                    "x",
                    metadata={"type": "postmortem", "processed_at": None},
                )
        assert row.ref_code == "JR1"

    def test_non_postmortem_journal_with_no_metadata_succeeds(self):
        """Defensive normalize: metadata=None must not crash on .get()."""
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        conn_cm, cursor = _mock_db_chain()
        cursor.fetchone.return_value = {
            "entry_id": "fake-uuid",
            "section": "journal",
            "ref_code": "JR2",
            "content": "x",
            "metadata": {},
            "status": "active",
            "sort_order": 0,
            "created_at": None,
            "updated_at": None,
        }
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            with patch.object(telos_db, "next_ref_code", return_value="JR2"):
                row = telos_db.add_entry(Section.JOURNAL, "x")
        assert row.ref_code == "JR2"

    def test_postmortem_invariant_does_not_apply_to_non_journal_sections(self):
        """Only journal entries get the invariant. A project_tasks row whose
        metadata happens to contain `type=postmortem` (unlikely but legal)
        must not trigger the rejection."""
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        conn_cm, cursor = _mock_db_chain()
        cursor.fetchone.return_value = {
            "entry_id": "fake-uuid",
            "section": "project_tasks",
            "ref_code": "PT1",
            "content": "x",
            "metadata": {"type": "postmortem"},
            "status": "active",
            "sort_order": 0,
            "created_at": None,
            "updated_at": None,
        }
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            with patch.object(telos_db, "next_ref_code", return_value="PT1"):
                row = telos_db.add_entry(
                    Section.PROJECT_TASKS,
                    "x",
                    metadata={"type": "postmortem"},
                )
        assert row.ref_code == "PT1"


# ---------------------------------------------------------------------------
# telos_add_journal event_type=postmortem normalization (defense in depth)
# ---------------------------------------------------------------------------


class TestTelosAddJournalPostmortemNormalization:
    def test_event_type_postmortem_writes_canonical_type_and_processed_at(self):
        from radbot.tools.telos import telos_tools

        captured: dict = {}

        def _stub_add(section, content, *, metadata=None, **kwargs):
            captured["metadata"] = metadata
            from radbot.tools.telos.models import Entry

            return Entry(
                entry_id="x",
                section=section,
                ref_code="JR42",
                content=content,
                metadata=metadata,
                status="active",
            )

        with patch.object(telos_tools.telos_db, "add_entry", side_effect=_stub_add):
            out = telos_tools.telos_add_journal(
                entry="postmortem text",
                event_type="postmortem",
            )

        assert out["status"] == "success"
        assert captured["metadata"]["type"] == "postmortem"
        assert "processed_at" in captured["metadata"]
        assert captured["metadata"]["processed_at"] is None
        assert captured["metadata"]["event_type"] == "postmortem"


# ---------------------------------------------------------------------------
# db.list_section sentinel pattern (Item 0.c blocker fix)
# ---------------------------------------------------------------------------


def _patch_list_section_chain(rows: list[dict]):
    """Return a (conn_cm, cursor, executed) tuple that captures the SQL."""
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    executed: list[tuple] = []
    cursor.execute.side_effect = lambda sql, params=None: executed.append((sql, params))
    cursor_cm = MagicMock()
    cursor_cm.__enter__.return_value = cursor
    cursor_cm.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor_cm
    conn_cm = MagicMock()
    conn_cm.__enter__.return_value = conn
    conn_cm.__exit__.return_value = False
    return conn_cm, cursor, executed


class TestListSectionSentinel:
    def test_omitting_both_status_args_uses_active_equivalent(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import ACTIVE_EQUIVALENT, Section

        conn_cm, _, executed = _patch_list_section_chain([])
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            telos_db.list_section(Section.EXPLORATIONS)

        sql, params = executed[0]
        assert "status = ANY(%s)" in sql
        assert sorted(params[1]) == sorted(ACTIVE_EQUIVALENT)

    def test_explicit_status_active_keeps_legacy_single_filter(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        conn_cm, _, executed = _patch_list_section_chain([])
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            telos_db.list_section(Section.EXPLORATIONS, status="active")

        sql, params = executed[0]
        assert "status = %s" in sql
        assert params[1] == "active"

    def test_explicit_status_none_returns_all_statuses(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        conn_cm, _, executed = _patch_list_section_chain([])
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            telos_db.list_section(Section.EXPLORATIONS, status=None)

        sql, params = executed[0]
        assert "status" not in sql
        assert tuple(params) == ("explorations",)

    def test_explicit_status_in_none_returns_all_statuses(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        conn_cm, _, executed = _patch_list_section_chain([])
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            telos_db.list_section(Section.EXPLORATIONS, status_in=None)

        sql, params = executed[0]
        assert "status" not in sql

    def test_explicit_status_in_set_uses_any(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        conn_cm, _, executed = _patch_list_section_chain([])
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            telos_db.list_section(
                Section.EXPLORATIONS, status_in={"proposed", "approved"}
            )

        sql, params = executed[0]
        assert "status = ANY(%s)" in sql
        assert sorted(params[1]) == ["approved", "proposed"]

    def test_status_and_status_in_mutually_exclusive(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import ACTIVE_EQUIVALENT, Section

        with pytest.raises(ValueError, match="mutually exclusive"):
            telos_db.list_section(
                Section.EXPLORATIONS, status="active", status_in=ACTIVE_EQUIVALENT
            )

    def test_metadata_filter_adds_jsonb_containment(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import Section

        conn_cm, _, executed = _patch_list_section_chain([])
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            telos_db.list_section(
                Section.JOURNAL,
                metadata_filter={"type": "postmortem", "processed_at": None},
            )

        sql, params = executed[0]
        assert "metadata @> %s::jsonb" in sql
        assert '"type": "postmortem"' in params[-1]


# ---------------------------------------------------------------------------
# _extract_constraint_status_set + _apply_status_check_constraint
# ---------------------------------------------------------------------------


class TestExtractConstraintStatusSet:
    def test_parses_array_text_form(self):
        from radbot.tools.telos.db import _extract_constraint_status_set

        result = _extract_constraint_status_set(
            "CHECK ((status = ANY (ARRAY['active'::text, 'completed'::text])))"
        )
        assert result == {"active", "completed"}

    def test_parses_in_clause_form(self):
        from radbot.tools.telos.db import _extract_constraint_status_set

        result = _extract_constraint_status_set(
            "CHECK (status IN ('active', 'completed', 'archived'))"
        )
        assert result == {"active", "completed", "archived"}

    def test_parses_double_cast_form(self):
        from radbot.tools.telos.db import _extract_constraint_status_set

        result = _extract_constraint_status_set(
            "CHECK ((status)::text = ANY ((ARRAY['active'::text, 'archived'::text])::text[]))"
        )
        assert result == {"active", "archived"}


class TestApplyStatusCheckConstraint:
    def _patched_chain(self, sequence: list):
        """Build a cursor whose `fetchone` returns each item in order."""
        cursor = MagicMock()
        cursor.fetchone.side_effect = sequence
        cursor.execute = MagicMock()
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = cursor
        cursor_cm.__exit__.return_value = False
        conn = MagicMock()
        conn_cm = MagicMock()
        conn_cm.__enter__.return_value = conn
        conn_cm.__exit__.return_value = False
        return conn_cm, conn, cursor, cursor_cm

    def test_preflight_aborts_when_bad_rows_exist(self):
        from radbot.tools.telos import db as telos_db

        conn_cm, conn, cursor, cursor_cm = self._patched_chain([(2, "weird, bogus")])
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            with patch.object(telos_db, "get_db_cursor", return_value=cursor_cm):
                with pytest.raises(RuntimeError, match="Fix data before applying"):
                    telos_db._apply_status_check_constraint()

    def test_no_existing_constraint_then_add(self):
        from radbot.tools.telos import db as telos_db

        # preflight: 0 bad rows; then None for existing constraint def
        conn_cm, conn, cursor, cursor_cm = self._patched_chain([(0, ""), None])
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            with patch.object(telos_db, "get_db_cursor", return_value=cursor_cm):
                telos_db._apply_status_check_constraint()

        # Last execute is the ADD CONSTRAINT
        last_sql = cursor.execute.call_args_list[-1][0][0]
        assert "ADD CONSTRAINT" in last_sql
        assert telos_db._STATUS_CHECK_NAME in last_sql

    def test_existing_constraint_with_matching_set_is_noop(self):
        from radbot.tools.telos import db as telos_db
        from radbot.tools.telos.models import STATUS_VALUES

        existing_def = (
            "CHECK (status IN ("
            + ", ".join(f"'{s}'" for s in sorted(STATUS_VALUES))
            + "))"
        )
        conn_cm, conn, cursor, cursor_cm = self._patched_chain(
            [(0, ""), (existing_def,)]
        )
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            with patch.object(telos_db, "get_db_cursor", return_value=cursor_cm):
                telos_db._apply_status_check_constraint()

        # No DROP/ADD beyond the two SELECTs (preflight + lookup)
        executed_sql = [c[0][0] for c in cursor.execute.call_args_list]
        assert not any("DROP CONSTRAINT" in s for s in executed_sql)
        assert not any("ADD CONSTRAINT" in s for s in executed_sql)

    def test_existing_constraint_with_legacy_set_triggers_replace(self):
        from radbot.tools.telos import db as telos_db

        legacy_def = (
            "CHECK (status IN ('active', 'completed', 'archived', 'superseded'))"
        )
        conn_cm, conn, cursor, cursor_cm = self._patched_chain([(0, ""), (legacy_def,)])
        with patch.object(telos_db, "get_db_connection", return_value=conn_cm):
            with patch.object(telos_db, "get_db_cursor", return_value=cursor_cm):
                telos_db._apply_status_check_constraint()

        executed_sql = [c[0][0] for c in cursor.execute.call_args_list]
        assert any("DROP CONSTRAINT" in s for s in executed_sql)
        assert any("ADD CONSTRAINT" in s for s in executed_sql)
        # The new ADD should contain all 8 statuses
        add_sql = next(s for s in executed_sql if "ADD CONSTRAINT" in s)
        for status in ("proposed", "in_review", "approved", "executing"):
            assert f"'{status}'" in add_sql
