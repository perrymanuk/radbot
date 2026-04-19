"""Jira integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Jira is unreachable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import (
    assert_response_contains_any,
    assert_response_not_empty,
)
from tests.e2e.helpers.ws_client import WSTestClient

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.slow,
    pytest.mark.requires_jira,
    pytest.mark.timeout(120),
]


class TestJiraIntegration:
    async def test_list_jira_issues(self, live_server):
        """Ask about Jira issues."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show my Jira issues")
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "issue", "jira", "ticket", "no issue", "assigned", "task"
            )
        finally:
            await ws.close()

    async def test_search_jira_issues(self, live_server):
        """Search Jira issues."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                "Search Jira for issues about deployment"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "issue",
                "jira",
                "result",
                "found",
                "no issue",
                "deployment",
                "search",
            )
        finally:
            await ws.close()

    @pytest.mark.writes_external
    async def test_add_jira_comment(self, live_server):
        """Add a comment to a Jira issue (requires --run-writes)."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # First list issues to get a real key
            r1 = await ws.send_and_wait_response("Show my Jira issues")
            text1 = assert_response_not_empty(r1)

            # Try to add a comment — may fail if no issues exist
            result = await ws.send_and_wait_response(
                "Add a comment to my most recent Jira issue saying 'E2E test comment - please ignore'"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "comment", "added", "jira", "issue", "no issue", "couldn't"
            )
        finally:
            await ws.close()

    async def test_get_jira_issue_detail(self, live_server):
        """Ask for details on a Jira issue — two-turn drill-down."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            # First list issues
            r1 = await ws.send_and_wait_response("Show my Jira issues")
            assert_response_not_empty(r1)

            # Then ask for details on one
            result = await ws.send_and_wait_response(
                "Show me the full details of the first issue you listed"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "issue",
                "description",
                "status",
                "priority",
                "summary",
                "assignee",
                "type",
                "key",
            )
        finally:
            await ws.close()
