"""Terminal API e2e tests — REST endpoints for workspaces and sessions."""

import uuid

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestTerminalAPI:
    """Basic terminal REST endpoint tests (no Claude Code CLI required)."""

    async def test_terminal_status(self, client):
        """GET /terminal/status/ should return status info."""
        resp = await client.get("/terminal/status/")
        assert resp.status_code == 200

    async def test_list_terminal_sessions(self, client):
        """GET /terminal/sessions/ should return session list."""
        resp = await client.get("/terminal/sessions/")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data

    async def test_list_workspaces(self, client):
        """GET /terminal/workspaces/ should return workspace list."""
        resp = await client.get("/terminal/workspaces/")
        assert resp.status_code == 200
        data = resp.json()
        assert "workspaces" in data


class TestWorkspaceCRUD:
    """Workspace create/update/delete tests."""

    async def test_create_scratch_workspace(self, client, cleanup):
        """POST /terminal/workspaces/scratch/ should create a workspace."""
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-scratch-test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "workspace" in data
        ws = data["workspace"]
        assert ws["owner"] == "_scratch"
        assert ws["name"] == "e2e-scratch-test"
        cleanup.track("workspace", ws["workspace_id"])

    async def test_update_workspace(self, client, cleanup):
        """PUT /terminal/workspaces/{id} should update name and description."""
        # Create a scratch workspace first
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-update-test"},
        )
        assert resp.status_code == 200
        ws_id = resp.json()["workspace"]["workspace_id"]
        cleanup.track("workspace", ws_id)

        # Update it
        resp = await client.put(
            f"/terminal/workspaces/{ws_id}",
            json={"name": "updated-name", "description": "updated-desc"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

        # Verify the update via list
        resp = await client.get("/terminal/workspaces/")
        workspaces = resp.json()["workspaces"]
        updated = [w for w in workspaces if w["workspace_id"] == ws_id]
        assert len(updated) == 1
        assert updated[0]["name"] == "updated-name"
        assert updated[0]["description"] == "updated-desc"

    async def test_delete_workspace(self, client):
        """DELETE /terminal/workspaces/{id} should soft-delete."""
        # Create a scratch workspace
        resp = await client.post(
            "/terminal/workspaces/scratch/",
            json={"name": "e2e-delete-test"},
        )
        assert resp.status_code == 200
        ws_id = resp.json()["workspace"]["workspace_id"]

        # Delete it
        resp = await client.delete(f"/terminal/workspaces/{ws_id}")
        assert resp.status_code == 200

        # Verify it's gone from active list
        resp = await client.get("/terminal/workspaces/")
        workspaces = resp.json()["workspaces"]
        assert all(w["workspace_id"] != ws_id for w in workspaces)

    async def test_delete_nonexistent_workspace(self, client):
        """DELETE /terminal/workspaces/{bad_id} should 404."""
        resp = await client.delete(f"/terminal/workspaces/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_update_nonexistent_workspace(self, client):
        """PUT /terminal/workspaces/{bad_id} should 404."""
        resp = await client.put(
            f"/terminal/workspaces/{uuid.uuid4()}",
            json={"name": "nope"},
        )
        assert resp.status_code == 404


class TestSessionErrors:
    """Terminal session error cases."""

    async def test_create_session_missing_workspace_id(self, client):
        """POST /terminal/sessions/ without workspace_id should 400."""
        resp = await client.post("/terminal/sessions/", json={})
        assert resp.status_code == 400

    async def test_create_session_invalid_workspace(self, client):
        """POST /terminal/sessions/ with nonexistent workspace should 404."""
        resp = await client.post(
            "/terminal/sessions/",
            json={"workspace_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    async def test_kill_nonexistent_session(self, client):
        """DELETE /terminal/sessions/{bad_id} should 404."""
        resp = await client.delete(f"/terminal/sessions/{uuid.uuid4()}")
        assert resp.status_code == 404
