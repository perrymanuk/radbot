#!/usr/bin/env python3
"""
Claude CLI MCP Integration

This module integrates Claude CLI's MCP server capabilities with the Radbot framework.
It allows executing shell commands and other operations through Claude CLI's powerful
capabilities exposed via the Model Context Protocol.
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


def get_claude_cli_config() -> Dict[str, Any]:
    """
    Get configuration for the Claude CLI MCP server from config.yaml.

    Returns:
        Dict with configuration values, or empty dict if not configured
    """
    try:
        # Get config from MCP servers configuration
        mcp_servers = config_loader.get_enabled_mcp_servers()
        for server in mcp_servers:
            if server.get("id") == "claude-cli":
                return server

        # Not found in enabled servers
        logger.warning("Claude CLI MCP server not found in enabled MCP servers")
        return {}

    except Exception as e:
        logger.error(f"Error getting Claude CLI config: {e}")
        return {}


def execute_command_via_claude(
    command: str, working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a shell command using Claude CLI's MCP server.

    Args:
        command: The shell command to execute
        working_dir: Optional working directory for the command

    Returns:
        Dict containing command output or error information
    """
    try:
        # Get the Claude CLI MCP client
        client = MCPClientFactory.get_client("claude-cli")

        # Check if client was created successfully
        if not client:
            raise MCPClientError("Failed to get Claude CLI MCP client")

        # Prepare arguments for the Bash tool
        tool_name = "Bash"  # Default name in Claude CLI
        args = {"command": command}

        # Add working directory if specified
        if working_dir:
            args["cwd"] = working_dir

        # Call the tool
        logger.info(f"Executing command via Claude CLI: {command}")
        result = client.call_tool(tool_name, args)

        # Process the result
        if isinstance(result, dict):
            # Extract relevant fields
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            exit_code = result.get("exitCode", result.get("exit_code", 0))

            return {
                "success": exit_code == 0,
                "output": stdout,
                "error": stderr,
                "exit_code": exit_code,
            }
        else:
            # Handle unexpected result format
            logger.warning(f"Unexpected result format from Bash tool: {result}")
            return {
                "success": False,
                "error": "Unexpected result format",
                "output": str(result),
                "exit_code": -1,
            }

    except Exception as e:
        logger.error(f"Error executing command via Claude CLI: {e}")
        return {"success": False, "error": str(e), "output": "", "exit_code": -1}


def read_file_via_claude(file_path: str) -> Dict[str, Any]:
    """
    Read a file using Claude CLI's MCP server.

    Args:
        file_path: Path to the file to read

    Returns:
        Dict containing file content or error information
    """
    try:
        # Get the Claude CLI MCP client
        client = MCPClientFactory.get_client("claude-cli")

        # Check if client was created successfully
        if not client:
            raise MCPClientError("Failed to get Claude CLI MCP client")

        # Prepare arguments for the Read tool
        tool_name = "Read"  # Default name in Claude CLI
        args = {"file_path": file_path}

        # Call the tool
        logger.info(f"Reading file via Claude CLI: {file_path}")
        result = client.call_tool(tool_name, args)

        # Process the result
        if isinstance(result, dict):
            # Extract content
            content = result.get("content", "")

            return {"success": True, "content": content}
        else:
            # Handle unexpected result format
            logger.warning(f"Unexpected result format from Read tool: {result}")
            return {
                "success": False,
                "error": "Unexpected result format",
                "content": str(result),
            }

    except Exception as e:
        logger.error(f"Error reading file via Claude CLI: {e}")
        return {"success": False, "error": str(e), "content": ""}


def write_file_via_claude(file_path: str, content: str) -> Dict[str, Any]:
    """
    Write to a file using Claude CLI's MCP server.

    Args:
        file_path: Path to the file to write
        content: Content to write to the file

    Returns:
        Dict containing result information
    """
    try:
        # Get the Claude CLI MCP client
        client = MCPClientFactory.get_client("claude-cli")

        # Check if client was created successfully
        if not client:
            raise MCPClientError("Failed to get Claude CLI MCP client")

        # Prepare arguments for the Write tool
        tool_name = "Write"  # Default name in Claude CLI
        args = {"file_path": file_path, "content": content}

        # Call the tool
        logger.info(f"Writing to file via Claude CLI: {file_path}")
        result = client.call_tool(tool_name, args)

        # Process the result (simple success check)
        return {"success": True if result else False, "result": result}

    except Exception as e:
        logger.error(f"Error writing file via Claude CLI: {e}")
        return {"success": False, "error": str(e)}


def create_claude_cli_tools() -> List[FunctionTool]:
    """
    Create a set of tools for interacting with the Claude CLI MCP server.

    Returns:
        List of FunctionTool instances
    """
    tools = []

    try:
        # Create tool schemas
        execute_command_schema = {
            "name": "claude_execute_command",
            "description": "Execute a shell command using Claude CLI",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Optional working directory for the command",
                    },
                },
                "required": ["command"],
            },
        }

        read_file_schema = {
            "name": "claude_read_file",
            "description": "Read a file using Claude CLI",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    }
                },
                "required": ["file_path"],
            },
        }

        write_file_schema = {
            "name": "claude_write_file",
            "description": "Write to a file using Claude CLI",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["file_path", "content"],
            },
        }

        # Create FunctionTools based on ADK version
        try:
            # Try with function_schema (ADK 0.4.0+)
            try:
                execute_tool = FunctionTool(
                    function=execute_command_via_claude,
                    function_schema=execute_command_schema,
                )
                read_tool = FunctionTool(
                    function=read_file_via_claude, function_schema=read_file_schema
                )
                write_tool = FunctionTool(
                    function=write_file_via_claude, function_schema=write_file_schema
                )
                logger.info("Created Claude CLI MCP tools with function_schema")
            except TypeError:
                # Try with schema (older ADK)
                execute_tool = FunctionTool(
                    execute_command_via_claude, schema=execute_command_schema
                )
                read_tool = FunctionTool(read_file_via_claude, schema=read_file_schema)
                write_tool = FunctionTool(
                    write_file_via_claude, schema=write_file_schema
                )
                logger.info("Created Claude CLI MCP tools with schema")
        except Exception as e:
            # Fallback to simple FunctionTool
            logger.warning(f"Error creating tools with schema: {e}, using basic tools")
            execute_tool = FunctionTool(execute_command_via_claude)
            read_tool = FunctionTool(read_file_via_claude)
            write_tool = FunctionTool(write_file_via_claude)

        # Add tools to the list
        tools.extend([execute_tool, read_tool, write_tool])
        logger.info(f"Created {len(tools)} Claude CLI MCP tools")

        return tools

    except Exception as e:
        logger.error(f"Error creating Claude CLI MCP tools: {e}")
        return []


def test_claude_cli_connection() -> Dict[str, Any]:
    """
    Test the connection to the Claude CLI MCP server.

    Returns:
        Dict with test results
    """
    try:
        # Get the Claude CLI MCP client
        client = MCPClientFactory.get_client("claude-cli")

        # Check if client was created successfully
        if not client:
            return {
                "success": False,
                "status": "client_creation_failed",
                "message": "Failed to create Claude CLI MCP client",
            }

        # Try to execute a simple command
        result = execute_command_via_claude("echo 'Hello from Claude CLI MCP'")

        if result.get("success", False):
            return {
                "success": True,
                "status": "connected",
                "output": result.get("output", "").strip(),
                "message": "Successfully connected to Claude CLI MCP server",
            }
        else:
            return {
                "success": False,
                "status": "command_failed",
                "error": result.get("error", "Unknown error"),
                "message": "Failed to execute test command",
            }

    except Exception as e:
        logger.error(f"Error testing Claude CLI connection: {e}")
        return {
            "success": False,
            "status": "error",
            "error": str(e),
            "message": "Error testing Claude CLI connection",
        }


def main():
    """Command line entry point for testing."""
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    print("Claude CLI MCP Integration Test")

    # Test connection
    print("\nTesting connection to Claude CLI MCP server...")
    connection_result = test_claude_cli_connection()

    if connection_result.get("success", False):
        print(f"✅ Connection successful!")
        print(f"Output: {connection_result.get('output', '')}")
    else:
        print(
            f"❌ Connection failed: {connection_result.get('message', 'Unknown error')}"
        )
        print(f"Error: {connection_result.get('error', '')}")
        return 1

    # Get tools
    print("\nCreating tools...")
    tools = create_claude_cli_tools()
    print(f"Created {len(tools)} tools:")
    for tool in tools:
        print(f"  - {getattr(tool, 'name', str(tool))}")

    # Test execute command
    print("\nTesting command execution...")
    cmd_result = execute_command_via_claude("ls -la")
    if cmd_result.get("success", False):
        print(f"✅ Command execution successful!")
        print(
            f"Output: {cmd_result.get('output', '')[:200]}..."
            if len(cmd_result.get("output", "")) > 200
            else f"Output: {cmd_result.get('output', '')}"
        )
    else:
        print(
            f"❌ Command execution failed: {cmd_result.get('error', 'Unknown error')}"
        )

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
