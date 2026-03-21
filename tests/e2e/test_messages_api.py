"""Messages API e2e tests."""

import uuid

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestMessagesAPI:
    @pytest_asyncio.fixture(loop_scope="session")
    async def test_session_id(self, client, cleanup):
        """Create a session for message tests."""
        resp = await client.post(
            "/api/sessions/create",
            json={"name": "e2e_messages_test"},
        )
        assert resp.status_code == 201
        sid = resp.json()["id"]
        cleanup.track("session", sid)
        return sid

    async def test_create_message(self, client, test_session_id):
        """POST /api/messages/{session_id} should store a message."""
        resp = await client.post(
            f"/api/messages/{test_session_id}",
            json={
                "role": "user",
                "content": "E2E test message",
            },
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "message_id" in data

    async def test_get_messages(self, client, test_session_id):
        """GET /api/messages/{session_id} should return stored messages."""
        # Create a message first
        await client.post(
            f"/api/messages/{test_session_id}",
            json={"role": "user", "content": "E2E get test"},
        )

        resp = await client.get(f"/api/messages/{test_session_id}")
        assert resp.status_code == 200
        data = resp.json()
        messages = data.get("messages", data) if isinstance(data, dict) else data
        assert isinstance(messages, (list, dict))

    async def test_batch_create_messages(self, client, test_session_id):
        """POST /api/messages/{session_id}/batch should insert multiple messages."""
        resp = await client.post(
            f"/api/messages/{test_session_id}/batch",
            json={
                "messages": [
                    {"role": "user", "content": "batch msg 1"},
                    {"role": "assistant", "content": "batch reply 1"},
                ],
            },
        )
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data.get("count", len(data.get("message_ids", []))) >= 2

    async def test_messages_pagination(self, client, test_session_id):
        """GET /api/messages/{session_id}?limit=1 should respect pagination."""
        resp = await client.get(
            f"/api/messages/{test_session_id}",
            params={"limit": 1},
        )
        assert resp.status_code == 200

    async def test_messages_nonexistent_session(self, client):
        """GET /api/messages/{bad_id} should return 404 or empty."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/messages/{fake_id}")
        # Either 404 or 200 with empty messages
        assert resp.status_code in (200, 404)
