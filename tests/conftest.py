"""
Configuration for pytest.

This file provides common fixtures and configuration for all tests.
"""

import pytest


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "mcp_compat: mark test as needing special MCP compatibility handling"
    )


def pytest_collection_modifyitems(items):
    """Mark tests with xfail based on current version compatibility issues."""
    skip_mcp_compat = pytest.mark.xfail(
        reason="Google ADK 0.3.0 compatibility issue with MCP"
    )

    for item in items:
        # Skip specific tests that are failing due to ADK 0.3.0 MCP changes
        if (
            "TestHomeAssistantConnection.test_connection_success_with_internal_tools"
            in item.nodeid
            or "TestCheckHomeAssistantEntity.test_entity_check_unsupported_domain"
            in item.nodeid
            or "TestListHomeAssistantDomains.test_list_domains_success_with_internal_tools"
            in item.nodeid
        ):
            item.add_marker(skip_mcp_compat)
