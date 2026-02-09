#!/usr/bin/env python3
"""
Dynamic MCP Tools Loader

This module automatically loads and registers tools from all enabled MCP servers
defined in the config.yaml file. It eliminates the need to manually update the
agent initialization code when adding new MCP servers.
"""

import logging
import asyncio
import threading
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from radbot.config.config_loader import config_loader
from radbot.tools.mcp.mcp_client_factory import MCPClientFactory, MCPClientError

logger = logging.getLogger(__name__)

# Tools that should never be loaded from MCP servers into the Gemini agent.
# These are Claude Code internal tools that are exposed by `claude mcp serve`
# but are completely unusable by Google Gemini models.
_MCP_TOOL_BLOCKLIST = {
    "Task", "TaskOutput", "Bash", "Glob", "Grep", "Read", "Edit", "Write",
    "NotebookEdit", "WebFetch", "TodoWrite", "WebSearch", "TaskStop",
    "AskUserQuestion", "Skill", "EnterPlanMode", "ExitPlanMode", "ToolSearch",
}


def load_dynamic_mcp_tools() -> List[Any]:
    """
    Dynamically load tools from all enabled MCP servers defined in config.yaml.
    
    This function:
    1. Reads all MCP servers from config
    2. Gets clients for enabled servers
    3. Gets all tools from each client
    4. Returns a combined list of all tools
    
    Returns:
        List of all MCP tools
    """
    all_tools = []
    
    try:
        # Get all enabled MCP servers from config
        enabled_servers = config_loader.get_enabled_mcp_servers()
        if not enabled_servers:
            logger.warning("No enabled MCP servers found in config")
            return []
            
        logger.info(f"Found {len(enabled_servers)} enabled MCP servers in config")
        
        # Track tool counts for logging
        server_tool_counts = {}
        
        # Process each server
        for server in enabled_servers:
            server_id = server.get("id")
            server_name = server.get("name", server_id)
            
            if not server_id:
                logger.warning(f"Skipping MCP server with no ID: {server}")
                continue
                
            try:
                # Try to get the client for this server
                client = MCPClientFactory.get_client(server_id)
                if not client:
                    logger.warning(f"Failed to get client for MCP server {server_id}")
                    continue
                    
                # Check if this is an async client that needs initialization
                if hasattr(client, "check_initialization") and callable(client.check_initialization):
                    # This is an async client that needs special handling
                    try:
                        # Use a background thread to run the async operation
                        init_result = {"success": False, "error": None}

                        def init_async_client():
                            nonlocal init_result
                            try:
                                # This thread will have its own event loop
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    # Run the initialization
                                    success = loop.run_until_complete(client.check_initialization())
                                    init_result["success"] = success
                                finally:
                                    loop.close()
                            except Exception as e:
                                init_result["error"] = str(e)

                        # Start a separate thread for async initialization
                        init_thread = threading.Thread(target=init_async_client)
                        init_thread.start()
                        init_thread.join()  # Wait for it to complete

                        # Check the result
                        if not init_result["success"]:
                            error_msg = init_result.get("error", "Unknown error")
                            logger.warning(f"Failed to initialize async client for MCP server {server_id}: {error_msg}")
                            continue
                    except Exception as e:
                        logger.error(f"Error initializing async client for MCP server {server_id}: {e}")
                        continue

                # Get tools from this client
                if hasattr(client, "get_tools") and callable(client.get_tools):
                    tools = client.get_tools()
                elif hasattr(client, "tools"):
                    tools = client.tools
                else:
                    # No tools found
                    logger.warning(f"No tools found for MCP server {server_id}")
                    continue
                    
                # Filter out blocklisted tools and add to our list
                if tools:
                    filtered_tools = []
                    blocked_names = []
                    for tool in tools:
                        tool_name = getattr(tool, 'name', None) or getattr(tool, '__name__', str(tool))
                        if tool_name in _MCP_TOOL_BLOCKLIST:
                            blocked_names.append(tool_name)
                        else:
                            filtered_tools.append(tool)

                    if blocked_names:
                        logger.warning(
                            f"Filtered {len(blocked_names)} blocklisted tools from "
                            f"MCP server {server_name}: {blocked_names}"
                        )

                    all_tools.extend(filtered_tools)
                    server_tool_counts[server_name] = len(filtered_tools)
                    logger.info(f"Added {len(filtered_tools)} tools from MCP server {server_name}")
                else:
                    logger.warning(f"No tools returned from MCP server {server_id}")
                    
            except MCPClientError as e:
                logger.warning(f"Error getting client for MCP server {server_id}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error processing MCP server {server_id}: {e}")
                
        # Log results
        if server_tool_counts:
            logger.info("Tool counts by server:")
            for server_name, count in server_tool_counts.items():
                logger.info(f"  - {server_name}: {count} tools")
        
        logger.info(f"Total MCP tools loaded: {len(all_tools)}")
        return all_tools
        
    except Exception as e:
        logger.error(f"Error loading dynamic MCP tools: {e}")
        return []
        
def load_specific_mcp_tools(server_id: str) -> List[Any]:
    """
    Load tools from a specific MCP server.
    
    Args:
        server_id: The ID of the MCP server to load tools from
        
    Returns:
        List of tools from the specified server
    """
    try:
        # Try to get the client for this server
        client = MCPClientFactory.get_client(server_id)
        if not client:
            logger.warning(f"Failed to get client for MCP server {server_id}")
            return []
            
        # Check if this is an async client that needs initialization
        if hasattr(client, "check_initialization") and callable(client.check_initialization):
            # This is an async client that needs special handling
            try:
                # Use a background thread to run the async operation
                init_result = {"success": False, "error": None}

                def init_async_client():
                    nonlocal init_result
                    try:
                        # This thread will have its own event loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            # Run the initialization
                            success = loop.run_until_complete(client.check_initialization())
                            init_result["success"] = success
                        finally:
                            loop.close()
                    except Exception as e:
                        init_result["error"] = str(e)

                # Start a separate thread for async initialization
                init_thread = threading.Thread(target=init_async_client)
                init_thread.start()
                init_thread.join()  # Wait for it to complete

                # Check the result
                if not init_result["success"]:
                    error_msg = init_result.get("error", "Unknown error")
                    logger.warning(f"Failed to initialize async client for MCP server {server_id}: {error_msg}")
                    return []
            except Exception as e:
                logger.error(f"Error initializing async client for MCP server {server_id}: {e}")
                return []

        # Get tools from this client
        if hasattr(client, "get_tools") and callable(client.get_tools):
            tools = client.get_tools()
        elif hasattr(client, "tools"):
            tools = client.tools
        else:
            # No tools found
            logger.warning(f"No tools found for MCP server {server_id}")
            return []
            
        # Return the tools
        if tools:
            logger.info(f"Loaded {len(tools)} tools from MCP server {server_id}")
            return tools
        else:
            logger.warning(f"No tools returned from MCP server {server_id}")
            return []
            
    except MCPClientError as e:
        logger.warning(f"Error getting client for MCP server {server_id}: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error processing MCP server {server_id}: {e}")
        return []
        
def main():
    """Command line entry point for testing."""
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    print("Dynamic MCP Tools Loader Test")
    
    # Load all tools
    tools = load_dynamic_mcp_tools()
    
    print(f"\nLoaded {len(tools)} total tools from all MCP servers")
    
    # Print tool names
    if tools:
        print("\nTool names:")
        for tool in tools:
            if hasattr(tool, "name"):
                print(f"  - {tool.name}")
            elif hasattr(tool, "__name__"):
                print(f"  - {tool.__name__}")
            else:
                print(f"  - {str(tool)}")
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())