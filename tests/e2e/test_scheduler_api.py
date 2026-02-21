"""Scheduler API e2e tests."""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestSchedulerAPI:
    async def test_create_scheduled_task(self, client, cleanup, test_prefix):
        """POST /api/scheduler/tasks should create a scheduled task."""
        resp = await client.post(
            "/api/scheduler/tasks",
            json={
                "name": f"{test_prefix}_sched",
                "cron_expression": "0 0 31 2 *",  # Feb 31 = never fires
                "prompt": "E2E test scheduled task - do nothing",
                "description": "E2E test task",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "task_id" in data
        cleanup.track("scheduled_task", data["task_id"])

    async def test_list_scheduled_tasks(self, client, cleanup, test_prefix):
        """GET /api/scheduler/tasks should include the created task."""
        # Create
        create_resp = await client.post(
            "/api/scheduler/tasks",
            json={
                "name": f"{test_prefix}_sched_list",
                "cron_expression": "0 0 31 2 *",
                "prompt": "E2E test",
            },
        )
        task_id = create_resp.json()["task_id"]
        cleanup.track("scheduled_task", task_id)

        # List
        resp = await client.get("/api/scheduler/tasks")
        assert resp.status_code == 200
        tasks = resp.json()
        assert isinstance(tasks, list)
        ids = [str(t.get("task_id")) for t in tasks]
        assert task_id in ids

    async def test_delete_scheduled_task(self, client, test_prefix):
        """DELETE /api/scheduler/tasks/{id} should remove the task."""
        # Create
        create_resp = await client.post(
            "/api/scheduler/tasks",
            json={
                "name": f"{test_prefix}_sched_del",
                "cron_expression": "0 0 31 2 *",
                "prompt": "E2E test delete",
            },
        )
        task_id = create_resp.json()["task_id"]

        # Delete
        resp = await client.delete(f"/api/scheduler/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    @pytest.mark.slow
    async def test_manual_trigger(self, client, cleanup, test_prefix):
        """POST /api/scheduler/tasks/{id}/trigger should accept."""
        # Create
        create_resp = await client.post(
            "/api/scheduler/tasks",
            json={
                "name": f"{test_prefix}_sched_trigger",
                "cron_expression": "0 0 31 2 *",
                "prompt": "Say OK",
            },
        )
        task_id = create_resp.json()["task_id"]
        cleanup.track("scheduled_task", task_id)

        # Trigger (this calls Gemini, may be slow)
        resp = await client.post(f"/api/scheduler/tasks/{task_id}/trigger")
        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"
