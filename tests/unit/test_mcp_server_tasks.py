"""Unit tests for radbot.mcp_server.tools.tasks.

Covers the EX46 / PT115 read-path bloat reduction:
- `_shorten_project_name` strips URLs from the per-row project label
- `_render_tasks` excludes the `done` bucket by default
- `_render_tasks` includes done when `include_done=True` or `status='done'`
- `list_tasks` tool description advertises the `include_done` knob
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from radbot.mcp_server.tools import tasks as mcp_tasks
from radbot.tools.telos.models import Entry, Section


def _entry(
    section: Section,
    content: str,
    ref_code: str | None = None,
    metadata: dict | None = None,
) -> Entry:
    now = datetime(2026, 4, 18, tzinfo=timezone.utc)
    return Entry(
        entry_id="abcd",
        section=section,
        ref_code=ref_code,
        content=content,
        metadata=metadata or {},
        status="active",
        sort_order=0,
        created_at=now,
        updated_at=now,
    )


class TestShortenProjectName:
    def test_strip_url_from_radbot_project_name(self):
        # PRJ1's content in production is literally this — the URL adds 41 chars
        # of duplication on every per-row label.
        out = mcp_tasks._shorten_project_name(
            "radbot https://github.com/perrymanuk/radbot"
        )
        assert out == "radbot"

    def test_passthrough_when_no_url(self):
        assert (
            mcp_tasks._shorten_project_name("homies automated agentic coding pipeline")
            == "homies automated agentic coding pipeline"
        )

    def test_strip_http_url_too(self):
        assert mcp_tasks._shorten_project_name("foo http://example.com/x") == "foo"

    def test_empty_input_passes_through(self):
        assert mcp_tasks._shorten_project_name("") == ""


class TestRenderTasksIncludeDone:
    def _stub_db(self, projects, tasks):
        def _list_section(section, **kwargs):
            if section == Section.PROJECTS:
                return projects
            if section == Section.PROJECT_TASKS:
                return tasks
            return []

        return _list_section

    def test_default_render_hides_done_bucket(self):
        projects = [
            _entry(
                Section.PROJECTS, "radbot https://github.com/perrymanuk/radbot", "PRJ1"
            )
        ]
        tasks = [
            _entry(
                Section.PROJECT_TASKS,
                "ship feature",
                "PT1",
                metadata={"task_status": "backlog", "parent_project": "PRJ1"},
            ),
            _entry(
                Section.PROJECT_TASKS,
                "old work",
                "PT2",
                metadata={"task_status": "done", "parent_project": "PRJ1"},
            ),
        ]
        with patch(
            "radbot.tools.telos.db.list_section",
            side_effect=self._stub_db(projects, tasks),
        ):
            out = mcp_tasks._render_tasks(status=None, project=None)

        assert "PT1" in out.text
        assert "PT2" not in out.text
        assert "## done" not in out.text
        # URL-stripped project label appears, raw URL does not.
        assert "[radbot]" in out.text
        assert "github.com" not in out.text

    def test_include_done_true_shows_done_bucket(self):
        projects = [_entry(Section.PROJECTS, "radbot", "PRJ1")]
        tasks = [
            _entry(
                Section.PROJECT_TASKS,
                "ship feature",
                "PT1",
                metadata={"task_status": "backlog", "parent_project": "PRJ1"},
            ),
            _entry(
                Section.PROJECT_TASKS,
                "old work",
                "PT2",
                metadata={"task_status": "done", "parent_project": "PRJ1"},
            ),
        ]
        with patch(
            "radbot.tools.telos.db.list_section",
            side_effect=self._stub_db(projects, tasks),
        ):
            out = mcp_tasks._render_tasks(status=None, project=None, include_done=True)

        assert "PT1" in out.text
        assert "PT2" in out.text
        assert "## done" in out.text

    def test_explicit_status_done_shows_only_done(self):
        projects = [_entry(Section.PROJECTS, "radbot", "PRJ1")]
        tasks = [
            _entry(
                Section.PROJECT_TASKS,
                "ship feature",
                "PT1",
                metadata={"task_status": "backlog", "parent_project": "PRJ1"},
            ),
            _entry(
                Section.PROJECT_TASKS,
                "old work",
                "PT2",
                metadata={"task_status": "done", "parent_project": "PRJ1"},
            ),
        ]
        with patch(
            "radbot.tools.telos.db.list_section",
            side_effect=self._stub_db(projects, tasks),
        ):
            out = mcp_tasks._render_tasks(status="done", project=None)

        assert "PT2" in out.text
        assert "PT1" not in out.text

    def test_empty_active_set_returns_no_tasks_message_with_filter_hint(self):
        projects = [_entry(Section.PROJECTS, "radbot", "PRJ1")]
        tasks = [
            _entry(
                Section.PROJECT_TASKS,
                "old work",
                "PT2",
                metadata={"task_status": "done", "parent_project": "PRJ1"},
            ),
        ]
        with patch(
            "radbot.tools.telos.db.list_section",
            side_effect=self._stub_db(projects, tasks),
        ):
            out = mcp_tasks._render_tasks(status=None, project=None)

        assert "_No tasks" in out.text
        assert "include_done=false" in out.text


class TestListTasksToolSchema:
    def test_schema_advertises_include_done_property(self):
        defs = {t.name: t for t in mcp_tasks.tools()}
        schema = defs["list_tasks"].inputSchema

        assert "include_done" in schema["properties"]
        assert schema["properties"]["include_done"]["type"] == "boolean"
        # Default (false) is not silently flipped — agents must opt in.
        assert "include_done" not in schema.get("required", [])
