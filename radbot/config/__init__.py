"""
Configuration management for the radbot agent framework.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from radbot.config.config_loader import ConfigLoader

# Import both configuration systems to support backwards compatibility
from radbot.config.settings import ConfigManager

# Configure logging for config module
logger = logging.getLogger(__name__)

# Create default instances
config_manager = ConfigManager()
config_loader = ConfigLoader()


# Helper functions to provide a unified interface
def get_agent_config() -> Dict[str, Any]:
    """
    Get the agent configuration.

    First tries the YAML configuration, then falls back to the legacy ConfigManager.

    Returns:
        Dictionary containing the agent configuration
    """
    # Try YAML config first
    yaml_config = config_loader.get_agent_config()

    # If empty or not found, fall back to legacy config
    if not yaml_config:
        logger.debug("Using legacy ConfigManager for agent configuration")
        return {
            "main_model": config_manager.get_main_model(),
            "sub_agent_model": config_manager.get_sub_agent_model(),
            "use_vertex_ai": config_manager.is_using_vertex_ai(),
        }

    return yaml_config


def get_cache_config() -> Dict[str, Any]:
    """
    Get the cache configuration.

    First tries the YAML configuration, then falls back to the environment variables.

    Returns:
        Dictionary containing the cache configuration
    """
    # Try YAML config first
    cache_config = config_loader.get_cache_config()

    # If empty or not found, fall back to environment variables
    if not cache_config:
        logger.debug("Using legacy environment variables for cache configuration")
        from radbot.config.cache_settings import (
            get_cache_config as get_legacy_cache_config,
        )

        return get_legacy_cache_config()

    return cache_config


def get_home_assistant_config() -> Dict[str, Any]:
    """
    Get the Home Assistant configuration.

    First tries the YAML configuration, then falls back to the legacy ConfigManager.

    Returns:
        Dictionary containing the Home Assistant configuration
    """
    # Try YAML config first
    ha_config = config_loader.get_home_assistant_config()

    # If empty or not found, fall back to legacy config
    if not ha_config:
        logger.debug("Using legacy ConfigManager for Home Assistant configuration")
        return config_manager.get_home_assistant_config()

    return ha_config


def get_mcp_servers() -> Dict[str, Any]:
    """
    Get all configured MCP servers.

    Returns:
        List of MCP server configurations from YAML
    """
    return config_loader.get_mcp_servers()


def get_enabled_mcp_servers() -> Dict[str, Any]:
    """
    Get all enabled MCP servers.

    Returns:
        List of enabled MCP server configurations from YAML
    """
    return config_loader.get_enabled_mcp_servers()


def get_mcp_server(server_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific MCP server by ID.

    Args:
        server_id: The ID of the MCP server

    Returns:
        Dictionary containing the MCP server configuration, or None if not found
    """
    return config_loader.get_mcp_server(server_id)


def is_mcp_server_enabled(server_id: str) -> bool:
    """
    Check if a specific MCP server is enabled.

    Args:
        server_id: The ID of the MCP server

    Returns:
        Boolean indicating if the server is enabled
    """
    return config_loader.is_mcp_server_enabled(server_id)


def get_instruction(name: str) -> str:
    """
    Get an instruction prompt by name.

    Delegates to the legacy ConfigManager to maintain compatibility.

    Args:
        name: Name of the instruction prompt to load

    Returns:
        The instruction prompt text
    """
    return config_manager.get_instruction(name)


def get_schema_config(schema_name: str) -> Dict[str, Any]:
    """
    Get JSON schema configuration for structured data interfaces.

    Delegates to the legacy ConfigManager to maintain compatibility.

    Args:
        schema_name: Name of the schema to load

    Returns:
        Dictionary representation of the JSON schema
    """
    return config_manager.get_schema_config(schema_name)


def get_claude_templates() -> Dict[str, str]:
    """
    Get all Claude templates from the configuration.

    Returns:
        Dictionary of template names to template strings
    """
    return config_loader.get_config().get("claude_templates", {})
