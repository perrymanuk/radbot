#!/usr/bin/env python
"""
Test script for validating the new MCP client implementation.

This script tests the new MCP client with MCP servers to validate
the implementation.

Usage:
    python test_new_mcp_client.py --server-id <server_id> [--debug]
"""

import os
import sys
import logging
import argparse
import json
from typing import Dict, Any, List, Optional

# Add parent directory to module path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("mcp_client_test")

def test_client(server_id: str, debug: bool = False) -> bool:
    """
    Test the new MCP client implementation with the specified server.
    
    Args:
        server_id: The ID of the MCP server to test
        debug: Enable debug logging
        
    Returns:
        True if the test is successful, False otherwise
    """
    if debug:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("radbot.tools.mcp").setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
        logging.getLogger("radbot.tools.mcp").setLevel(logging.INFO)
    
    try:
        # Import the necessary modules
        from radbot.config.config_loader import config_loader
        from radbot.tools.mcp.client import MCPSSEClient
        
        # Get server configuration
        server_config = config_loader.get_mcp_server(server_id)
        if not server_config:
            logger.error(f"Server '{server_id}' not found in configuration")
            return False
        
        # Get server details
        url = server_config.get("url")
        message_endpoint = server_config.get("message_endpoint")
        auth_token = server_config.get("auth_token")
        
        logger.info(f"Testing MCP client with server {server_id} at {url}")
        
        # Create client
        client = MCPSSEClient(
            url=url,
            message_endpoint=message_endpoint,
            auth_token=auth_token
        )
        
        # Initialize the client
        logger.info("Initializing client...")
        success = client.initialize()
        
        if not success:
            logger.error("Failed to initialize client")
            return False
        
        logger.info("Client initialized successfully")
        
        # Get tools
        tools = client.get_tools()
        
        if not tools:
            logger.warning("No tools found")
        else:
            logger.info(f"Found {len(tools)} tools")
            
            # List tool names
            tool_names = []
            if tools:
                for tool in tools:
                    if hasattr(tool, "name"):
                        tool_names.append(tool.name)
                    else:
                        tool_names.append(str(tool))
                
                logger.info(f"Tool names: {', '.join(tool_names)}")
            
            # Even if no tools found via client.get_tools(), try to discover them
            if not tool_names:
                discovered_tools = client.discover_tools()
                if discovered_tools:
                    tool_names = discovered_tools
                    logger.info(f"Discovered tool names: {', '.join(tool_names)}")
        
        # Discover tools explicitly
        logger.info("Testing discover_tools method")
        discovered_tools = client.discover_tools()
        if discovered_tools:
            logger.info(f"Discovered tools: {discovered_tools}")
        
        # Test completed successfully
        logger.info("MCP client test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error testing MCP client: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Test the new MCP client implementation")
    parser.add_argument("--server-id", required=True, help="ID of the MCP server to test")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    
    success = test_client(args.server_id, args.debug)
    
    if success:
        print("Test completed successfully")
        return 0
    else:
        print("Test failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())