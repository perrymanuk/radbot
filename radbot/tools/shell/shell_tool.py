"""Shell Command Execution Tool registration for the Agent SDK.

This module registers the shell command execution tool with the Google Agent SDK,
allowing the bot to execute shell commands with proper security controls.
It supports both subprocess and Claude CLI MCP backends for command execution.
"""

import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from radbot.tools.shell.shell_command import ALLOWED_COMMANDS, execute_shell_command

logger = logging.getLogger(__name__)


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
    tool_description += " (Using subprocess for execution)"

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
