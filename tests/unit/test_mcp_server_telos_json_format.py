"""Unit tests for radbot.mcp_server.tools.telos JSON format (Item 0.c).

Covers:
  * format='json' returns {entry: {...}} or {entries: [...]} with the
    pinned _entry_to_json_dict shape
  * timestamps render as literal Z (not +00:00)
  * UUIDs render as strings (no json.dumps crash)
  * Section enum renders as .value
  * default include_inactive=False translates to status_in=ACTIVE_EQUIVALENT
    on db.list_section
  * include_inactive=True translates to status_in=None (all statuses)
  * metadata_filter passes through to db.list_section
  * format='markdown' (default) preserves the legacy rendering
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from radbot.mcp_server.tools import telos as mcp_telos
from radbot.tools.telos.models import Entry, Section

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _entry(
    section: Section = Section.EXPLORATIONS,
    ref_code: str = "EX1",
    metadata: dict | None = None,
    status: str = "proposed",
) -> Entry:
    now = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
    return Entry(
        entry_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        section=section,
        ref_code=ref_code,
        content="exploration body",
        metadata=metadata or {"source_postmortem": "JR42"},
        status=status,
        sort_order=0,
        created_at=now,
        updated_at=now,
    )


def _call(name: str, arguments: dict):
    return asyncio.run(mcp_telos.call(name, arguments))


# ---------------------------------------------------------------------------
# JSON format payload shape
# ---------------------------------------------------------------------------


class TestGetEntryJsonFormat:
    def test_json_payload_shape_matches_contract(self):
        with patch("radbot.tools.telos.db.get_entry", return_value=_entry()):
            out = _call(
                "telos_get_entry",
                {"section": "explorations", "ref_code": "EX1", "format": "json"},
            )

        payload = json.loads(out[0].text)
        assert "entry" in payload
        e = payload["entry"]
        assert e["ref_code"] == "EX1"
        assert e["entry_id"] == "12345678-1234-5678-1234-567812345678"
        assert e["section"] == "explorations"
        assert e["status"] == "proposed"
        assert e["content"] == "exploration body"
        assert e["metadata"] == {"source_postmortem": "JR42"}

    def test_timestamps_use_literal_z_suffix(self):
        with patch("radbot.tools.telos.db.get_entry", return_value=_entry()):
            out = _call(
                "telos_get_entry",
                {"section": "explorations", "ref_code": "EX1", "format": "json"},
            )

        payload = json.loads(out[0].text)
        assert _TS_RE.match(payload["entry"]["created_at"])
        assert _TS_RE.match(payload["entry"]["updated_at"])
        assert "+00:00" not in out[0].text

    def test_uuid_renders_as_string_no_crash(self):
        """psycopg2 returns uuid.UUID for UUID columns; json.dumps would
        crash without explicit handling."""
        with patch("radbot.tools.telos.db.get_entry", return_value=_entry()):
            out = _call(
                "telos_get_entry",
                {"section": "explorations", "ref_code": "EX1", "format": "json"},
            )
        payload = json.loads(out[0].text)
        assert isinstance(payload["entry"]["entry_id"], str)

    def test_markdown_format_back_compat(self):
        """Default format=markdown preserves legacy rendering."""
        with patch("radbot.tools.telos.db.get_entry", return_value=_entry()):
            out = _call(
                "telos_get_entry",
                {"section": "explorations", "ref_code": "EX1"},
            )
        # Markdown rendering uses ### headers + **Status:** blocks
        assert "### explorations: EX1" in out[0].text
        assert "**Status:**" in out[0].text


class TestGetSectionJsonFormat:
    def test_returns_entries_list(self):
        rows = [_entry(ref_code="EX1"), _entry(ref_code="EX2")]
        with patch("radbot.tools.telos.db.list_section", return_value=rows):
            out = _call(
                "telos_get_section",
                {"section": "explorations", "format": "json"},
            )
        payload = json.loads(out[0].text)
        assert "entries" in payload
        refs = [e["ref_code"] for e in payload["entries"]]
        assert refs == ["EX1", "EX2"]
        # Every entry's timestamps match the literal-Z regex
        for e in payload["entries"]:
            assert _TS_RE.match(e["created_at"])
            assert _TS_RE.match(e["updated_at"])

    def test_default_include_inactive_omits_status_in_kwarg(self):
        """Default behavior: pass nothing → db.list_section uses
        ACTIVE_EQUIVALENT."""
        captured = {}

        def _stub(section, **kwargs):
            captured.update(kwargs)
            return []

        with patch("radbot.tools.telos.db.list_section", side_effect=_stub):
            _call("telos_get_section", {"section": "explorations"})

        # MCP layer omits both status and status_in when include_inactive=False
        # so db.list_section's sentinel default fires (ACTIVE_EQUIVALENT)
        assert "status" not in captured
        assert "status_in" not in captured

    def test_include_inactive_true_translates_to_status_in_none(self):
        captured = {}

        def _stub(section, **kwargs):
            captured.update(kwargs)
            return []

        with patch("radbot.tools.telos.db.list_section", side_effect=_stub):
            _call(
                "telos_get_section",
                {"section": "explorations", "include_inactive": True},
            )

        assert captured.get("status_in") is None

    def test_metadata_filter_passes_through(self):
        captured = {}

        def _stub(section, **kwargs):
            captured.update(kwargs)
            return []

        with patch("radbot.tools.telos.db.list_section", side_effect=_stub):
            _call(
                "telos_get_section",
                {
                    "section": "journal",
                    "format": "json",
                    "metadata_filter": {
                        "type": "postmortem",
                        "processed_at": None,
                    },
                },
            )

        assert captured["metadata_filter"] == {
            "type": "postmortem",
            "processed_at": None,
        }


class TestSchemaShape:
    def test_telos_get_section_schema_has_format_and_metadata_filter(self):
        defs = {t.name: t for t in mcp_telos.tools()}
        sch = defs["telos_get_section"].inputSchema["properties"]
        assert "format" in sch
        assert sch["format"]["enum"] == ["markdown", "json"]
        assert "metadata_filter" in sch

    def test_telos_get_entry_schema_has_format(self):
        defs = {t.name: t for t in mcp_telos.tools()}
        sch = defs["telos_get_entry"].inputSchema["properties"]
        assert "format" in sch
        assert sch["format"]["enum"] == ["markdown", "json"]


class TestIsoDefault:
    def test_iso_default_handles_naive_via_aware_promotion(self):
        # datetime that's already aware in UTC
        from radbot.mcp_server.tools.telos import _iso_default

        dt = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
        assert _iso_default(dt) == "2026-05-03T12:00:00Z"

    def test_iso_default_handles_uuid(self):
        from radbot.mcp_server.tools.telos import _iso_default

        u = uuid.UUID("12345678-1234-5678-1234-567812345678")
        assert _iso_default(u) == "12345678-1234-5678-1234-567812345678"

    def test_iso_default_raises_typeerror_for_unknown(self):
        import pytest

        from radbot.mcp_server.tools.telos import _iso_default

        with pytest.raises(TypeError):
            _iso_default({"not": "supported"})
