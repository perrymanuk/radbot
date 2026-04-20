"""Scheduler e2e tests via agent chat."""

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


class TestSchedulerAgent:
    async def test_agent_list_scheduled_tasks(self, live_server):
        """Ask the agent to list scheduled tasks."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show my scheduled tasks")
            assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "scheduled",
                "task",
                "cron",
                "no scheduled",
                "none",
                "list",
                "recurring",
                "backlog",
                "schedule",
                "no",
                "here",
                "planner",
                "nada",
                "nothing",
            )
        finally:
            await ws.close()

    async def test_agent_create_scheduled_task(self, live_server, client, test_prefix):
        """Create a scheduled task via agent chat."""
        session_id = str(uuid.uuid4())
        task_name = f"{test_prefix}_e2e_sched"
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                f"Schedule a task called '{task_name}' to run every day at 3am "
                f"(cron: 0 3 * * *) with prompt 'E2E test - do nothing'"
            )
            assert_response_not_empty(result)
            assert_response_contains_any(
                result,
                "scheduled",
                "created",
                "task",
                task_name,
                "success",
                "set up",
                "done",
                "3",
                "daily",
                "every day",
                "cron",
            )
        finally:
            await ws.close()

        # Cleanup via REST
        resp = await client.get("/api/scheduler/tasks")
        if resp.status_code == 200:
            tasks = resp.json()
            for t in tasks:
                if test_prefix in str(t.get("name", "")):
                    await client.delete(f"/api/scheduler/tasks/{t['task_id']}")
