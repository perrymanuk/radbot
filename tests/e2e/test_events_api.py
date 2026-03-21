"""Events API e2e tests."""

import uuid

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestEventsAPI:
    async def test_get_events_empty_session(self, client):
        """GET /api/events/{session_id} for a new session should return empty or 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/events/{fake_id}")
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list)
        else:
            assert resp.status_code == 404
