"""Webhooks API e2e tests."""

import uuid

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestWebhooksAPI:
    async def test_create_webhook(self, client, cleanup, test_prefix):
        """POST /api/webhooks/definitions should create a webhook."""
        suffix = f"{test_prefix}_wh"
        resp = await client.post(
            "/api/webhooks/definitions",
            json={
                "name": f"{test_prefix}_webhook",
                "path_suffix": suffix,
                "prompt_template": "E2E test webhook received: {{payload.msg}}",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "webhook_id" in data
        cleanup.track("webhook", data["webhook_id"])

    async def test_list_webhooks(self, client, cleanup, test_prefix):
        """GET /api/webhooks/definitions should include the webhook with masked secret."""
        suffix = f"{test_prefix}_wh_list"
        create_resp = await client.post(
            "/api/webhooks/definitions",
            json={
                "name": f"{test_prefix}_wh_list",
                "path_suffix": suffix,
                "prompt_template": "test: {{payload.x}}",
                "secret": "supersecret",
            },
        )
        webhook_id = create_resp.json()["webhook_id"]
        cleanup.track("webhook", webhook_id)

        resp = await client.get("/api/webhooks/definitions")
        assert resp.status_code == 200
        webhooks = resp.json()
        assert isinstance(webhooks, list)

        # Find our webhook
        ours = [w for w in webhooks if str(w.get("webhook_id")) == webhook_id]
        assert len(ours) == 1
        # Secret should be masked
        assert ours[0].get("secret") == "***"

    async def test_trigger_webhook(self, client, cleanup, test_prefix):
        """POST /api/webhooks/trigger/{path} should return accepted."""
        suffix = f"{test_prefix}_wh_trigger"
        create_resp = await client.post(
            "/api/webhooks/definitions",
            json={
                "name": f"{test_prefix}_wh_trig",
                "path_suffix": suffix,
                "prompt_template": "Webhook test: {{payload.msg}}",
            },
        )
        webhook_id = create_resp.json()["webhook_id"]
        cleanup.track("webhook", webhook_id)

        resp = await client.post(
            f"/api/webhooks/trigger/{suffix}",
            json={"msg": "hello from e2e"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    async def test_trigger_nonexistent(self, client):
        """POST /api/webhooks/trigger/{bad_path} should return 404."""
        resp = await client.post(
            "/api/webhooks/trigger/nonexistent_e2e_path",
            json={"x": 1},
        )
        assert resp.status_code == 404

    async def test_delete_webhook(self, client, test_prefix):
        """DELETE /api/webhooks/definitions/{id} should remove it."""
        suffix = f"{test_prefix}_wh_del"
        create_resp = await client.post(
            "/api/webhooks/definitions",
            json={
                "name": f"{test_prefix}_wh_del",
                "path_suffix": suffix,
                "prompt_template": "delete me",
            },
        )
        webhook_id = create_resp.json()["webhook_id"]

        resp = await client.delete(f"/api/webhooks/definitions/{webhook_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
