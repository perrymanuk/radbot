#!/usr/bin/env python3
"""
Test script for MCP-Proxy integration.

This script tests connectivity and tool discovery for each MCP-Proxy endpoint.
"""

import logging
import sys
import os
import json
from typing import Dict, Any, List, Optional

# Add parent directory to path to allow importing radbot modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from radbot.tools.mcp.mcp_client_factory import MCPClientFactory, MCPClientError
from radbot.config.config_loader import config_loader

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Proxy endpoint IDs to test
PROXY_ENDPOINTS = [
    "firecrawl-proxy",
    "context7-proxy",
    "webresearch-proxy",
    "nomad-proxy"  # May be optional depending on configuration
]

def test_endpoint(endpoint_id: str) -> Dict[str, Any]:
    """
    Test connection to a proxy endpoint and discover available tools.
    
    Args:
        endpoint_id: The ID of the proxy endpoint to test
        
    Returns:
        Dict with test results
    """
    try:
        logger.info(f"Testing connection to {endpoint_id}...")
        
        # Get client for the endpoint
        client = MCPClientFactory.get_client(endpoint_id)
        
        if not client:
            return {
                "endpoint": endpoint_id,
                "status": "failed",
                "error": "Failed to create client",
                "message": "Client creation returned None"
            }
            
        # Check if client is initialized
        if not getattr(client, "initialized", False):
            # Try to initialize
            if hasattr(client, "initialize") and callable(client.initialize):
                success = client.initialize()
                if not success:
                    return {
                        "endpoint": endpoint_id,
                        "status": "failed",
                        "error": "Initialization failed",
                        "message": "Client initialization returned False"
                    }
            else:
                return {
                    "endpoint": endpoint_id,
                    "status": "failed",
                    "error": "No initialization method",
                    "message": "Client has no initialize method"
                }
                
        # Try to get available tools
        tools = []
        if hasattr(client, "get_tools") and callable(client.get_tools):
            tools = client.get_tools()
        elif hasattr(client, "tools"):
            tools = client.tools
        
        # Get tool names
        tool_names = []
        for tool in tools:
            if hasattr(tool, "name"):
                tool_names.append(tool.name)
            elif hasattr(tool, "__name__"):
                tool_names.append(tool.__name__)
            else:
                tool_names.append(str(tool))
                
        return {
            "endpoint": endpoint_id,
            "status": "success",
            "tools_count": len(tools),
            "tools": tool_names,
            "message": f"Successfully connected to {endpoint_id}"
        }
        
    except MCPClientError as e:
        return {
            "endpoint": endpoint_id,
            "status": "failed",
            "error": "MCPClientError",
            "message": str(e)
        }
    except Exception as e:
        return {
            "endpoint": endpoint_id,
            "status": "failed",
            "error": type(e).__name__,
            "message": str(e)
        }

def main():
    """Main test function."""
    print("\n🔌 Testing MCP-Proxy Integration\n")
    
    # Check if config is loaded
    try:
        # Get enabled MCP servers
        mcp_servers = config_loader.get_enabled_mcp_servers()
        if not mcp_servers:
            print("❌ No enabled MCP servers found in configuration!")
            print("Please check your config.yaml file and ensure the MCP proxy servers are configured.")
            return 1
            
        print(f"📊 Found {len(mcp_servers)} enabled MCP servers in config\n")
        
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        print("Please check your config.yaml file and ensure it's valid.")
        return 1
    
    # Test each configured proxy endpoint
    results = []
    for endpoint_id in PROXY_ENDPOINTS:
        result = test_endpoint(endpoint_id)
        results.append(result)
        
        # Print result
        if result["status"] == "success":
            print(f"✅ {endpoint_id}: Successfully connected")
            print(f"   Found {result['tools_count']} tools: {', '.join(result['tools'][:5])}" + 
                  (f"... and {len(result['tools']) - 5} more" if len(result['tools']) > 5 else ""))
        else:
            print(f"❌ {endpoint_id}: Failed - {result['message']}")
        print()
        
    # Summary
    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"\n📋 Summary: {success_count}/{len(results)} endpoints connected successfully")
    
    if success_count == 0:
        print("\n❌ All connections failed. Please check your configuration and network connectivity.")
        return 1
    elif success_count < len(results):
        print("\n⚠️  Some connections failed. Check the logs above for details.")
        return 0
    else:
        print("\n✅ All connections successful! MCP-Proxy integration is working properly.")
        return 0

if __name__ == "__main__":
    sys.exit(main())