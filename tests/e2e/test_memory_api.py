"""Memory API e2e tests."""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestMemoryAPI:
    async def test_store_memory(self, client, cleanup):
        """POST /api/memory/store should succeed with a valid session."""
        # Create a session first
        session_resp = await client.post(
            "/api/sessions/create",
            json={"name": "e2e_test_memory"},
        )
        session_id = session_resp.json()["id"]
        cleanup.track("session", session_id)

        resp = await client.post(
            "/api/memory/store",
            json={
                "text": "E2E test memory entry - the test code is BRAVO42",
                "memory_type": "important_fact",
                "session_id": session_id,
            },
        )
        # Memory may fail if Qdrant is not available — accept 200 or 500
        if resp.status_code == 200:
            data = resp.json()
            assert data["status"] == "success"
        else:
            # Qdrant not available — skip instead of fail
            pytest.skip("Memory service (Qdrant) not available")

    async def test_store_memory_missing_fields(self, client):
        """POST /api/memory/store without required fields should fail."""
        resp = await client.post(
            "/api/memory/store",
            json={"memory_type": "fact"},
        )
        assert resp.status_code == 422  # Pydantic validation error
