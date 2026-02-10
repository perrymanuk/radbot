"""
Integration tests for Home Assistant MCP integration.

These tests verify the integration between radbot and Home Assistant via MCP.
"""
import os
import pytest
import uuid
from unittest.mock import patch, MagicMock

from google.adk.tools.mcp_tool import McpToolset
from radbot.tools.mcp_tools import SseServerParams

from radbot.tools.mcp_tools import create_home_assistant_toolset, create_ha_mcp_enabled_agent
from radbot.tools.mcp_utils import (
    test_home_assistant_connection, 
    check_home_assistant_entity,
    list_home_assistant_domains
)


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
        os.environ["HA_MCP_SSE_URL"] = "mock://homeassistant:8123/api/mcp/stream"
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

    @patch('radbot.tools.mcp_tools.McpToolset')
    def test_create_toolset_with_environment_variables(self, mock_mcp_toolset):
        """Test that environment variables are correctly used when creating a toolset."""
        # Setup mock
        mock_instance = MagicMock()
        mock_mcp_toolset.return_value = mock_instance
        
        # Call function
        result = create_home_assistant_toolset()
        
        # Assertions
        assert result is mock_instance
        mock_mcp_toolset.assert_called_once()
        
        # Check that correct parameters were passed to McpToolset
        args, kwargs = mock_mcp_toolset.call_args
        server_params = kwargs.get("server_params", {})
        
        assert "home_assistant_mcp" in server_params
        ha_params = server_params["home_assistant_mcp"]
        assert ha_params.url == "mock://homeassistant:8123/api/mcp/stream"
        assert ha_params.headers["Authorization"] == "Bearer mock_token_for_testing"
    
    @patch('radbot.tools.mcp_utils.create_home_assistant_toolset')
    def test_integration_workflow(self, mock_create_toolset):
        """Test full integration workflow from connection test to domain listing."""
        # Setup mock toolset
        mock_toolset = MagicMock()
        mock_toolset.list_tools.return_value = [
            "home_assistant_mcp.light.turn_on",
            "home_assistant_mcp.light.turn_off",
            "home_assistant_mcp.light.get_state",
            "home_assistant_mcp.sensor.get_state",
            "home_assistant_mcp.climate.set_temperature"
        ]
        mock_create_toolset.return_value = mock_toolset
        
        # Test connection
        conn_result = test_home_assistant_connection()
        assert conn_result["success"] is True
        assert conn_result["tools_count"] == 5
        
        # List domains
        domains_result = list_home_assistant_domains()
        assert domains_result["success"] is True
        assert sorted(domains_result["domains"]) == ["climate", "light", "sensor"]
        assert domains_result["domains_count"] == 3
        
        # Check entity
        entity_result = check_home_assistant_entity("light.living_room")
        assert entity_result["success"] is True
        assert entity_result["domain"] == "light"
    
    @patch('radbot.tools.mcp_tools.create_home_assistant_toolset')
    def test_agent_creation_with_ha_integration(self, mock_create_toolset):
        """Test creating an agent with Home Assistant integration."""
        # Setup mock toolset
        mock_toolset = MagicMock()
        mock_create_toolset.return_value = mock_toolset
        
        # Setup mock agent factory
        mock_agent = MagicMock()
        mock_agent_factory = MagicMock(return_value=mock_agent)
        
        # Setup mock tools
        mock_tool1 = MagicMock()
        mock_tool2 = MagicMock()
        base_tools = [mock_tool1, mock_tool2]
        
        # Create agent
        agent = create_ha_mcp_enabled_agent(mock_agent_factory, base_tools)
        
        # Assertions
        assert agent is mock_agent
        mock_create_toolset.assert_called_once()
        mock_agent_factory.assert_called_once()
        
        # Check that tools were passed correctly
        args, kwargs = mock_agent_factory.call_args
        tools = kwargs.get("tools", [])
        assert len(tools) == 3
        assert tools[0] is mock_tool1
        assert tools[1] is mock_tool2
        assert tools[2] is mock_toolset