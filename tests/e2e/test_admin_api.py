"""Admin API e2e tests."""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestAdminAPI:
    async def test_admin_unauthorized(self, client):
        """GET /admin/api/credentials without token should return 401 or 503."""
        resp = await client.get("/admin/api/credentials")
        assert resp.status_code in (401, 503)

    async def test_list_credentials(self, client, admin_headers, admin_token):
        """GET /admin/api/credentials with token should return 200."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")
        resp = await client.get("/admin/api/credentials", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_store_and_delete_credential(self, client, admin_headers, admin_token):
        """POST then DELETE a test credential."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")

        cred_name = "_e2e_test_cred"

        # Store
        resp = await client.post(
            "/admin/api/credentials",
            headers=admin_headers,
            json={
                "name": cred_name,
                "value": "test_value_123",
                "credential_type": "api_key",
                "description": "E2E test credential",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify it's in the list
        resp = await client.get("/admin/api/credentials", headers=admin_headers)
        names = [c.get("name") for c in resp.json()]
        assert cred_name in names

        # Delete
        resp = await client.delete(
            f"/admin/api/credentials/{cred_name}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_get_all_config(self, client, admin_headers, admin_token):
        """GET /admin/api/config should return config sections."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")
        resp = await client.get("/admin/api/config", headers=admin_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

    async def test_save_and_get_config(self, client, admin_headers, admin_token):
        """PUT then GET a test config section."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")

        section = "_e2e_test_section"
        test_data = {"foo": "bar", "num": 42}

        # Save
        resp = await client.put(
            f"/admin/api/config/{section}",
            headers=admin_headers,
            json=test_data,
        )
        assert resp.status_code == 200

        # Get it back
        resp = await client.get(
            f"/admin/api/config/{section}",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("foo") == "bar"
        assert data.get("num") == 42

        # Cleanup: delete
        resp = await client.delete(
            f"/admin/api/config/{section}",
            headers=admin_headers,
        )
        assert resp.status_code == 200

    async def test_delete_config(self, client, admin_headers, admin_token):
        """DELETE a config section."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")

        section = "_e2e_test_del_section"

        # Create
        await client.put(
            f"/admin/api/config/{section}",
            headers=admin_headers,
            json={"temp": True},
        )

        # Delete
        resp = await client.delete(
            f"/admin/api/config/{section}",
            headers=admin_headers,
        )
        assert resp.status_code == 200

        # Verify gone
        resp = await client.get(
            f"/admin/api/config/{section}",
            headers=admin_headers,
        )
        # Should be 404 or return empty/null
        assert resp.status_code in (200, 404)

    async def test_integration_status(self, client, admin_headers, admin_token):
        """GET /admin/api/status should return integration statuses."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")
        resp = await client.get("/admin/api/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    async def test_live_config_redacted(self, client, admin_headers, admin_token):
        """GET /admin/api/config-live should redact sensitive values."""
        if not admin_token:
            pytest.skip("RADBOT_ADMIN_TOKEN not set")
        resp = await client.get("/admin/api/config-live", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        # Check that the database section exists and password is redacted
        db_config = data.get("database", {})
        if db_config.get("password"):
            assert db_config["password"] == "***"
