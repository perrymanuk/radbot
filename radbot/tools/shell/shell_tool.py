"""Shell Command Execution Tool registration for the Agent SDK.

This module registers the shell command execution tool with the Google Agent SDK,
allowing the bot to execute shell commands with proper security controls.
It supports both subprocess and Claude CLI MCP backends for command execution.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from google.adk.tools import FunctionTool

from radbot.tools.shell.shell_command import ALLOWED_COMMANDS, execute_shell_command

logger = logging.getLogger(__name__)


def execute_command_with_claude(
    command: str,
    arguments: Optional[List[str]] = None,
    timeout: int = 120,
    strict_mode: bool = True,
) -> Dict[str, Any]:
    """
    Execute a shell command (Claude CLI support has been removed).

    This function now just returns an error message indicating that
    Claude CLI command execution has been deprecated in favor of direct prompting.

    Args:
        command: The command to execute
        arguments: Command arguments (optional)
        timeout: Maximum execution time in seconds
        strict_mode: Whether to enforce command allowlisting

    Returns:
        Dict with error message
    """
    error_message = "Claude CLI shell integration has been removed. Only Claude direct prompting is supported."
    logger.warning(error_message)
    return {
        "stdout": "",
        "stderr": error_message,
        "return_code": -1,
        "error": error_message,
    }


def get_shell_tool(strict_mode: bool = True, use_claude_cli: bool = False) -> Any:
    """Get the shell command execution tool configured for the Google Agent SDK.

    Args:
        strict_mode: When True, only allow-listed commands are permitted.
                    When False, any command can be executed (SECURITY RISK).
        use_claude_cli: Whether to use Claude CLI for command execution (deprecated).
                    Now always uses subprocess regardless of this setting.

    Returns:
        A tool object ready to be used with the agent.
    """
    # Warn if attempting to use Claude CLI
    if use_claude_cli:
        logger.warning(
            "Claude CLI shell execution has been removed. Using subprocess instead."
        )

    # Dynamically generate the description based on the allowed commands
    allowed_commands_str = ", ".join(sorted(list(ALLOWED_COMMANDS)))

    if strict_mode:
        tool_description = (
            f"Executes an allow-listed shell command and returns its output. "
            f"Only the following commands are permitted: {allowed_commands_str}. "
            f"Provide the command name and a list of arguments."
        )
    else:
        tool_description = (
            "WARNING - SECURITY RISK: Executes any shell command and returns its output. "
            "This mode bypasses command allow-listing and permits execution of ANY command. "
            "Use with extreme caution. Provide the command name and a list of arguments."
        )
        logger.warning("Shell tool initialized in ALLOW ALL mode - SECURITY RISK")

    # Always using subprocess now
    tool_description += f" (Using subprocess for execution)"

    # Create a wrapper function for ADK compatibility
    def shell_command_tool(
        command: str, arguments: Optional[List[str]] = None, timeout: int = 60
    ) -> Dict[str, Any]:
        """Execute a shell command securely.

        Args:
            command: The command to execute. In strict mode, must be in ALLOWED_COMMANDS.
            arguments: A list of arguments to pass to the command.
            timeout: Maximum execution time in seconds.

        Returns:
            A dictionary with stdout, stderr, return_code, and error information.
        """
        if arguments is None:
            arguments = []

        # Always use subprocess
        logger.info(f"Executing command '{command}' using subprocess")
        return execute_shell_command(
            command=command,
            arguments=arguments,
            timeout=timeout,
            strict_mode=strict_mode,
        )

    # Set metadata for the function
    shell_command_tool.__name__ = "execute_shell_command"
    shell_command_tool.__doc__ = tool_description

    # Wrap in FunctionTool for ADK compatibility
    return FunctionTool(shell_command_tool)


async def handle_shell_function_call(
    function_name: str,
    arguments: Dict[str, Any],
    strict_mode: bool = True,
    use_claude_cli: bool = False,
) -> Dict[str, Any]:
    """Handle function calls from the agent to the shell command execution tool.

    Args:
        function_name: The name of the function being called.
        arguments: The arguments passed to the function.
        strict_mode: Whether to enforce command allow-listing.
        use_claude_cli: Whether to use Claude CLI for command execution (deprecated).
                        Now always uses subprocess regardless of this setting.

    Returns:
        The result of executing the shell command.
    """
    # Warn if attempting to use Claude CLI
    if use_claude_cli:
        logger.warning(
            "Claude CLI shell execution has been removed. Using subprocess instead."
        )

    if function_name != "execute_shell_command":
        error_message = f"Unknown function: {function_name}"
        logger.error(error_message)
        return {
            "stdout": "",
            "stderr": error_message,
            "return_code": -1,
            "error": error_message,
        }

    # Extract and validate arguments
    command = arguments.get("command", "")
    if not command:
        error_message = "No command specified"
        logger.error(error_message)
        return {
            "stdout": "",
            "stderr": error_message,
            "return_code": -1,
            "error": error_message,
        }

    # Extract optional arguments with defaults
    arg_list = arguments.get("arguments", [])
    timeout = arguments.get("timeout", 60)

    # Type validation for arguments
    if not isinstance(arg_list, list):
        error_message = "Arguments must be a list"
        logger.error(error_message)
        return {
            "stdout": "",
            "stderr": error_message,
            "return_code": -1,
            "error": error_message,
        }

    if not isinstance(timeout, int) or timeout <= 0:
        error_message = "Timeout must be a positive integer"
        logger.error(error_message)
        return {
            "stdout": "",
            "stderr": error_message,
            "return_code": -1,
            "error": error_message,
        }

    # Always use subprocess now
    logger.info(f"Function call: Executing command '{command}' using subprocess")
    return execute_shell_command(
        command=command, arguments=arg_list, timeout=timeout, strict_mode=strict_mode
    )
