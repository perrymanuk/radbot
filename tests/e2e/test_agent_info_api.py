"""Agent info API e2e tests."""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


class TestAgentInfoAPI:
    async def test_get_agent_info(self, client):
        """GET /api/agent-info should return agent name and model info."""
        resp = await client.get("/api/agent-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "agent_name" in data
        assert "model" in data

    async def test_agent_info_has_sub_agents(self, client):
        """Agent info should include sub-agent model configuration."""
        resp = await client.get("/api/agent-info")
        assert resp.status_code == 200
        data = resp.json()
        agent_models = data.get("agent_models", {})
        assert isinstance(agent_models, dict)
        # Should have at least some agent model entries
        assert len(agent_models) > 0
