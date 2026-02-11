#!/usr/bin/env python3
"""
Direct Claude CLI MCP Integration

This module provides a direct, simplified interface to Claude CLI's MCP server capabilities
without relying on the more complex MCP client infrastructure. This can be more reliable
for basic command execution needs.
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Union

import google.adk.tools as adk_tools
from google.adk.tools import FunctionTool

from radbot.config.config_loader import config_loader

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


def execute_command_directly(
    command: str, working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a shell command directly using Claude CLI.

    This bypasses the MCP client factory and directly uses subprocess to
    call Claude CLI with the command.

    Args:
        command: The shell command to execute
        working_dir: Optional working directory for the command

    Returns:
        Dict containing command output or error information
    """
    try:
        # Get Claude CLI config
        config = get_claude_cli_config()

        if not config:
            logger.error("Claude CLI configuration not found")
            return {
                "success": False,
                "error": "Claude CLI configuration not found",
                "output": "",
                "exit_code": -1,
            }

        # Get claude command and arguments - use the mcp command with appropriate options
        claude_command = config.get("command", "claude")
        # Use direct command with --print to get non-interactive output
        claude_args = [
            "--print",
            "--output-format",
            "json",
            f"Execute this command: {command}",
        ]

        # Set working directory
        cwd = working_dir or config.get("working_directory", os.getcwd())

        # Execute the command
        logger.info(f"Executing command directly via Claude CLI: {command}")

        # Run the process
        process = subprocess.Popen(
            [claude_command] + claude_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
        )

        # Get the output
        stdout, stderr = process.communicate(timeout=60)
        exit_code = process.returncode

        # Process the output
        if exit_code == 0:
            try:
                # Parse JSON output
                result = json.loads(stdout)
                return {
                    "success": True,
                    "output": result.get("stdout", ""),
                    "error": result.get("stderr", ""),
                    "exit_code": result.get("exitCode", 0),
                }
            except json.JSONDecodeError:
                # Return raw output if not valid JSON
                return {
                    "success": True,
                    "output": stdout,
                    "error": stderr,
                    "exit_code": exit_code,
                }
        else:
            return {
                "success": False,
                "output": stdout,
                "error": stderr,
                "exit_code": exit_code,
            }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command execution timed out",
            "output": "",
            "exit_code": -1,
        }
    except Exception as e:
        logger.error(f"Error executing command directly via Claude CLI: {e}")
        return {"success": False, "error": str(e), "output": "", "exit_code": -1}


def read_file_directly(file_path: str) -> Dict[str, Any]:
    """
    Read a file directly using Claude CLI.

    Args:
        file_path: Path to the file to read

    Returns:
        Dict containing file content or error information
    """
    try:
        # Get Claude CLI config
        config = get_claude_cli_config()

        if not config:
            logger.error("Claude CLI configuration not found")
            return {
                "success": False,
                "error": "Claude CLI configuration not found",
                "content": "",
            }

        # Use cat command to read the file content
        # This is more reliable than asking Claude to read the file
        command = f"cat {file_path}"

        # Execute the command to read the file
        result = execute_command_directly(command)

        if result.get("success", False):
            return {"success": True, "content": result.get("output", "")}
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "content": "",
            }

    except Exception as e:
        logger.error(f"Error reading file directly via Claude CLI: {e}")
        return {"success": False, "error": str(e), "content": ""}


def write_file_directly(file_path: str, content: str) -> Dict[str, Any]:
    """
    Write to a file directly using Claude CLI.

    Args:
        file_path: Path to the file to write
        content: Content to write to the file

    Returns:
        Dict containing result information
    """
    try:
        # Get Claude CLI config
        config = get_claude_cli_config()

        if not config:
            logger.error("Claude CLI configuration not found")
            return {"success": False, "error": "Claude CLI configuration not found"}

        # Use echo and redirect to write to the file
        # We'll write to a temporary file and then move it to avoid permission issues
        tmp_file = f"/tmp/claude_cli_write_{int(time.time())}.tmp"

        # Escape content to prevent shell injection
        escaped_content = content.replace("'", "'\\''")

        # First command: write to temp file
        write_cmd = f"echo '{escaped_content}' > {tmp_file}"
        write_result = execute_command_directly(write_cmd)

        if not write_result.get("success", False):
            return {
                "success": False,
                "error": f"Failed to write to temporary file: {write_result.get('error', 'Unknown error')}",
            }

        # Second command: move temp file to destination
        move_cmd = f"mv {tmp_file} {file_path}"
        move_result = execute_command_directly(move_cmd)

        if move_result.get("success", False):
            return {
                "success": True,
                "result": f"File successfully written to {file_path}",
            }
        else:
            return {
                "success": False,
                "error": f"Failed to move file to destination: {move_result.get('error', 'Unknown error')}",
            }

    except Exception as e:
        logger.error(f"Error writing file directly via Claude CLI: {e}")
        return {"success": False, "error": str(e)}


def prompt_claude_directly(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Send a prompt directly to Claude CLI.

    Args:
        prompt: The prompt to send to Claude
        system_prompt: Optional system prompt to set context
        temperature: Optional temperature parameter (0.0-1.0)

    Returns:
        Dict containing response or error information
    """
    try:
        # Get Claude CLI config
        config = get_claude_cli_config()

        if not config:
            logger.error("Claude CLI configuration not found")
            return {
                "success": False,
                "error": "Claude CLI configuration not found",
                "response": "",
            }

        # First check which options are supported
        support_check = _check_claude_cli_support()

        # Get claude command and arguments
        claude_command = config.get("command", "claude")
        # Start with basic arguments
        claude_args = ["--print"]

        # Add JSON output format if supported
        use_json_output = support_check.get("json_output", True)
        if use_json_output:
            claude_args.extend(["--output-format", "json"])

        # Add system prompt if provided and supported
        if system_prompt and support_check.get("system_prompt", False):
            claude_args.extend(["--system", system_prompt])

        # Add temperature if provided and supported
        if temperature is not None and support_check.get("temperature", False):
            claude_args.extend(["--temperature", str(temperature)])

        # Add the prompt
        claude_args.append(prompt)

        # Set working directory
        cwd = config.get("working_directory", os.getcwd())

        # Execute the command
        logger.info(f"Sending prompt directly to Claude CLI: {prompt[:50]}...")
        logger.info(f"Using arguments: {claude_args}")

        # Run the process
        process = subprocess.Popen(
            [claude_command] + claude_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
        )

        # Get the output
        stdout, stderr = process.communicate(timeout=60)
        exit_code = process.returncode

        # Process the output
        if exit_code == 0:
            try:
                # Parse JSON output if we requested JSON
                if use_json_output:
                    json_result = json.loads(stdout)

                    # Check if the result field has actual content
                    result_content = json_result.get("result", "")
                    if result_content == "(no content)" or not result_content:
                        # Claude CLI returned empty content, try again without JSON
                        logger.warning(
                            "Claude CLI returned empty content in JSON mode, retrying without JSON"
                        )
                        return prompt_claude_directly_raw(
                            prompt, system_prompt, temperature
                        )

                    return {
                        "success": True,
                        "response": result_content,  # Return just the result field as the response
                        "raw_response": json_result,  # Include the full JSON response
                        "raw_output": stdout,
                    }
                else:
                    # Return raw output
                    return {"success": True, "response": stdout, "raw_output": stdout}
            except json.JSONDecodeError:
                # Return raw output if not valid JSON
                return {"success": True, "response": stdout, "raw_output": stdout}
        else:
            return {"success": False, "error": stderr, "response": ""}

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command execution timed out",
            "response": "",
        }
    except Exception as e:
        logger.error(f"Error sending prompt to Claude CLI: {e}")
        return {"success": False, "error": str(e), "response": ""}


def prompt_claude_directly_raw(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Send a prompt directly to Claude CLI without JSON formatting.
    This is a fallback for when JSON mode returns empty content.

    Args:
        prompt: The prompt to send to Claude
        system_prompt: Optional system prompt to set context
        temperature: Optional temperature parameter (0.0-1.0)

    Returns:
        Dict containing response or error information
    """
    try:
        # Get Claude CLI config
        config = get_claude_cli_config()

        if not config:
            logger.error("Claude CLI configuration not found")
            return {
                "success": False,
                "error": "Claude CLI configuration not found",
                "response": "",
            }

        # Get claude command and arguments - don't use JSON output format
        claude_command = config.get("command", "claude")
        claude_args = ["--print"]

        # Add system prompt if provided and supported
        support_check = _check_claude_cli_support()
        if system_prompt and support_check.get("system_prompt", False):
            claude_args.extend(["--system", system_prompt])

        # Add temperature if provided and supported
        if temperature is not None and support_check.get("temperature", False):
            claude_args.extend(["--temperature", str(temperature)])

        # Add the prompt
        claude_args.append(prompt)

        # Set working directory
        cwd = config.get("working_directory", os.getcwd())

        # Execute the command
        logger.info(
            f"Sending prompt directly to Claude CLI (raw mode): {prompt[:50]}..."
        )
        logger.info(f"Using arguments: {claude_args}")

        # Run the process
        process = subprocess.Popen(
            [claude_command] + claude_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
        )

        # Get the output
        stdout, stderr = process.communicate(timeout=60)
        exit_code = process.returncode

        # Process the output
        if exit_code == 0:
            return {"success": True, "response": stdout, "raw_output": stdout}
        else:
            return {"success": False, "error": stderr, "response": ""}

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Command execution timed out",
            "response": "",
        }
    except Exception as e:
        logger.error(f"Error sending prompt to Claude CLI (raw mode): {e}")
        return {"success": False, "error": str(e), "response": ""}


def _check_claude_cli_support() -> Dict[str, bool]:
    """
    Check which features are supported by the installed Claude CLI.

    Returns:
        Dict with support flags for various features
    """
    support = {
        "json_output": True,  # Assume JSON output is supported by default
        "system_prompt": False,  # Assume system prompt is not supported by default
        "temperature": False,  # Assume temperature is not supported by default
    }

    try:
        # Check Claude CLI help to see if it mentions these features
        process = subprocess.Popen(
            ["claude", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout, stderr = process.communicate(timeout=10)

        # Check for feature support in help output
        help_text = stdout + stderr

        # Check for JSON output support
        if "--output-format" in help_text or "--json" in help_text:
            support["json_output"] = True
        else:
            support["json_output"] = False

        # Check for system prompt support
        if "--system" in help_text:
            support["system_prompt"] = True

        # Check for temperature support
        if "--temperature" in help_text:
            support["temperature"] = True

        logger.info(f"Claude CLI feature support: {support}")
        return support

    except Exception as e:
        logger.warning(f"Error checking Claude CLI support: {e}, using defaults")
        return support


def create_direct_claude_cli_tools() -> List[FunctionTool]:
    """
    Create a set of tools for direct interaction with Claude CLI.

    Returns:
        List of FunctionTool instances
    """
    tools = []

    try:
        # Create tool schemas
        execute_command_schema = {
            "name": "claude_execute_command_direct",
            "description": "Execute a shell command directly using Claude CLI",
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
            "name": "claude_read_file_direct",
            "description": "Read a file directly using Claude CLI",
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
            "name": "claude_write_file_direct",
            "description": "Write to a file directly using Claude CLI",
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

        prompt_claude_schema = {
            "name": "prompt_claude_direct",
            "description": "Send a prompt directly to Claude CLI and receive a response",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt to send to Claude",
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "Optional system prompt to set context",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Optional temperature parameter (0.0-1.0)",
                    },
                },
                "required": ["prompt"],
            },
            "returns": {
                "type": "object",
                "properties": {
                    "success": {
                        "type": "boolean",
                        "description": "Whether the prompt was successful",
                    },
                    "response": {
                        "type": "string",
                        "description": "The textual response from Claude",
                    },
                },
            },
        }

        # Create FunctionTools based on ADK version
        try:
            # Try with function_schema (ADK 0.4.0+)
            try:
                execute_tool = FunctionTool(
                    function=execute_command_directly,
                    function_schema=execute_command_schema,
                )
                read_tool = FunctionTool(
                    function=read_file_directly, function_schema=read_file_schema
                )
                write_tool = FunctionTool(
                    function=write_file_directly, function_schema=write_file_schema
                )
                prompt_tool = FunctionTool(
                    function=prompt_claude_directly,
                    function_schema=prompt_claude_schema,
                )
                logger.info("Created direct Claude CLI tools with function_schema")
            except TypeError:
                # Try with schema (older ADK)
                execute_tool = FunctionTool(
                    execute_command_directly, schema=execute_command_schema
                )
                read_tool = FunctionTool(read_file_directly, schema=read_file_schema)
                write_tool = FunctionTool(write_file_directly, schema=write_file_schema)
                prompt_tool = FunctionTool(
                    prompt_claude_directly, schema=prompt_claude_schema
                )
                logger.info("Created direct Claude CLI tools with schema")
        except Exception as e:
            # Fallback to simple FunctionTool
            logger.warning(f"Error creating tools with schema: {e}, using basic tools")
            execute_tool = FunctionTool(execute_command_directly)
            read_tool = FunctionTool(read_file_directly)
            write_tool = FunctionTool(write_file_directly)
            prompt_tool = FunctionTool(prompt_claude_directly)

        # Add tools to the list
        tools.extend([execute_tool, read_tool, write_tool, prompt_tool])
        logger.info(f"Created {len(tools)} direct Claude CLI tools")

        return tools

    except Exception as e:
        logger.error(f"Error creating direct Claude CLI tools: {e}")
        return []


def list_claude_cli_tools() -> Dict[str, Any]:
    """
    List all available tools from Claude CLI.

    Returns:
        Dict with tools information
    """
    try:
        # Get Claude CLI config
        config = get_claude_cli_config()

        if not config:
            logger.error("Claude CLI configuration not found")
            return {
                "success": False,
                "error": "Claude CLI configuration not found",
                "tools": [],
            }

        # Get claude command and arguments
        claude_command = config.get("command", "claude")
        claude_args = ["--help"]

        # Set working directory
        cwd = config.get("working_directory", os.getcwd())

        # Execute the command
        logger.info(f"Listing Claude CLI help information")

        # Run the process
        process = subprocess.Popen(
            [claude_command] + claude_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
        )

        # Get the output
        stdout, stderr = process.communicate(timeout=60)
        exit_code = process.returncode

        # Since Claude CLI doesn't have a way to directly list tools,
        # we'll create a predefined list of tools we know our implementation supports
        tools_list = [
            {"name": "Bash", "description": "Execute shell commands"},
            {"name": "Read", "description": "Read files from the filesystem"},
            {"name": "Write", "description": "Write files to the filesystem"},
            {"name": "prompt_claude", "description": "Send a direct prompt to Claude"},
        ]

        # Process the output
        if exit_code == 0:
            return {"success": True, "tools": tools_list, "raw_output": stdout}
        else:
            return {"success": False, "error": stderr, "tools": []}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command execution timed out", "tools": []}
    except Exception as e:
        logger.error(f"Error listing Claude CLI help: {e}")
        return {"success": False, "error": str(e), "tools": []}


def test_direct_claude_cli_connection() -> Dict[str, Any]:
    """
    Test the direct connection to Claude CLI.

    Returns:
        Dict with test results
    """
    try:
        # Execute a simple command
        result = execute_command_directly("echo 'Hello from Direct Claude CLI'")

        if result.get("success", False):
            # Also try to list tools
            tools_result = list_claude_cli_tools()

            return {
                "success": True,
                "status": "connected",
                "output": result.get("output", "").strip(),
                "tools": tools_result.get("tools", []),
                "message": f"Successfully connected to Claude CLI directly with {len(tools_result.get('tools', []))} tools available",
            }
        else:
            return {
                "success": False,
                "status": "command_failed",
                "error": result.get("error", "Unknown error"),
                "message": "Failed to execute test command directly",
            }

    except Exception as e:
        logger.error(f"Error testing direct Claude CLI connection: {e}")
        return {
            "success": False,
            "status": "error",
            "error": str(e),
            "message": "Error testing direct Claude CLI connection",
        }


def main():
    """Command line entry point for testing."""
    # Set up logging
    logging.basicConfig(level=logging.INFO)

    print("Direct Claude CLI Integration Test")

    # List available tools
    print("\nListing available Claude CLI tools...")
    tools_result = list_claude_cli_tools()

    if tools_result.get("success", False):
        print(f"✅ Found {len(tools_result.get('tools', []))} tools:")
        for tool in tools_result.get("tools", []):
            print(f"  - {tool['name']}: {tool['description']}")
    else:
        print(f"❌ Failed to list tools: {tools_result.get('error', 'Unknown error')}")

    # Test connection
    print("\nTesting direct connection to Claude CLI...")
    connection_result = test_direct_claude_cli_connection()

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
    print("\nCreating direct tools...")
    tools = create_direct_claude_cli_tools()
    print(f"Created {len(tools)} tools:")
    for tool in tools:
        print(f"  - {getattr(tool, 'name', str(tool))}")

    # Test execute command
    print("\nTesting direct command execution...")
    cmd_result = execute_command_directly("pwd")
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
