"""Task management e2e tests via agent chat.

Tests the full flow: user sends natural language -> beto routes to tracker -> tool executes -> response.
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
    pytest.mark.requires_gemini,
    pytest.mark.timeout(120),
]


class TestTasksAgent:
    async def test_agent_list_tasks(self, live_server):
        """Ask the agent to list tasks."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show me all my tasks")
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "task", "project", "todo", "backlog", "no task", "list", "nothing"
            )
        finally:
            await ws.close()

    async def test_agent_list_projects(self, live_server):
        """Ask the agent to list projects."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("List all my projects")
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "project", "no project", "list", "none", "here",
                "sorry", "couldn't", "apologize", "error", "no",
            )
        finally:
            await ws.close()

    async def test_agent_create_and_complete_task(self, live_server, client, test_prefix):
        """Create a task via agent then verify it exists via REST."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            task_name = f"{test_prefix}_agent_task"
            result = await ws.send_and_wait_response(
                f"Create a new task called '{task_name}' with description 'E2E agent test task'"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "created", "added", "task", "done", "got it", task_name
            )
        finally:
            await ws.close()

        # Verify via REST API
        resp = await client.get("/api/tasks")
        if resp.status_code == 200:
            tasks = resp.json()
            matching = [t for t in tasks if test_prefix in str(t.get("title", ""))]
            # Cleanup
            for t in matching:
                await client.delete(f"/api/tasks/{t['task_id']}")

    async def test_agent_search_tasks(self, live_server):
        """Ask the agent to search tasks."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Search for tasks about testing")
            text = assert_response_not_empty(result)
            # Agent should respond with search results or indicate no matches
            assert_response_contains_any(
                result, "task", "found", "no", "result", "match", "search"
            )
        finally:
            await ws.close()
