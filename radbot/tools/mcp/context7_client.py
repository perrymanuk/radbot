#!/usr/bin/env python3
"""
Context7 MCP Integration

This module integrates Context7's MCP server capabilities with the Radbot framework.
It allows retrieving documentation for various libraries and frameworks through
Context7's MCP server implementation.
"""

import json
import logging
import os
import subprocess
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

import google.adk.tools as adk_tools
from google.adk.tools import FunctionTool

from radbot.config.config_loader import config_loader
from radbot.tools.mcp.mcp_client_factory import MCPClientError, MCPClientFactory

logger = logging.getLogger(__name__)


def get_context7_config() -> Dict[str, Any]:
    """
    Get configuration for the Context7 MCP server from config.yaml.

    Returns:
        Dict with configuration values, or empty dict if not configured
    """
    try:
        # Get config from MCP servers configuration
        mcp_servers = config_loader.get_enabled_mcp_servers()
        for server in mcp_servers:
            if server.get("id") == "context7":
                return server

        # Not found in enabled servers
        logger.warning("Context7 MCP server not found in enabled MCP servers")
        return {}

    except Exception as e:
        logger.error(f"Error getting Context7 config: {e}")
        return {}


def resolve_library_id(library_name: str) -> Dict[str, Any]:
    """
    Resolve a library name to a Context7-compatible library ID.

    Args:
        library_name: The name of the library to resolve

    Returns:
        Dict containing resolution results or error information
    """
    try:
        # Get the Context7 MCP client
        client = MCPClientFactory.get_client("context7")

        # Check if client was created successfully
        if not client:
            raise MCPClientError("Failed to get Context7 MCP client")

        # Prepare arguments for the resolve tool
        tool_name = "resolve-library-id"
        args = {"libraryName": library_name}

        # Call the tool
        logger.info(f"Resolving library ID for: {library_name}")
        result = client.call_tool(tool_name, args)

        # Process the result
        if isinstance(result, dict):
            return {
                "success": True,
                "library_id": result.get("libraryId", ""),
                "matches": result.get("matches", []),
                "message": result.get("message", ""),
            }
        else:
            # Handle unexpected result format
            logger.warning(
                f"Unexpected result format from resolve-library-id tool: {result}"
            )
            return {
                "success": False,
                "error": "Unexpected result format",
                "result": str(result),
            }

    except Exception as e:
        logger.error(f"Error resolving library ID: {e}")
        return {"success": False, "error": str(e)}


def get_library_docs(
    library_id: str, topic: Optional[str] = None, tokens: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get documentation for a library using Context7.

    Args:
        library_id: The Context7-compatible library ID
        topic: Optional topic to focus documentation on
        tokens: Optional maximum number of tokens to retrieve

    Returns:
        Dict containing documentation or error information
    """
    try:
        # Get the Context7 MCP client
        client = MCPClientFactory.get_client("context7")

        # Check if client was created successfully
        if not client:
            raise MCPClientError("Failed to get Context7 MCP client")

        # Prepare arguments for the docs tool
        tool_name = "get-library-docs"
        args = {"context7CompatibleLibraryID": library_id}

        # Add optional parameters if provided
        if topic:
            args["topic"] = topic
        if tokens:
            args["tokens"] = tokens

        # Call the tool
        logger.info(f"Getting documentation for library: {library_id}")
        result = client.call_tool(tool_name, args)

        # Process the result
        if isinstance(result, dict):
            return {
                "success": True,
                "documentation": result.get("documentation", ""),
                "library_id": result.get("libraryId", library_id),
                "message": result.get("message", ""),
            }
        else:
            # Handle unexpected result format
            logger.warning(
                f"Unexpected result format from get-library-docs tool: {result}"
            )
            return {
                "success": False,
                "error": "Unexpected result format",
                "result": str(result),
            }

    except Exception as e:
        logger.error(f"Error getting library documentation: {e}")
        return {"success": False, "error": str(e)}


def create_context7_tools() -> List[FunctionTool]:
    """
    Create a set of tools for interacting with the Context7 MCP server.

    Returns:
        List of FunctionTool instances
    """
    tools = []

    try:
        # Create tool schemas
        resolve_library_schema = {
            "name": "context7_resolve_library",
            "description": "Resolve a library name to a Context7-compatible library ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "library_name": {
                        "type": "string",
                        "description": "The name of the library to resolve",
                    }
                },
                "required": ["library_name"],
            },
        }

        get_docs_schema = {
            "name": "context7_get_docs",
            "description": "Get documentation for a library using Context7",
            "parameters": {
                "type": "object",
                "properties": {
                    "library_id": {
                        "type": "string",
                        "description": "The Context7-compatible library ID",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Optional topic to focus documentation on",
                    },
                    "tokens": {
                        "type": "integer",
                        "description": "Optional maximum number of tokens to retrieve",
                    },
                },
                "required": ["library_id"],
            },
        }

        # Create FunctionTools based on ADK version
        try:
            # Try with function_schema (ADK 0.4.0+)
            try:
                resolve_tool = FunctionTool(
                    function=resolve_library_id, function_schema=resolve_library_schema
                )
                docs_tool = FunctionTool(
                    function=get_library_docs, function_schema=get_docs_schema
                )
                logger.info("Created Context7 MCP tools with function_schema")
            except TypeError:
                # Try with schema (older ADK)
                resolve_tool = FunctionTool(
                    resolve_library_id, schema=resolve_library_schema
                )
                docs_tool = FunctionTool(get_library_docs, schema=get_docs_schema)
                logger.info("Created Context7 MCP tools with schema")
        except Exception as e:
            # Fallback to simple FunctionTool
            logger.warning(f"Error creating tools with schema: {e}, using basic tools")
            resolve_tool = FunctionTool(resolve_library_id)
            docs_tool = FunctionTool(get_library_docs)

        # Add tools to the list
        tools.extend([resolve_tool, docs_tool])
        logger.info(f"Created {len(tools)} Context7 MCP tools")

        return tools

    except Exception as e:
        logger.error(f"Error creating Context7 MCP tools: {e}")
        return []


def test_context7_connection() -> Dict[str, Any]:
    """
    Test the connection to the Context7 MCP server.

    Returns:
        Dict with test results
    """
    try:
        # Try to resolve a commonly used library as a connectivity test
        test_result = resolve_library_id("react")

        if test_result.get("success", False):
            return {
                "success": True,
                "status": "connected",
                "library_id": test_result.get("library_id", ""),
                "message": "Successfully connected to Context7 MCP server",
            }
        else:
            return {
                "success": False,
                "status": "error",
                "error": test_result.get("error", "Unknown error"),
                "message": "Failed to resolve test library",
            }

    except Exception as e:
        logger.error(f"Error testing Context7 connection: {e}")
        return {
            "success": False,
            "status": "error",
            "error": str(e),
            "message": "Error testing Context7 connection",
        }


def main():
    """Command line entry point for testing."""
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    print("Context7 MCP Integration Test")

    # Test connection
    print("\nTesting connection to Context7 MCP server...")
    connection_result = test_context7_connection()

    if connection_result.get("success", False):
        print(f"✅ Connection successful!")
        print(f"Library ID: {connection_result.get('library_id', '')}")
    else:
        print(
            f"❌ Connection failed: {connection_result.get('message', 'Unknown error')}"
        )
        print(f"Error: {connection_result.get('error', '')}")
        return 1

    # Get tools
    print("\nCreating tools...")
    tools = create_context7_tools()
    print(f"Created {len(tools)} tools:")
    for tool in tools:
        print(f"  - {getattr(tool, 'name', str(tool))}")

    # Test resolve library
    print("\nTesting library resolution...")
    resolve_result = resolve_library_id("python")
    if resolve_result.get("success", False):
        print(f"✅ Library resolution successful!")
        print(f"Library ID: {resolve_result.get('library_id', '')}")

        # Test get docs
        print("\nTesting documentation retrieval...")
        docs_result = get_library_docs(resolve_result.get("library_id", ""))
        if docs_result.get("success", False):
            print(f"✅ Documentation retrieval successful!")
            print(
                f"Documentation snippet: {docs_result.get('documentation', '')[:200]}..."
            )
        else:
            print(
                f"❌ Documentation retrieval failed: {docs_result.get('error', 'Unknown error')}"
            )
    else:
        print(
            f"❌ Library resolution failed: {resolve_result.get('error', 'Unknown error')}"
        )

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
