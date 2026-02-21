"""Sessions API e2e tests."""

import uuid

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestSessionsAPI:
    async def test_create_session(self, client, cleanup):
        """POST /api/sessions/create should return a new session."""
        resp = await client.post(
            "/api/sessions/create",
            json={"name": "e2e_test_session"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "e2e_test_session"
        cleanup.track("session", data["id"])

    async def test_create_session_with_custom_id(self, client, cleanup):
        """POST /api/sessions/create with explicit session_id."""
        custom_id = str(uuid.uuid4())
        resp = await client.post(
            "/api/sessions/create",
            json={"session_id": custom_id, "name": "e2e_test_custom"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == custom_id
        cleanup.track("session", custom_id)

    async def test_list_sessions(self, client, cleanup):
        """GET /api/sessions/ should include the created session."""
        # Create a session first
        create_resp = await client.post(
            "/api/sessions/create",
            json={"name": "e2e_test_list"},
        )
        session_id = create_resp.json()["id"]
        cleanup.track("session", session_id)

        # List sessions
        resp = await client.get("/api/sessions/")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        ids = [s["id"] for s in data["sessions"]]
        assert session_id in ids

    async def test_rename_session(self, client, cleanup):
        """PUT /api/sessions/{id}/rename should update the name."""
        # Create
        create_resp = await client.post(
            "/api/sessions/create",
            json={"name": "e2e_test_rename_old"},
        )
        session_id = create_resp.json()["id"]
        cleanup.track("session", session_id)

        # Rename
        resp = await client.put(
            f"/api/sessions/{session_id}/rename",
            json={"name": "e2e_test_rename_new"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "e2e_test_rename_new"

    async def test_delete_session(self, client):
        """DELETE /api/sessions/{id} should remove the session."""
        # Create
        create_resp = await client.post(
            "/api/sessions/create",
            json={"name": "e2e_test_delete"},
        )
        session_id = create_resp.json()["id"]

        # Delete
        resp = await client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    async def test_get_nonexistent_session(self, client):
        """GET /api/sessions/{bad_id} should return 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/sessions/{fake_id}")
        assert resp.status_code == 404

    async def test_full_session_lifecycle(self, client):
        """Create -> rename -> reset -> delete a session."""
        # Create
        resp = await client.post(
            "/api/sessions/create",
            json={"name": "e2e_lifecycle"},
        )
        assert resp.status_code == 201
        session_id = resp.json()["id"]

        # Rename
        resp = await client.put(
            f"/api/sessions/{session_id}/rename",
            json={"name": "e2e_lifecycle_renamed"},
        )
        assert resp.status_code == 200

        # Reset
        resp = await client.post(f"/api/sessions/{session_id}/reset")
        assert resp.status_code == 200

        # Delete
        resp = await client.delete(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
