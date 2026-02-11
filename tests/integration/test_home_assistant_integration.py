"""
Integration tests for Home Assistant MCP integration.

These tests verify the integration between radbot and Home Assistant via MCP.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHomeAssistantIntegration:
    """Integration tests for Home Assistant MCP.

    Note: These tests will be skipped if Home Assistant integration environment variables are not set.
    """

    @pytest.fixture(autouse=True)
    def setup_environment(self):
        """Set up environment for testing Home Assistant integration."""
        # Store original environment variables
        self.original_ha_mcp_url = os.environ.get("HA_MCP_SSE_URL")
        self.original_ha_auth_token = os.environ.get("HA_AUTH_TOKEN")

        # Set test environment variables
        os.environ["HA_MCP_SSE_URL"] = "mock://homeassistant:8123/mcp_server/sse"
        os.environ["HA_AUTH_TOKEN"] = "mock_token_for_testing"

        yield

        # Restore original environment variables
        if self.original_ha_mcp_url:
            os.environ["HA_MCP_SSE_URL"] = self.original_ha_mcp_url
        else:
            os.environ.pop("HA_MCP_SSE_URL", None)

        if self.original_ha_auth_token:
            os.environ["HA_AUTH_TOKEN"] = self.original_ha_auth_token
        else:
            os.environ.pop("HA_AUTH_TOKEN", None)

    @patch("radbot.tools.mcp.mcp_homeassistant.config_loader")
    @patch("radbot.tools.mcp.mcp_homeassistant.McpToolset")
    def test_create_toolset_with_environment_variables(
        self, mock_mcp_toolset, mock_config_loader
    ):
        """Test that environment variables are correctly used when creating a toolset."""
        from radbot.tools.mcp.mcp_tools import create_home_assistant_toolset

        # Config returns empty to force env var fallback
        mock_config_loader.get_home_assistant_config.return_value = {}

        # Setup mock - from_server returns (tools, exit_stack) tuple
        mock_tools = [MagicMock(), MagicMock()]
        mock_exit_stack = MagicMock()
        mock_mcp_toolset.from_server = AsyncMock(
            return_value=(mock_tools, mock_exit_stack)
        )

        # Call function
        result = create_home_assistant_toolset()

        # Assertions - result should be a list of tools
        assert result == mock_tools

    @patch("radbot.tools.mcp.mcp_utils.create_home_assistant_toolset")
    def test_integration_workflow(self, mock_create_toolset):
        """Test full integration workflow from connection test to domain listing."""
        from radbot.tools.mcp.mcp_utils import test_home_assistant_connection

        # Setup mock - return a list of mock tools (not a toolset object)
        mock_tool1 = MagicMock()
        mock_tool1.name = "HassTurnOn"
        mock_tool1.description = "Turn on a device"
        mock_tool2 = MagicMock()
        mock_tool2.name = "HassTurnOff"
        mock_tool2.description = "Turn off a device"
        mock_create_toolset.return_value = [mock_tool1, mock_tool2]

        # Test connection
        conn_result = test_home_assistant_connection()
        assert isinstance(conn_result, dict)
        assert conn_result["success"] is True
        assert conn_result["tools_count"] == 2

    @patch("radbot.tools.mcp.mcp_ha_agent.create_find_ha_entities_tool")
    @patch("radbot.tools.mcp.mcp_ha_agent.search_home_assistant_entities")
    @patch("radbot.tools.mcp.mcp_ha_agent.create_home_assistant_toolset")
    def test_agent_creation_with_ha_integration(
        self, mock_create_toolset, mock_search_entities, mock_create_find_tool
    ):
        """Test creating an agent with Home Assistant integration."""
        from radbot.tools.mcp.mcp_tools import create_ha_mcp_enabled_agent

        # Setup mock toolset
        mock_create_toolset.return_value = []
        mock_create_find_tool.return_value = MagicMock(
            name="search_home_assistant_entities"
        )

        # Setup mock agent factory
        mock_agent = MagicMock()
        mock_agent_factory = MagicMock(return_value=mock_agent)

        # Create agent
        agent = create_ha_mcp_enabled_agent(
            mock_agent_factory, [], ensure_memory_tools=False
        )

        # Assertions
        mock_create_toolset.assert_called_once()


@patch("radbot.tools.mcp.mcp_utils.create_home_assistant_toolset")
def test_home_assistant_connection(mock_create_toolset):
    """Basic test for the home assistant connection test function."""
    from radbot.tools.mcp.mcp_utils import test_home_assistant_connection

    # Mock returns empty list to simulate no HA tools available
    mock_create_toolset.return_value = []

    result = test_home_assistant_connection()
    assert isinstance(result, dict)
    assert "success" in result
    # With no tools, success should be False
    assert result["success"] is False
