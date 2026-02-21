"""Jira integration e2e tests.

Read-only tests via agent chat. Auto-skipped if Jira is unreachable.
"""

import uuid

import pytest

from tests.e2e.helpers.assertions import assert_response_contains_any, assert_response_not_empty
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
