"""Unit tests for the Home Assistant dashboard tools."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

from radbot.tools.homeassistant.ha_dashboard_tools import (
    create_ha_dashboard,
    delete_ha_dashboard,
    get_ha_dashboard_config,
    list_ha_dashboards,
    save_ha_dashboard_config,
    update_ha_dashboard,
)

# All tools use get_ha_ws_client(), so we patch it at module level
_PATCH_CLIENT = "radbot.tools.homeassistant.ha_dashboard_tools.get_ha_ws_client"


def _mock_client(**method_returns):
    """Build an AsyncMock WS client with given return values."""
    client = AsyncMock()
    for method, ret in method_returns.items():
        getattr(client, method).return_value = ret
    return client


# ---------------------------------------------------------------------------
# Client unavailable
# ---------------------------------------------------------------------------

class TestClientUnavailable:
    def test_list_dashboards_no_client(self):
        async def _fut():
            return await list_ha_dashboards()
        with patch(_PATCH_CLIENT, return_value=None):
            result = asyncio.run(_fut())
            assert result["status"] == "error"
            assert "not configured" in result["message"]

    def test_get_config_no_client(self):
        async def _fut():
            return await get_ha_dashboard_config()
        with patch(_PATCH_CLIENT, return_value=None):
            result = asyncio.run(_fut())
            assert result["status"] == "error"

    def test_create_no_client(self):
        async def _fut():
            return await create_ha_dashboard("test", "Test")
        with patch(_PATCH_CLIENT, return_value=None):
            result = asyncio.run(_fut())
            assert result["status"] == "error"


# ---------------------------------------------------------------------------
# list_ha_dashboards
# ---------------------------------------------------------------------------

class TestListDashboards:
    def test_success(self):
        dashboards = [{"id": 1, "url_path": "test-dash", "title": "Test"}]
        client = _mock_client(list_dashboards=dashboards)

        async def _fut():
            return await list_ha_dashboards()
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "success"
            assert result["dashboards"] == dashboards

    def test_error_from_ha(self):
        client = AsyncMock()
        client.list_dashboards.side_effect = RuntimeError("WS error")

        async def _fut():
            return await list_ha_dashboards()
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "error"
            assert "WS error" in result["message"]


# ---------------------------------------------------------------------------
# get_ha_dashboard_config
# ---------------------------------------------------------------------------

class TestGetDashboardConfig:
    def test_success_default(self):
        config = {"views": [{"title": "Home"}]}
        client = _mock_client(get_dashboard_config=config)

        async def _fut():
            return await get_ha_dashboard_config()
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "success"
            assert result["config"] == config
            assert result["url_path"] == "(default)"

    def test_success_specific(self):
        config = {"views": [{"title": "Energy"}]}
        client = _mock_client(get_dashboard_config=config)

        async def _fut():
            return await get_ha_dashboard_config("energy")
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "success"
            assert result["url_path"] == "energy"


# ---------------------------------------------------------------------------
# create_ha_dashboard
# ---------------------------------------------------------------------------

class TestCreateDashboard:
    def test_success(self):
        created = {"id": 5, "url_path": "new-dash", "title": "New Dash"}
        client = _mock_client(create_dashboard=created)

        async def _fut():
            return await create_ha_dashboard("new-dash", "New Dash", icon="mdi:star")
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "success"
            assert result["dashboard"] == created
            client.create_dashboard.assert_called_once_with(
                url_path="new-dash",
                title="New Dash",
                icon="mdi:star",
                require_admin=False,
                show_in_sidebar=True,
            )

    def test_error(self):
        client = AsyncMock()
        client.create_dashboard.side_effect = RuntimeError("already exists")

        async def _fut():
            return await create_ha_dashboard("dup", "Dup")
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "error"
            assert "already exists" in result["message"]


# ---------------------------------------------------------------------------
# update_ha_dashboard
# ---------------------------------------------------------------------------

class TestUpdateDashboard:
    def test_success(self):
        updated = {"id": 3, "title": "Renamed"}
        client = _mock_client(update_dashboard=updated)

        async def _fut():
            return await update_ha_dashboard(3, title="Renamed")
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "success"
            assert result["dashboard"] == updated

    def test_no_fields(self):
        client = _mock_client()

        async def _fut():
            return await update_ha_dashboard(3)
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "error"
            assert "No fields" in result["message"]


# ---------------------------------------------------------------------------
# delete_ha_dashboard
# ---------------------------------------------------------------------------

class TestDeleteDashboard:
    def test_success(self):
        client = _mock_client(delete_dashboard=None)

        async def _fut():
            return await delete_ha_dashboard(7)
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "success"
            assert result["deleted_id"] == 7

    def test_error(self):
        client = AsyncMock()
        client.delete_dashboard.side_effect = RuntimeError("not found")

        async def _fut():
            return await delete_ha_dashboard(999)
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "error"


# ---------------------------------------------------------------------------
# save_ha_dashboard_config
# ---------------------------------------------------------------------------

class TestSaveDashboardConfig:
    def test_success(self):
        client = _mock_client(save_dashboard_config=None)
        config_json = json.dumps({"views": [{"title": "My View"}]})

        async def _fut():
            return await save_ha_dashboard_config(config_json, "my-dash")
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "success"
            assert result["url_path"] == "my-dash"

    def test_invalid_json(self):
        client = _mock_client()

        async def _fut():
            return await save_ha_dashboard_config("not json{{{", "x")
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "error"
            assert "Invalid JSON" in result["message"]

    def test_non_object_json(self):
        client = _mock_client()

        async def _fut():
            return await save_ha_dashboard_config("[1,2,3]", "x")
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "error"
            assert "JSON object" in result["message"]

    def test_default_url_path(self):
        client = _mock_client(save_dashboard_config=None)
        config_json = json.dumps({"views": []})

        async def _fut():
            return await save_ha_dashboard_config(config_json)
        with patch(_PATCH_CLIENT, return_value=client):
            result = asyncio.run(_fut())
            assert result["status"] == "success"
            assert result["url_path"] == "(default)"
