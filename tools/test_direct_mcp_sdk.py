#!/usr/bin/env python
"""
Test script for directly using the MCP Python SDK.

This script tests direct connections to MCP servers using the official
MCP Python SDK to validate compatibility and behavior.

Usage:
    python test_direct_mcp_sdk.py <sse_url> [--auth-token TOKEN] [--debug]

Example:
    python test_direct_mcp_sdk.py https://example.com/mcp/sse
"""

import os
import sys
import logging
import argparse
import json
import asyncio
from typing import Dict, Any, List, Optional, Union, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('mcp_sdk_test')

async def run_mcp_test(sse_url: str, auth_token: Optional[str] = None, debug: bool = False):
    """
    Test MCP connection and functionality using the MCP Python SDK.
    
    Args:
        sse_url: URL of the SSE endpoint
        auth_token: Optional authentication token
        debug: Enable debug logging
    """
    try:
        # Configure logging
        if debug:
            logger.setLevel(logging.DEBUG)
            logging.getLogger('mcp').setLevel(logging.DEBUG)
            logging.getLogger('httpx').setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
            
        # Import MCP SDK (here to avoid errors if not installed)
        try:
            from mcp import ClientSession
            from mcp.client.sse import sse_client
            from mcp.types import Tool
            import httpx
        except ImportError:
            logger.error("MCP Python SDK not installed. Please install with: pip install mcp httpx")
            return False
            
        logger.info(f"Connecting to MCP server at: {sse_url}")
        
        # Set up headers
        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Content-Type": "application/json"
        }
        
        # Add authentication if provided
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
            logger.info("Added authentication token")
            
        # Create the SSE client context
        try:
            # Connect to the SSE endpoint
            logger.info("Establishing SSE connection...")
            async with sse_client(url=sse_url, headers=headers) as streams:
                read_stream, write_stream = streams
                
                # Create the client session
                logger.info("Creating client session...")
                async with ClientSession(read_stream, write_stream) as session:
                    # Initialize the session
                    logger.info("Initializing session...")
                    await session.initialize()
                    logger.info("Session initialized successfully")
                    
                    # Get available tools
                    logger.info("Listing available tools...")
                    tools = await session.list_tools()
                    
                    # Process the tool list based on different return formats
                    tool_names = []
                    
                    if isinstance(tools, list):
                        logger.info(f"Received tools in list format: {len(tools)} tools found")
                        
                        for tool in tools:
                            if hasattr(tool, 'name'):
                                tool_names.append(tool.name)
                                logger.info(f"Tool: {tool.name} - {getattr(tool, 'description', 'No description')}")
                            elif isinstance(tool, tuple) and len(tool) > 0:
                                if isinstance(tool[0], str):
                                    tool_names.append(tool[0])
                                    logger.info(f"Tool (tuple): {tool[0]} - {tool[1] if len(tool) > 1 else 'No description'}")
                                else:
                                    logger.info(f"Unknown tuple tool format: {type(tool[0])}")
                            elif isinstance(tool, dict) and 'name' in tool:
                                tool_names.append(tool['name'])
                                logger.info(f"Tool (dict): {tool['name']} - {tool.get('description', 'No description')}")
                            else:
                                logger.info(f"Unknown tool format: {type(tool)}")
                    elif isinstance(tools, tuple):
                        logger.info(f"Received tools in tuple format")
                        
                        # Handle the common ('meta', None), ('nextCursor', None), ('tools', [...]) format
                        for item in tools:
                            if isinstance(item, tuple) and len(item) >= 2:
                                key, value = item[0], item[1]
                                logger.info(f"Tuple item: ({key}, {type(value)})")
                                
                                if key == 'tools' and isinstance(value, list):
                                    for tool in value:
                                        if hasattr(tool, 'name'):
                                            tool_names.append(tool.name)
                                            logger.info(f"Tool: {tool.name} - {getattr(tool, 'description', 'No description')}")
                    else:
                        logger.info(f"Unknown tools response format: {type(tools)}")
                    
                    if tool_names:
                        logger.info(f"Found {len(tool_names)} tools: {', '.join(tool_names)}")
                    else:
                        logger.warning("No tools found")
                        
                    # Try to call a tool if available
                    if tool_names:
                        # Choose a tool to test
                        # Prefer common MCP tools for testing
                        test_candidates = ['md', 'crawl', 'html', 'HassTurnOn', 'screenshot', 'search']
                        test_tool = None
                        
                        for candidate in test_candidates:
                            if candidate in tool_names:
                                test_tool = candidate
                                break
                                
                        if not test_tool:
                            # If no preferred tool is found, use the first one
                            test_tool = tool_names[0]
                            
                        # Set up test arguments based on the tool
                        test_args = {}
                        if test_tool in ['md', 'html', 'screenshot', 'crawl']:
                            test_args = {"url": "https://example.com"}
                        elif test_tool == 'search':
                            test_args = {"query": "example domain"}
                        elif test_tool == 'HassTurnOn':
                            test_args = {"name": "Office Light"}
                            
                        logger.info(f"Testing tool '{test_tool}' with args: {test_args}")
                        
                        try:
                            result = await session.call_tool(test_tool, test_args)
                            logger.info(f"Tool call succeeded: {result}")
                        except Exception as e:
                            logger.error(f"Tool call failed: {str(e)}")
                            return False
                            
                    # Try to list resources if available
                    try:
                        logger.info("Listing available resources...")
                        resources = await session.list_resources()
                        if resources:
                            logger.info(f"Found {len(resources)} resources: {resources}")
                        else:
                            logger.info("No resources found")
                    except Exception as e:
                        logger.info(f"Resource listing not supported: {str(e)}")
                        
                    # Try to list prompts if available
                    try:
                        logger.info("Listing available prompts...")
                        prompts = await session.list_prompts()
                        if prompts:
                            prompt_names = [p.name if hasattr(p, 'name') else str(p) for p in prompts]
                            logger.info(f"Found {len(prompts)} prompts: {', '.join(prompt_names)}")
                        else:
                            logger.info("No prompts found")
                    except Exception as e:
                        logger.info(f"Prompt listing not supported: {str(e)}")
                        
                    logger.info("Test completed successfully")
                    return True
                        
        except Exception as e:
            logger.error(f"Error connecting to MCP server: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        return False

async def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description='Test direct MCP Python SDK usage')
    parser.add_argument('sse_url', help='URL of the SSE endpoint')
    parser.add_argument('--auth-token', help='Authentication token')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    
    success = await run_mcp_test(args.sse_url, args.auth_token, args.debug)
    return 0 if success else 1

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