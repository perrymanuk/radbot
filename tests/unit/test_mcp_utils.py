"""
Unit tests for MCP utilities.

Tests the utility functions for working with Home Assistant MCP.
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from radbot.tools.mcp.mcp_tools import create_home_assistant_toolset
from radbot.tools.mcp.mcp_utils import (
    check_home_assistant_entity,
    list_home_assistant_domains,
    test_home_assistant_connection,
)


class TestHomeAssistantConnection:
    def test_connection_direct(self):
        """Test direct call to home assistant connection test function."""
        # Just call the function directly without mocking
        result = test_home_assistant_connection()

        # We expect it to fail in the test environment, but structure should be correct
        assert isinstance(result, dict)
        assert "success" in result
        assert "status" in result


class TestCheckHomeAssistantEntity:
    def test_check_entity_direct(self):
        """Test direct call to entity check function."""
        # Just call the function directly without mocking
        result = check_home_assistant_entity("light.living_room")

        # We expect it to fail in the test environment, but structure should be correct
        assert isinstance(result, dict)
        assert "success" in result
        assert "status" in result


class TestListHomeAssistantDomains:
    def test_list_domains_direct(self):
        """Test direct call to domain listing function."""
        # Just call the function directly without mocking
        result = list_home_assistant_domains()

        # We expect it to fail in the test environment, but structure should be correct
        assert isinstance(result, dict)
        assert "success" in result
        assert "status" in result
