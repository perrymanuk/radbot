#!/usr/bin/env python
"""
Test script for validating the standard MCP client implementation.

This script tests the MCP client with MCP servers to validate proper
implementation and compatibility.

Usage:
    python test_mcp_standard_client.py [--server-id SERVER_ID] [--debug]
"""

import os
import sys
import logging
import argparse
import json
import asyncio
from typing import Dict, Any, List, Optional

# Add parent directory to module path to allow importing radbot modules
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Import radbot modules
from radbot.tools.mcp.mcp_client_factory import MCPClientFactory
from radbot.tools.mcp.mcp_core import create_mcp_tools
from radbot.config.config_loader import config_loader

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('mcp_test')

def configure_logging(debug: bool = False):
    """Configure logging level."""
    if debug:
        logger.setLevel(logging.DEBUG)
        logging.getLogger('radbot.tools.mcp').setLevel(logging.DEBUG)
        logging.getLogger('httpx').setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
        logging.getLogger('radbot.tools.mcp').setLevel(logging.INFO)
        logging.getLogger('httpx').setLevel(logging.WARNING)

def get_mcp_servers() -> List[Dict[str, Any]]:
    """Get a list of all enabled MCP servers from configuration."""
    return config_loader.get_enabled_mcp_servers()

async def test_server(server_id: str) -> bool:
    """Test MCP connection and tool discovery for a server."""
    try:
        logger.info(f"Testing MCP server: {server_id}")
        
        # Get server configuration
        server_config = config_loader.get_mcp_server(server_id)
        if not server_config:
            logger.error(f"Server {server_id} not found in configuration")
            return False
            
        logger.info(f"Server configuration: {json.dumps(server_config, indent=2)}")
            
        # Create client
        try:
            client = MCPClientFactory.get_client(server_id)
            logger.info(f"Created client for {server_id}")
        except Exception as e:
            logger.error(f"Failed to create client for {server_id}: {e}")
            return False

        # Initialize client if needed
        if hasattr(client, 'initialize') and callable(client.initialize):
            try:
                result = client.initialize()
                logger.info(f"Initialized client for {server_id}: {result}")
            except Exception as e:
                logger.error(f"Failed to initialize client for {server_id}: {e}")
                return False

        # Get tools
        if hasattr(client, 'tools') and client.tools:
            tools = client.tools
            logger.info(f"Found {len(tools)} tools directly from client.tools attribute")
        elif hasattr(client, 'get_tools') and callable(client.get_tools):
            tools = client.get_tools()
            logger.info(f"Found {len(tools)} tools from get_tools() method")
        else:
            logger.warning(f"No tools attribute or get_tools method found for {server_id}")
            tools = []
            
        # Show tool names
        tool_names = []
        for tool in tools:
            if hasattr(tool, 'name'):
                tool_names.append(tool.name)
        
        if tool_names:
            logger.info(f"Tools for {server_id}: {', '.join(tool_names)}")
        else:
            logger.warning(f"No tools found for {server_id}")
            
        # Test tool discovery
        if hasattr(client, 'discover_tools') and callable(client.discover_tools):
            try:
                discovered_tools = client.discover_tools()
                if discovered_tools:
                    logger.info(f"Successfully discovered {len(discovered_tools)} tools")
                    
                    # Show discovered tool names
                    discovered_names = [t for t in discovered_tools]
                    logger.info(f"Discovered tool names: {', '.join(discovered_names)}")
                else:
                    logger.warning("No tools discovered by discover_tools()")
            except Exception as e:
                logger.error(f"Error discovering tools: {e}")
                
        # If we get here without errors, return success
        return True
                
    except Exception as e:
        logger.error(f"Error testing server {server_id}: {e}")
        return False

async def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Test MCP standard client implementation')
    parser.add_argument('--server-id', help='Test a specific server by ID')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    
    # Configure logging
    configure_logging(args.debug)
    
    if args.server_id:
        # Test a specific server
        success = await test_server(args.server_id)
        if success:
            logger.info(f"Test successful for server {args.server_id}")
            return 0
        else:
            logger.error(f"Test failed for server {args.server_id}")
            return 1
    else:
        # Test all enabled servers
        servers = get_mcp_servers()
        if not servers:
            logger.error("No enabled MCP servers found in configuration")
            return 1
        
        logger.info(f"Found {len(servers)} enabled MCP servers")
        
        # Test each server
        success_count = 0
        failure_count = 0
        
        for server in servers:
            server_id = server.get('id')
            if server_id:
                result = await test_server(server_id)
                if result:
                    logger.info(f"Server {server_id} test passed")
                    success_count += 1
                else:
                    logger.error(f"Server {server_id} test failed")
                    failure_count += 1
        
        # Report results
        logger.info(f"Test results: {success_count} passed, {failure_count} failed")
        
        if failure_count > 0:
            return 1
        return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        sys.exit(1)