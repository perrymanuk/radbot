"""Unit tests for radbot.mcp_server.tools.journal (Item 0.a).

Covers:
  * journal_add returns the structured-success contract envelope
  * journal_add propagates the postmortem invariant ValueError as a JSON
    error envelope (not a Python crash)
  * journal_update accepts metadata_merge + status, validates status enum
  * journal_update returns the JSON _err envelope on missing ref_code
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from radbot.mcp_server.tools import journal as mcp_journal
from radbot.tools.telos.models import Entry, Section


def _fake_journal_entry(ref_code: str = "JR1") -> Entry:
    return Entry(
        entry_id="abcd-uuid",
        section=Section.JOURNAL,
        ref_code=ref_code,
        content="postmortem text",
        metadata={"type": "postmortem", "processed_at": None},
        status="active",
        sort_order=0,
    )


def _call(name: str, arguments: dict):
    return asyncio.run(mcp_journal.call(name, arguments))


class TestJournalAdd:
    def test_returns_structured_success_envelope(self):
        with patch.object(
            mcp_journal,
            "_do_journal_add",
            wraps=mcp_journal._do_journal_add,
        ):
            with patch(
                "radbot.tools.telos.db.add_entry",
                return_value=_fake_journal_entry("JR42"),
            ):
                out = _call(
                    "journal_add",
                    {
                        "entry": "postmortem text",
                        "metadata": {"type": "postmortem", "processed_at": None},
                    },
                )

        assert len(out) == 1
        payload = json.loads(out[0].text)
        assert payload == {
            "status": "success",
            "ref_code": "JR42",
            "entry_id": "abcd-uuid",
            "section": "journal",
        }

    def test_propagates_invariant_violation_as_json_error(self):
        """db.add_entry's postmortem invariant raises ValueError; the MCP
        wrapper must convert that to the JSON `_err` envelope, not crash."""

        def _raise(*a, **kw):
            raise ValueError(
                "postmortem journal entries must include metadata.processed_at"
            )

        with patch("radbot.tools.telos.db.add_entry", side_effect=_raise):
            out = _call(
                "journal_add",
                {"entry": "x", "metadata": {"type": "postmortem"}},
            )

        payload = json.loads(out[0].text)
        assert payload["status"] == "error"
        assert "processed_at" in payload["message"]

    def test_empty_entry_rejected(self):
        out = _call("journal_add", {"entry": "   "})
        payload = json.loads(out[0].text)
        assert payload["status"] == "error"
        assert "entry" in payload["message"]


class TestJournalUpdate:
    def test_metadata_merge_and_status_passes_through(self):
        captured: dict = {}

        def _stub_update(section, ref_code, **kwargs):
            captured.update(kwargs)
            captured["ref_code"] = ref_code
            return _fake_journal_entry(ref_code)

        with patch("radbot.tools.telos.db.update_entry", side_effect=_stub_update):
            out = _call(
                "journal_update",
                {
                    "ref_code": "JR1",
                    "metadata_merge": {
                        "processed_at": "2026-05-03T12:00:00Z",
                        "processed_by": "scout",
                    },
                    "status": "completed",
                },
            )

        payload = json.loads(out[0].text)
        assert payload["status"] == "success"
        assert captured["ref_code"] == "JR1"
        assert captured["status"] == "completed"
        assert captured["metadata_merge"]["processed_by"] == "scout"

    def test_invalid_status_rejected_against_journal_enum(self):
        # Lifecycle states are not valid for journal rows
        out = _call(
            "journal_update",
            {"ref_code": "JR1", "status": "in_review"},
        )
        payload = json.loads(out[0].text)
        assert payload["status"] == "error"
        assert "in_review" in payload["message"]

    def test_missing_ref_code_returns_json_err(self):
        with patch("radbot.tools.telos.db.update_entry", return_value=None):
            out = _call("journal_update", {"ref_code": "JRZ"})
        payload = json.loads(out[0].text)
        assert payload["status"] == "error"
        assert "JRZ" in payload["message"]


class TestSchemaShape:
    def test_journal_add_schema_requires_entry_only(self):
        defs = {t.name: t for t in mcp_journal.tools()}
        schema = defs["journal_add"].inputSchema
        assert schema["required"] == ["entry"]
        assert "metadata" in schema["properties"]
        assert schema["properties"]["metadata"]["type"] == "object"

    def test_journal_update_status_enum_excludes_lifecycle_states(self):
        defs = {t.name: t for t in mcp_journal.tools()}
        schema = defs["journal_update"].inputSchema
        statuses = schema["properties"]["status"]["enum"]
        assert "active" in statuses
        for lifecycle in ("proposed", "in_review", "approved", "executing"):
            assert lifecycle not in statuses
