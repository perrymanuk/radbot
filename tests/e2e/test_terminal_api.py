"""Terminal API e2e tests."""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestTerminalAPI:
    async def test_terminal_status(self, client):
        """GET /terminal/status/ should return status info."""
        resp = await client.get("/terminal/status/")
        assert resp.status_code == 200

    async def test_list_terminal_sessions(self, client):
        """GET /terminal/sessions/ should return session list."""
        resp = await client.get("/terminal/sessions/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))

    async def test_list_workspaces(self, client):
        """GET /terminal/workspaces/ should return workspace list."""
        resp = await client.get("/terminal/workspaces/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))
