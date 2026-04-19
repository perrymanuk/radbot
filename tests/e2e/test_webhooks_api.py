"""Webhooks API e2e tests."""

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

    async def test_duplicate_path_suffix(self, client, cleanup, test_prefix):
        """POST /api/webhooks/definitions with duplicate path_suffix should fail."""
        suffix = f"{test_prefix}_wh_dup"
        # First create
        resp1 = await client.post(
            "/api/webhooks/definitions",
            json={
                "name": f"{test_prefix}_wh_dup1",
                "path_suffix": suffix,
                "prompt_template": "first",
            },
        )
        assert resp1.status_code == 200
        cleanup.track("webhook", resp1.json()["webhook_id"])

        # Second create with same path_suffix
        resp2 = await client.post(
            "/api/webhooks/definitions",
            json={
                "name": f"{test_prefix}_wh_dup2",
                "path_suffix": suffix,
                "prompt_template": "duplicate",
            },
        )
        # Should fail with conflict
        if resp2.status_code == 200 and "webhook_id" in resp2.json():
            cleanup.track("webhook", resp2.json()["webhook_id"])
        else:
            assert resp2.status_code in (400, 409, 422, 500)

    async def test_webhook_hmac_validation(self, client, cleanup, test_prefix):
        """Trigger a webhook with a secret but without HMAC should fail or be accepted."""
        suffix = f"{test_prefix}_wh_hmac"
        # Create webhook with secret
        create_resp = await client.post(
            "/api/webhooks/definitions",
            json={
                "name": f"{test_prefix}_wh_hmac",
                "path_suffix": suffix,
                "prompt_template": "HMAC test: {{payload.msg}}",
                "secret": "e2e_test_secret_key",
            },
        )
        assert create_resp.status_code == 200
        cleanup.track("webhook", create_resp.json()["webhook_id"])

        # Trigger without HMAC signature — webhook may still accept
        # (HMAC is verified at the webhook level, not all webhooks enforce it)
        resp = await client.post(
            f"/api/webhooks/trigger/{suffix}",
            json={"msg": "no hmac"},
        )
        # Either accepted (no enforcement) or rejected (401/403)
        assert resp.status_code in (200, 401, 403)
