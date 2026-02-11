#!/usr/bin/env python3
"""
Claude CLI Direct Prompting Tool

This module provides a direct, simplified interface to Claude CLI for sending prompts
and getting responses. It bypasses the more complex MCP architecture and directly
executes the Claude CLI command with appropriate arguments.
"""

import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Union

from google.adk.tools import FunctionTool

from radbot.config.config_loader import config_loader

logger = logging.getLogger(__name__)


def get_claude_cli_config() -> Dict[str, Any]:
    """
    Get configuration for the Claude CLI from config.yaml.

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
        logger.warning("Claude CLI server not found in enabled MCP servers")
        return {}

    except Exception as e:
        logger.error(f"Error getting Claude CLI config: {e}")
        return {}


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


def prompt_claude(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Send a prompt to Claude CLI.

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
        use_json_output = support_check.get("json_output", True)
        claude_args = ["--print"]

        # Add JSON output format if supported
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
                        return prompt_claude_raw(prompt, system_prompt, temperature)

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


def prompt_claude_raw(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Send a prompt to Claude CLI without JSON formatting.
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


def create_claude_prompt_tool() -> FunctionTool:
    """
    Create a FunctionTool for the prompt_claude function.

    Returns:
        FunctionTool instance for the prompt function
    """
    # Create tool schema
    prompt_claude_schema = {
        "name": "prompt_claude",
        "description": "Send a prompt to Claude CLI and receive a response",
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

    # Create FunctionTool - use ADK 0.4.0+ style since that's what we're using
    try:
        # In ADK 0.4.0, FunctionTool uses 'func' parameter instead of 'function'
        prompt_tool = FunctionTool(func=prompt_claude)
        logger.info("Created Claude prompt tool with proper ADK 0.4.0 parameters")
    except Exception as e:
        # Log the error and fallback to a basic configuration
        logger.warning(
            f"Error creating tool with FunctionTool: {e}, trying fallback approach"
        )
        # Last resort fallback - this should not normally be needed
        try:
            prompt_tool = FunctionTool(prompt_claude)
            logger.info("Created Claude prompt tool using positional parameter")
        except Exception as e2:
            logger.error(f"Could not create FunctionTool at all: {e2}")
            raise

    return prompt_tool
