"""
MCP Home Assistant integration tools.

This module provides utilities for connecting to Home Assistant via MCP Server
and creating the necessary tools for agent interaction.
"""

import os
import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from contextlib import AsyncExitStack

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseServerParams

from radbot.config.config_loader import config_loader

logger = logging.getLogger(__name__)

async def _create_home_assistant_toolset_async() -> Tuple[List[Any], Optional[AsyncExitStack]]:
    """
    Async function to create an McpToolset for Home Assistant's MCP Server.

    Returns:
        Tuple[List[MCPTool], AsyncExitStack]: The list of tools and exit stack, or ([], None) if configuration fails
    """
    try:
        # Get Home Assistant configuration from config.yaml
        ha_config = config_loader.get_home_assistant_config()
        
        # Get connection parameters from configuration or fall back to environment variables
        ha_mcp_url = ha_config.get("mcp_sse_url")
        if not ha_mcp_url:
            # Fall back to environment variable
            ha_mcp_url = os.getenv("HA_MCP_SSE_URL")
        
        ha_auth_token = ha_config.get("token")
        if not ha_auth_token:
            # Fall back to environment variable
            ha_auth_token = os.getenv("HA_AUTH_TOKEN")
        
        if not ha_mcp_url:
            logger.error("Home Assistant MCP URL not found. "
                        "Please set mcp_sse_url in the Home Assistant configuration section of config.yaml "
                        "or set HA_MCP_SSE_URL environment variable.")
            return [], None
            
        if not ha_auth_token:
            logger.error("Home Assistant authentication token not found. "
                        "Please set token in the Home Assistant configuration section of config.yaml "
                        "or set HA_AUTH_TOKEN environment variable.")
            return [], None
            
        # Normalize URL path - ensure it has the correct format
        # Home Assistant MCP Server typically uses /mcp_server/sse or sometimes /api/mcp_server/sse
        if not ha_mcp_url.endswith("/mcp_server/sse") and not ha_mcp_url.endswith("/api/mcp_server/sse"):
            original_url = ha_mcp_url
            
            # If URL ends with a trailing slash, remove it
            if ha_mcp_url.endswith("/"):
                ha_mcp_url = ha_mcp_url[:-1]
                
            # If URL doesn't contain /mcp_server/sse path, add it
            if "/mcp_server/sse" not in ha_mcp_url:
                ha_mcp_url = f"{ha_mcp_url}/mcp_server/sse"
                
            logger.info(f"Normalized Home Assistant MCP URL from {original_url} to {ha_mcp_url}")
            
        logger.info(f"Using Home Assistant MCP URL: {ha_mcp_url}")
        
        # Configure the SSE parameters for Home Assistant MCP server
        ha_mcp_params = SseServerParams(
            url=ha_mcp_url,
            headers={
                "Authorization": f"Bearer {ha_auth_token}"
            }
        )
        
        # Create an AsyncExitStack for resource management
        exit_stack = AsyncExitStack()
        
        try:
            tools, _ = await McpToolset.from_server(
                connection_params=ha_mcp_params,
                async_exit_stack=exit_stack
            )
            
            logger.info(f"Successfully loaded {len(tools)} Home Assistant MCP tools")
            return tools, exit_stack
        except Exception as e:
            logger.error(f"Failed to create McpToolset: {str(e)}")
            # Try to clean up resources if exit_stack was used
            try:
                await exit_stack.aclose()
            except:
                pass
            return [], None
        
    except ImportError as ie:
        logger.error(f"Failed to import required modules: {str(ie)}")
        logger.error("Make sure google-adk>=1.22.0 is installed")
        return [], None
    except Exception as e:
        logger.error(f"Failed to create Home Assistant MCP toolset: {str(e)}")
        return [], None

def create_home_assistant_toolset() -> List[Any]:
    """
    Create Home Assistant MCP tools using McpToolset.

    Uses environment variables for configuration (HA_MCP_SSE_URL, HA_AUTH_TOKEN).

    Returns:
        List[MCPTool]: List of Home Assistant MCP tools, or empty list if configuration fails
    """
    exit_stack = None
    try:
        # Need to check if we're already in an event loop
        try:
            existing_loop = asyncio.get_event_loop()
            if existing_loop.is_running():
                logger.warning("Cannot create Home Assistant toolset: Event loop is already running")
                logger.warning("This likely means you're using this in an async context")
                logger.warning("Try using 'await _create_home_assistant_toolset_async()' instead")
                return []
        except RuntimeError:
            # No event loop exists, create a new one
            pass
            
        # Run the async function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tools, exit_stack = loop.run_until_complete(_create_home_assistant_toolset_async())
        
        # Close only the event loop
        loop.close()
        
        return tools
    except Exception as e:
        logger.error(f"Error creating Home Assistant tools: {str(e)}")
        if exit_stack:
            try:
                # We need to close the exit stack if an error occurred
                # Create a new event loop for this
                cleanup_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(cleanup_loop)
                cleanup_loop.run_until_complete(exit_stack.aclose())
                cleanup_loop.close()
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup: {str(cleanup_error)}")
        return []