"""
Unit tests for MCP tools.

Tests the functionality of the Home Assistant MCP integration tools.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from radbot.tools.mcp.mcp_tools import (
    create_ha_mcp_enabled_agent,
    create_home_assistant_toolset,
)


class TestCreateHomeAssistantToolset:
    @patch("radbot.tools.mcp.mcp_homeassistant.os.getenv")
    @patch("radbot.tools.mcp.mcp_homeassistant.config_loader")
    @patch("radbot.tools.mcp.mcp_homeassistant.McpToolset")
    def test_create_home_assistant_toolset_success(
        self, mock_mcp_toolset, mock_config_loader, mock_getenv
    ):
        """Test successful creation of Home Assistant McpToolset."""
        # Setup config to return empty (force env var fallback)
        mock_config_loader.get_home_assistant_config.return_value = {}

        # Setup environment variables
        mock_getenv.side_effect = lambda key: {
            "HA_MCP_SSE_URL": "http://homeassistant:8123/mcp_server/sse",
            "HA_AUTH_TOKEN": "fake_token_123",
        }.get(key)

        # Setup mock McpToolset.from_server as async - returns (tools, exit_stack)
        mock_tools = [MagicMock(), MagicMock()]
        mock_exit_stack = MagicMock()
        mock_mcp_toolset.from_server = AsyncMock(
            return_value=(mock_tools, mock_exit_stack)
        )

        # Call function
        result = create_home_assistant_toolset()

        # Assertions - now we expect a list of tools
        assert result == mock_tools

    @patch("radbot.tools.mcp.mcp_homeassistant.os.getenv")
    @patch("radbot.tools.mcp.mcp_homeassistant.config_loader")
    def test_missing_url_environment_variable(self, mock_config_loader, mock_getenv):
        """Test handling of missing Home Assistant MCP URL environment variable."""
        mock_config_loader.get_home_assistant_config.return_value = {}

        # Setup missing HA_MCP_SSE_URL
        mock_getenv.side_effect = lambda key: {
            "HA_MCP_SSE_URL": None,
            "HA_AUTH_TOKEN": "fake_token_123",
        }.get(key)

        # Call function
        result = create_home_assistant_toolset()

        # Assertions - should return empty list, not None
        assert result == []

    @patch("radbot.tools.mcp.mcp_homeassistant.os.getenv")
    @patch("radbot.tools.mcp.mcp_homeassistant.config_loader")
    def test_missing_token_environment_variable(self, mock_config_loader, mock_getenv):
        """Test handling of missing Home Assistant auth token environment variable."""
        mock_config_loader.get_home_assistant_config.return_value = {}

        # Setup missing HA_AUTH_TOKEN
        mock_getenv.side_effect = lambda key: {
            "HA_MCP_SSE_URL": "http://homeassistant:8123/mcp_server/sse",
            "HA_AUTH_TOKEN": None,
        }.get(key)

        # Call function
        result = create_home_assistant_toolset()

        # Assertions - should return empty list, not None
        assert result == []

    @patch("radbot.tools.mcp.mcp_homeassistant.os.getenv")
    @patch("radbot.tools.mcp.mcp_homeassistant.config_loader")
    @patch("radbot.tools.mcp.mcp_homeassistant.McpToolset")
    def test_exception_handling(
        self, mock_mcp_toolset, mock_config_loader, mock_getenv
    ):
        """Test exception handling during toolset creation."""
        mock_config_loader.get_home_assistant_config.return_value = {}

        # Setup environment variables
        mock_getenv.side_effect = lambda key: {
            "HA_MCP_SSE_URL": "http://homeassistant:8123/mcp_server/sse",
            "HA_AUTH_TOKEN": "fake_token_123",
        }.get(key)

        # Setup exception in McpToolset.from_server
        mock_mcp_toolset.from_server = AsyncMock(
            side_effect=Exception("Test exception")
        )

        # Call function
        result = create_home_assistant_toolset()

        # Assertions - now expecting an empty list on error, not None
        assert result == []


class TestCreateHaMcpEnabledAgent:
    @patch("radbot.tools.mcp.mcp_ha_agent.create_find_ha_entities_tool")
    @patch("radbot.tools.mcp.mcp_ha_agent.search_home_assistant_entities")
    @patch("radbot.tools.mcp.mcp_ha_agent.create_home_assistant_toolset")
    def test_create_agent_with_ha_toolset(
        self, mock_create_ha_toolset, mock_search_entities, mock_create_find_tool
    ):
        """Test that create_ha_mcp_enabled_agent calls create_home_assistant_toolset."""
        mock_create_ha_toolset.return_value = []
        mock_create_find_tool.return_value = MagicMock(
            name="search_home_assistant_entities"
        )

        mock_factory = MagicMock(return_value=MagicMock())
        agent = create_ha_mcp_enabled_agent(mock_factory, [], ensure_memory_tools=False)

        # Verify create_home_assistant_toolset was called
        mock_create_ha_toolset.assert_called_once()

    @patch("radbot.tools.mcp.mcp_ha_agent.create_find_ha_entities_tool")
    @patch("radbot.tools.mcp.mcp_ha_agent.search_home_assistant_entities")
    @patch("radbot.tools.mcp.mcp_ha_agent.create_home_assistant_toolset")
    def test_create_agent_without_ha_toolset(
        self, mock_create_ha_toolset, mock_search_entities, mock_create_find_tool
    ):
        """Test agent creation when no HA toolset available."""
        mock_create_ha_toolset.return_value = []
        mock_create_find_tool.return_value = MagicMock(
            name="search_home_assistant_entities"
        )

        mock_factory = MagicMock(return_value=MagicMock())
        agent = create_ha_mcp_enabled_agent(mock_factory, [], ensure_memory_tools=False)

        mock_create_ha_toolset.assert_called_once()

    @patch("radbot.tools.mcp.mcp_ha_agent.create_find_ha_entities_tool")
    @patch("radbot.tools.mcp.mcp_ha_agent.search_home_assistant_entities")
    @patch("radbot.tools.mcp.mcp_ha_agent.create_home_assistant_toolset")
    def test_create_agent_with_no_base_tools(
        self, mock_create_ha_toolset, mock_search_entities, mock_create_find_tool
    ):
        """Test agent creation with no base tools."""
        mock_create_ha_toolset.return_value = []
        mock_create_find_tool.return_value = MagicMock(
            name="search_home_assistant_entities"
        )

        mock_factory = MagicMock(return_value=MagicMock())
        agent = create_ha_mcp_enabled_agent(mock_factory, ensure_memory_tools=False)

        mock_create_ha_toolset.assert_called_once()

    @patch("radbot.tools.mcp.mcp_ha_agent.create_find_ha_entities_tool")
    @patch("radbot.tools.mcp.mcp_ha_agent.search_home_assistant_entities")
    @patch("radbot.tools.mcp.mcp_ha_agent.create_home_assistant_toolset")
    def test_exception_handling(
        self, mock_create_ha_toolset, mock_search_entities, mock_create_find_tool
    ):
        """Test exception handling during agent creation."""
        mock_create_ha_toolset.return_value = ["tool1", "tool2"]
        mock_create_find_tool.return_value = MagicMock(
            name="search_home_assistant_entities"
        )
        mock_factory = MagicMock(side_effect=Exception("Test exception"))

        # Call function
        agent = create_ha_mcp_enabled_agent(mock_factory, ensure_memory_tools=False)

        # Assertions
        assert agent is None
        mock_create_ha_toolset.assert_called_once()
