"""Shell Command Execution Tool.

This module provides a secure implementation of shell command execution
for the radbot agent, utilizing Python's subprocess module with multiple
security controls.

The implementation follows two modes:
1. Strict Mode (default): Only allows execution of pre-approved commands
2. Allow All Mode: Permits execution of any command (SECURITY RISK)

Security measures include:
- Command allow-listing (in strict mode)
- Basic argument validation
- shell=False to prevent shell metacharacter interpretation
- Command and arguments passed as separate list elements
- Timeout enforcement to prevent runaway processes
- Comprehensive error handling and logging
"""

import logging
import shlex
import subprocess
from typing import Any, Dict, List, Optional

# --- Security Configuration ---
# CRITICAL: Define the *only* commands the agent is allowed to run in strict mode.
# Keep this list as minimal as absolutely necessary for agent functionality.
ALLOWED_COMMANDS = {
    # File navigation and inspection
    "ls",
    "pwd",
    "cd",
    "find",
    "locate",
    # File content viewing
    "cat",
    "head",
    "tail",
    "less",
    "more",
    "grep",
    "egrep",
    "fgrep",
    "zgrep",
    # File manipulation
    "cp",
    "mv",
    "rm",
    "mkdir",
    "rmdir",
    "touch",
    "chmod",
    "chown",
    # System information
    "ps",
    "top",
    "df",
    "du",
    "free",
    "uname",
    "whoami",
    "id",
    "uptime",
    "w",
    # Network utilities
    "ping",
    "netstat",
    "ifconfig",
    "ip",
    "ss",
    "dig",
    "nslookup",
    "curl",
    "wget",
    # Text processing
    "echo",
    "sort",
    "uniq",
    "wc",
    "cut",
    "awk",
    "sed",
    "tr",
    "diff",
    "comm",
    # Archive and compression
    "tar",
    "gzip",
    "gunzip",
    "zip",
    "unzip",
    "bzip2",
    "bunzip2",
    # Code search and version control
    "rg",
    "ripgrep",
    "git",
    "gh",
    # Python tooling
    "uv",
    "pip",
    # Miscellaneous utilities
    "date",
    "cal",
    "which",
    "whereis",
    "who",
    "history",
    "env",
    "printenv",
}  # Expanded set of commands to provide more functionality

DEFAULT_TIMEOUT = 120  # Default execution timeout in seconds (increased to 2 minutes)
# --------------------------

logger = logging.getLogger(__name__)


def execute_shell_command(
    command: str,
    arguments: List[str] = [],
    timeout: int = DEFAULT_TIMEOUT,
    strict_mode: bool = True,
) -> Dict[str, Any]:
    """Execute a shell command securely using subprocess.

    Args:
        command: The command to execute. In strict mode, must be in ALLOWED_COMMANDS.
        arguments: A list of string arguments to pass to the command.
        timeout: Maximum execution time in seconds. Defaults to DEFAULT_TIMEOUT.
        strict_mode: When True, only allow-listed commands are permitted.
                    When False, any command can be executed (SECURITY RISK).

    Returns:
        A dictionary containing:
        - 'stdout' (str): The standard output captured from the command.
        - 'stderr' (str): The standard error captured from the command.
        - 'return_code' (int): The exit code returned by the command.
          -1 indicates an execution error before the command ran.
        - 'error' (Optional[str]): Description of any error that occurred.
          None on success (return code 0).
    """
    logger.info(f"Attempting to execute command: {command} with arguments: {arguments}")

    # --- Security Check 1: Command Allow-listing (only when strict_mode is True) ---
    if strict_mode and command not in ALLOWED_COMMANDS:
        error_message = f"Error: Command '{command}' is not allowed in strict mode."
        logger.warning(error_message)
        return {
            "stdout": "",
            "stderr": error_message,
            "return_code": -1,
            "error": error_message,
        }

    # Log security warning if executing non-allow-listed command
    if not strict_mode and command not in ALLOWED_COMMANDS:
        logger.warning(
            f"SECURITY WARNING: Executing non-allow-listed command '{command}' with strict_mode=False"
        )

    # --- Security Check 2: Smart Argument Validation ---
    # More robust validation that provides reasonable flexibility
    # while maintaining security controls
    sanitized_arguments = []

    # High-risk shell metacharacters that could allow command chaining or injection
    high_risk_chars = [";", "|", "&", "$", "`"]

    # Exempt certain commands from strict character filtering
    # These commands commonly need special characters in their arguments
    command_exemptions = {
        # Git commands often use special characters
        "git": ["<", ">", "(", ")", "\\", ".."],
        "gh": ["<", ">", "(", ")", "\\", ".."],
        # Search tools often need regex patterns with special characters
        "grep": ["|", "(", ")", "[", "]", "{", "}", "\\", "."],
        "egrep": ["|", "(", ")", "[", "]", "{", "}", "\\", "."],
        "fgrep": ["|", "(", ")", "[", "]", "{", "}", "\\", "."],
        "rg": ["|", "(", ")", "[", "]", "{", "}", "\\", "."],
        "ripgrep": ["|", "(", ")", "[", "]", "{", "}", "\\", "."],
        # Text processing tools that use regex or special syntax
        "sed": ["|", "(", ")", "[", "]", "{", "}", "\\", ".", "/"],
        "awk": ["|", "(", ")", "[", "]", "{", "}", "\\", ".", "/"],
        "tr": ["[", "]", "\\"],
        # Shell utilities that might need path traversal
        "cd": [".."],
        "cp": [".."],
        "mv": [".."],
        "find": ["..", "(", ")", "\\"],
        # Package managers often use URLs or complex arguments
        "pip": ["<", ">", "@", "=", "+", ".."],
        "uv": ["<", ">", "@", "=", "+", ".."],
    }

    # Get the list of characters exempted for this command
    exempted_chars = command_exemptions.get(command, [])

    for arg in arguments:
        # Filter out high-risk characters that aren't exempted for this command
        risky_chars_present = [
            char
            for char in high_risk_chars
            if char in arg and char not in exempted_chars
        ]

        # Check for potential path traversal (.. in paths) unless exempted
        path_traversal_risk = ".." in arg and ".." not in exempted_chars

        if risky_chars_present:
            error_message = f"Error: Argument '{arg}' contains potentially unsafe characters: {', '.join(risky_chars_present)}"
            logger.warning(f"Rejected unsafe argument for command '{command}': {arg}")
            return {
                "stdout": "",
                "stderr": error_message,
                "return_code": -1,
                "error": error_message,
            }

        if path_traversal_risk:
            error_message = f"Error: Argument '{arg}' contains path traversal sequences which are not allowed for this command."
            logger.warning(
                f"Rejected path traversal in argument for command '{command}': {arg}"
            )
            return {
                "stdout": "",
                "stderr": error_message,
                "return_code": -1,
                "error": error_message,
            }

        sanitized_arguments.append(arg)

    command_to_run = [command] + sanitized_arguments
    logger.info(f"Executing validated command list: {command_to_run}")

    try:
        # --- Secure Execution ---
        result = subprocess.run(
            command_to_run,
            capture_output=True,  # Capture stdout/stderr
            text=True,  # Decode stdout/stderr as text
            check=False,  # Manually handle return codes
            timeout=timeout,  # Enforce execution time limit
            shell=False,  # CRITICAL: Prevent shell interpretation
        )

        # --- Process Results ---
        if result.returncode == 0:
            logger.info(f"Command '{command}' executed successfully. Return code: 0.")
            error_info = None
        else:
            error_info = f"Command exited with non-zero status {result.returncode}."
            logger.warning(
                f"Command '{command}' failed. Return code: {result.returncode}. "
                f"Stderr: {result.stderr.strip()}"
            )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "error": error_info,
        }

    # --- Exception Handling ---
    except FileNotFoundError:
        error_message = f"Error: Command '{command}' not found. Check system PATH."
        logger.error(error_message)
        return {
            "stdout": "",
            "stderr": error_message,
            "return_code": -1,
            "error": error_message,
        }
    except subprocess.TimeoutExpired:
        error_message = f"Error: Command '{command}' timed out after {timeout} seconds."
        logger.warning(error_message)
        return {
            "stdout": "",
            "stderr": error_message,
            "return_code": -1,
            "error": error_message,
        }
    except PermissionError:
        error_message = f"Error: Permission denied executing command '{command}'."
        logger.error(error_message)
        return {
            "stdout": "",
            "stderr": error_message,
            "return_code": -1,
            "error": error_message,
        }
    except Exception as e:
        # Catch unexpected errors, log securely
        error_message = f"An unexpected error occurred: {type(e).__name__}"
        logger.exception(
            f"Unexpected error executing command '{command}': {e}", exc_info=True
        )
        return {
            "stdout": "",
            "stderr": error_message,
            "return_code": -1,
            "error": error_message,
        }
