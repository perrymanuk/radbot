"""Tasks API e2e tests."""

import uuid

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestTasksAPI:
    @pytest_asyncio.fixture(loop_scope="session")
    async def test_project_id(self, client):
        """Get or verify a project exists for creating tasks."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        projects = resp.json()
        if projects:
            return projects[0]["project_id"]
        # If no projects exist, we can't create tasks via the API alone
        pytest.skip("No projects available for task creation tests")

    async def test_create_task(self, client, cleanup, test_project_id, test_prefix):
        """POST /api/tasks should create a new task."""
        resp = await client.post(
            "/api/tasks",
            json={
                "title": f"{test_prefix}_task",
                "description": "E2E test task",
                "project_id": test_project_id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "task_id" in data
        cleanup.track("task", data["task_id"])

    async def test_create_task_no_project(self, client, test_prefix):
        """POST /api/tasks without project_id should return 400."""
        resp = await client.post(
            "/api/tasks",
            json={"title": f"{test_prefix}_bad"},
        )
        assert resp.status_code == 400

    async def test_list_tasks(self, client, cleanup, test_project_id, test_prefix):
        """GET /api/tasks should include the created task."""
        # Create
        create_resp = await client.post(
            "/api/tasks",
            json={
                "title": f"{test_prefix}_list",
                "project_id": test_project_id,
            },
        )
        task_id = create_resp.json()["task_id"]
        cleanup.track("task", task_id)

        # List
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        tasks = resp.json()
        assert isinstance(tasks, list)
        ids = [t.get("task_id") for t in tasks]
        assert task_id in ids

    async def test_update_task_status(self, client, cleanup, test_project_id, test_prefix):
        """PUT /api/tasks/{id} should update the status."""
        create_resp = await client.post(
            "/api/tasks",
            json={
                "title": f"{test_prefix}_status",
                "project_id": test_project_id,
            },
        )
        task_id = create_resp.json()["task_id"]
        cleanup.track("task", task_id)

        resp = await client.put(
            f"/api/tasks/{task_id}",
            json={"status": "inprogress"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    async def test_update_task_title(self, client, cleanup, test_project_id, test_prefix):
        """PUT /api/tasks/{id} should update the title."""
        create_resp = await client.post(
            "/api/tasks",
            json={
                "title": f"{test_prefix}_title_old",
                "project_id": test_project_id,
            },
        )
        task_id = create_resp.json()["task_id"]
        cleanup.track("task", task_id)

        resp = await client.put(
            f"/api/tasks/{task_id}",
            json={"title": f"{test_prefix}_title_new"},
        )
        assert resp.status_code == 200

    async def test_delete_task(self, client, test_project_id, test_prefix):
        """DELETE /api/tasks/{id} should remove the task."""
        create_resp = await client.post(
            "/api/tasks",
            json={
                "title": f"{test_prefix}_del",
                "project_id": test_project_id,
            },
        )
        task_id = create_resp.json()["task_id"]

        resp = await client.delete(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    async def test_get_projects(self, client):
        """GET /api/projects should return a list."""
        resp = await client.get("/api/projects")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_task_lifecycle(self, client, test_project_id, test_prefix):
        """Create -> update status -> update title -> delete."""
        # Create
        resp = await client.post(
            "/api/tasks",
            json={
                "title": f"{test_prefix}_lifecycle",
                "project_id": test_project_id,
            },
        )
        assert resp.status_code == 200
        task_id = resp.json()["task_id"]

        # Update status
        resp = await client.put(
            f"/api/tasks/{task_id}",
            json={"status": "inprogress"},
        )
        assert resp.status_code == 200

        # Update title
        resp = await client.put(
            f"/api/tasks/{task_id}",
            json={"title": f"{test_prefix}_lifecycle_done"},
        )
        assert resp.status_code == 200

        # Complete
        resp = await client.put(
            f"/api/tasks/{task_id}",
            json={"status": "done"},
        )
        assert resp.status_code == 200

        # Delete
        resp = await client.delete(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
