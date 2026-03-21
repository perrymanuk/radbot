"""Webhooks e2e tests via agent chat."""

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


class TestWebhooksAgent:
    async def test_agent_list_webhooks(self, live_server):
        """Ask the agent to list webhooks."""
        session_id = str(uuid.uuid4())
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response("Show my webhooks")
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "webhook", "no webhook", "none", "list", "registered"
            )
        finally:
            await ws.close()

    async def test_agent_create_webhook(self, live_server, client, test_prefix):
        """Create a webhook via agent chat."""
        session_id = str(uuid.uuid4())
        hook_name = f"{test_prefix}_e2e_hook"
        ws = await WSTestClient.connect(live_server, session_id)
        try:
            result = await ws.send_and_wait_response(
                f"Create a webhook called '{hook_name}' with path suffix '{hook_name}' "
                f"and prompt template 'Webhook fired: {{{{payload.event}}}}'"
            )
            text = assert_response_not_empty(result)
            assert_response_contains_any(
                result, "webhook", "created", hook_name, "success", "registered"
            )
        finally:
            await ws.close()

        # Cleanup via REST
        resp = await client.get("/api/webhooks/definitions")
        if resp.status_code == 200:
            webhooks = resp.json()
            for w in webhooks:
                if test_prefix in str(w.get("name", "")):
                    await client.delete(f"/api/webhooks/definitions/{w['webhook_id']}")
