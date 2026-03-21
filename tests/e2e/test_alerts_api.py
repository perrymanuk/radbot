"""Alerts API e2e tests."""

import uuid

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


def _make_alert_payload(fingerprint: str = None, alertname: str = "E2ETestAlert"):
    """Build an Alertmanager v4 webhook payload."""
    return {
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": alertname,
                    "severity": "warning",
                    "instance": "e2e-test:9090",
                },
                "annotations": {"summary": "E2E test alert"},
                "startsAt": "2026-03-21T00:00:00Z",
                "fingerprint": fingerprint or f"e2e_{uuid.uuid4().hex[:12]}",
            }
        ]
    }


class TestAlertsWebhook:
    async def test_alertmanager_webhook_ingestion(self, client):
        """POST /api/alerts/alertmanager should accept a valid payload."""
        resp = await client.post(
            "/api/alerts/alertmanager",
            json=_make_alert_payload(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["alerts_received"] == 1

    async def test_alertmanager_empty_payload(self, client):
        """POST /api/alerts/alertmanager with empty alerts should return 0."""
        resp = await client.post(
            "/api/alerts/alertmanager",
            json={"alerts": []},
        )
        assert resp.status_code == 200
        assert resp.json()["alerts_received"] == 0

    async def test_alertmanager_invalid_json(self, client):
        """POST /api/alerts/alertmanager with invalid body should return 400."""
        resp = await client.post(
            "/api/alerts/alertmanager",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400


class TestAlertsManagement:
    async def test_list_alerts(self, client, admin_headers, admin_token):
        """GET /api/alerts/ should return alert list."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")
        resp = await client.get("/api/alerts/", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "total" in data

    async def test_get_nonexistent_alert(self, client, admin_headers, admin_token):
        """GET /api/alerts/{bad_uuid} should return 404."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/alerts/{fake_id}", headers=admin_headers)
        assert resp.status_code == 404

    async def test_get_alert_invalid_uuid(self, client, admin_headers, admin_token):
        """GET /api/alerts/not-a-uuid should return 400."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")
        resp = await client.get("/api/alerts/not-a-uuid", headers=admin_headers)
        assert resp.status_code == 400

    async def test_dismiss_nonexistent_alert(self, client, admin_headers, admin_token):
        """POST /api/alerts/{bad_uuid}/dismiss should return 404."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/alerts/{fake_id}/dismiss", headers=admin_headers
        )
        assert resp.status_code == 404


class TestAlertsPolicyCRUD:
    async def test_policy_lifecycle(self, client, admin_headers, admin_token, cleanup, test_prefix):
        """Create, list, update, and delete a remediation policy."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")

        # Create
        resp = await client.post(
            "/api/alerts/policies/",
            headers=admin_headers,
            json={
                "alertname_pattern": f"{test_prefix}_E2ETest.*",
                "action": "auto",
                "max_auto_remediations": 1,
                "window_minutes": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        policy_id = data["policy_id"]
        cleanup.track("alert_policy", policy_id)

        # List
        resp = await client.get("/api/alerts/policies/", headers=admin_headers)
        assert resp.status_code == 200
        policies = resp.json()["policies"]
        ids = [str(p.get("policy_id")) for p in policies]
        assert policy_id in ids

        # Update
        resp = await client.put(
            f"/api/alerts/policies/{policy_id}",
            headers=admin_headers,
            json={"max_auto_remediations": 5},
        )
        assert resp.status_code == 200

        # Delete
        resp = await client.delete(
            f"/api/alerts/policies/{policy_id}",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    async def test_list_policies(self, client, admin_headers, admin_token):
        """GET /api/alerts/policies/ should return policy list."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")
        resp = await client.get("/api/alerts/policies/", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "policies" in data
        assert "count" in data
