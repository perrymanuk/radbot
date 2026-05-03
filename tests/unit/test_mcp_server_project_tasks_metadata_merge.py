"""Unit tests for radbot.mcp_server.tools.project_tasks (Item 0.b).

Covers:
  * task_add / exploration_add return the structured-success contract
    envelope (status/ref_code/entry_id/section)
  * task_add / exploration_add accept metadata_merge atomically (no
    chain-race) and whitelist keys silently win on collision
  * task_update / exploration_update accept metadata_merge with same
    precedence rule
  * exploration_update accepts optional `status` (validated against
    extended STATUS_VALUES)
  * exploration_add accepts optional `status` and propagates to add_entry
  * content/description optional + whitespace-rejection trifecta
  * Error paths return JSON `_err` envelope (not plain prose)
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from radbot.mcp_server.tools import project_tasks as mcp_pt
from radbot.tools.telos.models import Entry, Section


def _fake_row(section: Section, ref_code: str) -> Entry:
    return Entry(
        entry_id="abcd-uuid",
        section=section,
        ref_code=ref_code,
        content="x",
        metadata={},
        status="active",
        sort_order=0,
    )


def _call(name: str, arguments: dict):
    return asyncio.run(mcp_pt.call(name, arguments))


def _ok_project():
    return _fake_row(Section.PROJECTS, "PRJ1"), None


# ---------------------------------------------------------------------------
# *_add return contract
# ---------------------------------------------------------------------------


class TestAddReturnContract:
    def test_task_add_returns_json_envelope(self):
        with patch.object(mcp_pt, "_require_project", return_value=_ok_project()):
            with patch(
                "radbot.tools.telos.db.add_entry",
                return_value=_fake_row(Section.PROJECT_TASKS, "PT42"),
            ):
                out = _call(
                    "task_add",
                    {"parent_project": "PRJ1", "description": "do thing"},
                )

        payload = json.loads(out[0].text)
        assert payload == {
            "status": "success",
            "ref_code": "PT42",
            "entry_id": "abcd-uuid",
            "section": "project_tasks",
        }

    def test_exploration_add_returns_json_envelope(self):
        with patch.object(mcp_pt, "_require_project", return_value=_ok_project()):
            with patch(
                "radbot.tools.telos.db.add_entry",
                return_value=_fake_row(Section.EXPLORATIONS, "EX17"),
            ):
                out = _call(
                    "exploration_add",
                    {"parent_project": "PRJ1", "topic": "research"},
                )
        payload = json.loads(out[0].text)
        assert payload["status"] == "success"
        assert payload["ref_code"] == "EX17"
        assert payload["section"] == "explorations"

    def test_milestone_add_returns_json_envelope(self):
        with patch.object(mcp_pt, "_require_project", return_value=_ok_project()):
            with patch(
                "radbot.tools.telos.db.add_entry",
                return_value=_fake_row(Section.MILESTONES, "MS3"),
            ):
                out = _call(
                    "milestone_add",
                    {"parent_project": "PRJ1", "title": "ship v1"},
                )
        payload = json.loads(out[0].text)
        assert payload["status"] == "success"
        assert payload["ref_code"] == "MS3"
        assert payload["section"] == "milestones"

    def test_error_path_returns_json_err_envelope(self):
        # Missing project — _require_project returns the JSON err envelope
        with patch("radbot.tools.telos.db.get_entry", return_value=None):
            out = _call(
                "task_add",
                {"parent_project": "PRJZ", "description": "do thing"},
            )
        payload = json.loads(out[0].text)
        assert payload["status"] == "error"
        assert "PRJZ" in payload["message"]


# ---------------------------------------------------------------------------
# metadata_merge atomic-creation (Item 0.b.ii — closes chain-race blocker)
# ---------------------------------------------------------------------------


class TestMetadataMergeOnAdd:
    def test_task_add_passes_caller_metadata_through(self):
        captured = {}

        def _stub_add(section, content, *, metadata=None, **kw):
            captured["metadata"] = metadata
            return _fake_row(section, "PT1")

        with patch.object(mcp_pt, "_require_project", return_value=_ok_project()):
            with patch("radbot.tools.telos.db.add_entry", side_effect=_stub_add):
                _call(
                    "task_add",
                    {
                        "parent_project": "PRJ1",
                        "description": "x",
                        "metadata_merge": {
                            "source_postmortem": "JR42",
                            "postmortem_followup_role": "task",
                            "postmortem_followup_key": "abc123",
                        },
                    },
                )

        assert captured["metadata"]["source_postmortem"] == "JR42"
        assert captured["metadata"]["postmortem_followup_role"] == "task"
        assert captured["metadata"]["postmortem_followup_key"] == "abc123"
        # Whitelist is also present
        assert captured["metadata"]["parent_project"] == "PRJ1"
        assert captured["metadata"]["task_status"] == "backlog"

    def test_task_add_whitelist_silently_wins_on_collision(self):
        """3-of-3 council consensus: silent override, no error raised."""
        captured = {}

        def _stub_add(section, content, *, metadata=None, **kw):
            captured["metadata"] = metadata
            return _fake_row(section, "PT1")

        with patch.object(mcp_pt, "_require_project", return_value=_ok_project()):
            with patch("radbot.tools.telos.db.add_entry", side_effect=_stub_add):
                _call(
                    "task_add",
                    {
                        "parent_project": "PRJ1",
                        "description": "x",
                        "task_status": "inprogress",
                        "metadata_merge": {"task_status": "done"},
                    },
                )

        # Whitelist (inprogress) wins silently over caller's "done"
        assert captured["metadata"]["task_status"] == "inprogress"

    def test_exploration_add_passes_metadata_merge(self):
        captured = {}

        def _stub_add(section, content, *, metadata=None, **kw):
            captured["metadata"] = metadata
            return _fake_row(section, "EX5")

        with patch.object(mcp_pt, "_require_project", return_value=_ok_project()):
            with patch("radbot.tools.telos.db.add_entry", side_effect=_stub_add):
                _call(
                    "exploration_add",
                    {
                        "parent_project": "PRJ1",
                        "topic": "x",
                        "metadata_merge": {"source_postmortem": "JR42"},
                    },
                )
        assert captured["metadata"]["source_postmortem"] == "JR42"
        assert captured["metadata"]["parent_project"] == "PRJ1"

    def test_milestone_add_passes_metadata_merge(self):
        captured = {}

        def _stub_add(section, content, *, metadata=None, **kw):
            captured["metadata"] = metadata
            return _fake_row(section, "MS1")

        with patch.object(mcp_pt, "_require_project", return_value=_ok_project()):
            with patch("radbot.tools.telos.db.add_entry", side_effect=_stub_add):
                _call(
                    "milestone_add",
                    {
                        "parent_project": "PRJ1",
                        "title": "ship",
                        "metadata_merge": {"foo": "bar"},
                    },
                )
        assert captured["metadata"]["foo"] == "bar"
        assert captured["metadata"]["parent_project"] == "PRJ1"


# ---------------------------------------------------------------------------
# Optional status on exploration_add / exploration_update
# ---------------------------------------------------------------------------


class TestExplorationStatus:
    def test_exploration_add_with_status_proposed(self):
        captured = {}

        def _stub_add(section, content, *, status="active", metadata=None, **kw):
            captured["status"] = status
            return _fake_row(section, "EX99")

        with patch.object(mcp_pt, "_require_project", return_value=_ok_project()):
            with patch("radbot.tools.telos.db.add_entry", side_effect=_stub_add):
                out = _call(
                    "exploration_add",
                    {
                        "parent_project": "PRJ1",
                        "topic": "x",
                        "status": "proposed",
                    },
                )
        assert captured["status"] == "proposed"
        assert json.loads(out[0].text)["status"] == "success"

    def test_exploration_add_default_status_is_active(self):
        captured = {}

        def _stub_add(section, content, *, status="active", metadata=None, **kw):
            captured["status"] = status
            return _fake_row(section, "EX100")

        with patch.object(mcp_pt, "_require_project", return_value=_ok_project()):
            with patch("radbot.tools.telos.db.add_entry", side_effect=_stub_add):
                _call(
                    "exploration_add",
                    {"parent_project": "PRJ1", "topic": "x"},
                )
        assert captured["status"] == "active"

    def test_exploration_update_status_in_review(self):
        captured = {}

        def _stub_update(section, ref_code, **kwargs):
            captured.update(kwargs)
            return _fake_row(section, ref_code)

        with patch("radbot.tools.telos.db.update_entry", side_effect=_stub_update):
            out = _call(
                "exploration_update",
                {"ref_code": "EX1", "status": "in_review"},
            )

        assert captured["status"] == "in_review"
        payload = json.loads(out[0].text)
        assert payload["status"] == "success"
        assert payload["entry_status"] == "in_review"

    def test_exploration_update_invalid_status_returns_json_err(self):
        out = _call("exploration_update", {"ref_code": "EX1", "status": "bogus"})
        payload = json.loads(out[0].text)
        assert payload["status"] == "error"
        assert "bogus" in payload["message"]


# ---------------------------------------------------------------------------
# content/description optional + whitespace-rejection
# ---------------------------------------------------------------------------


class TestUpdateContentOptional:
    def test_exploration_update_absent_content_leaves_body_unchanged(self):
        captured = {}

        def _stub_update(section, ref_code, **kwargs):
            captured.update(kwargs)
            return _fake_row(section, ref_code)

        with patch("radbot.tools.telos.db.update_entry", side_effect=_stub_update):
            _call("exploration_update", {"ref_code": "EX1"})

        # content kwarg is None when absent
        assert captured["content"] is None

    def test_exploration_update_non_empty_content_replaces_body(self):
        captured = {}

        def _stub_update(section, ref_code, **kwargs):
            captured.update(kwargs)
            return _fake_row(section, ref_code)

        with patch("radbot.tools.telos.db.update_entry", side_effect=_stub_update):
            _call("exploration_update", {"ref_code": "EX1", "content": "new body"})

        assert captured["content"] == "new body"

    def test_exploration_update_whitespace_content_rejected(self):
        out = _call("exploration_update", {"ref_code": "EX1", "content": "   "})
        payload = json.loads(out[0].text)
        assert payload["status"] == "error"
        assert "whitespace" in payload["message"]

    def test_task_update_absent_description_leaves_body_unchanged(self):
        captured = {}

        def _stub_update(section, ref_code, **kwargs):
            captured.update(kwargs)
            return _fake_row(section, ref_code)

        with patch("radbot.tools.telos.db.update_entry", side_effect=_stub_update):
            _call("task_update", {"ref_code": "PT1"})
        assert captured["content"] is None

    def test_task_update_whitespace_description_rejected(self):
        out = _call("task_update", {"ref_code": "PT1", "description": "  "})
        payload = json.loads(out[0].text)
        assert payload["status"] == "error"


# ---------------------------------------------------------------------------
# *_update metadata_merge precedence (matches *_add rule)
# ---------------------------------------------------------------------------


class TestUpdateMetadataMerge:
    def test_task_update_metadata_merge_passes_through(self):
        captured = {}

        def _stub_update(section, ref_code, **kwargs):
            captured.update(kwargs)
            return _fake_row(section, ref_code)

        with patch("radbot.tools.telos.db.update_entry", side_effect=_stub_update):
            _call(
                "task_update",
                {
                    "ref_code": "PT1",
                    "metadata_merge": {"source_postmortem": "JR42"},
                },
            )

        assert captured["metadata_merge"]["source_postmortem"] == "JR42"

    def test_task_update_whitelist_silently_wins(self):
        captured = {}

        def _stub_update(section, ref_code, **kwargs):
            captured.update(kwargs)
            return _fake_row(section, ref_code)

        with patch("radbot.tools.telos.db.update_entry", side_effect=_stub_update):
            _call(
                "task_update",
                {
                    "ref_code": "PT1",
                    "title": "real title",
                    "metadata_merge": {"title": "caller title"},
                },
            )

        assert captured["metadata_merge"]["title"] == "real title"


# ---------------------------------------------------------------------------
# Schema shape verification
# ---------------------------------------------------------------------------


class TestSchemaShape:
    def test_task_add_schema_has_metadata_merge(self):
        defs = {t.name: t for t in mcp_pt.tools()}
        assert "metadata_merge" in defs["task_add"].inputSchema["properties"]

    def test_exploration_add_schema_has_status_and_metadata_merge(self):
        defs = {t.name: t for t in mcp_pt.tools()}
        sch = defs["exploration_add"].inputSchema["properties"]
        assert "status" in sch
        assert "metadata_merge" in sch

    def test_exploration_update_content_optional(self):
        defs = {t.name: t for t in mcp_pt.tools()}
        assert "content" not in defs["exploration_update"].inputSchema["required"]

    def test_task_update_description_optional(self):
        defs = {t.name: t for t in mcp_pt.tools()}
        assert "description" not in defs["task_update"].inputSchema["required"]

    def test_exploration_status_enum_includes_lifecycle(self):
        defs = {t.name: t for t in mcp_pt.tools()}
        for tool_name in ("exploration_add", "exploration_update"):
            statuses = defs[tool_name].inputSchema["properties"]["status"]["enum"]
            for lifecycle in (
                "proposed",
                "in_review",
                "approved",
                "executing",
                "active",
                "completed",
                "archived",
                "superseded",
            ):
                assert lifecycle in statuses
