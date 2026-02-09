"""Code execution toolset for specialized agents.

This module provides tools for executing shell commands and code,
as well as tools for managing execution environments.
"""

import logging
from typing import List, Any, Optional

# Import shell execution tools
try:
    from radbot.tools.shell.shell_tool import execute_shell_command
except ImportError:
    execute_shell_command = None

# Import ADK built-in code execution tool if available
try:
    from radbot.tools.adk_builtin.code_execution_tool import create_code_execution_tool
except ImportError:
    create_code_execution_tool = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)

def create_code_execution_toolset() -> List[Any]:
    """Create the set of tools for the code execution specialized agent.
    
    Returns:
        List of tools for executing code and shell commands
    """
    toolset = []
    
    # Add shell command execution tool
    if execute_shell_command:
        try:
            toolset.append(execute_shell_command)
            logger.info("Added execute_shell_command to code execution toolset")
        except Exception as e:
            logger.error(f"Failed to add execute_shell_command: {e}")
    
    # Add ADK built-in code execution tool if available
    if create_code_execution_tool:
        try:
            code_execution_tool = create_code_execution_tool()
            if code_execution_tool:
                toolset.append(code_execution_tool)
                logger.info("Added code_execution_tool to code execution toolset")
        except Exception as e:
            logger.error(f"Failed to add code_execution_tool: {e}")
    
    return toolset

# Register the toolset with the system
register_toolset(
    name="code_execution",
    toolset_func=create_code_execution_toolset,
    description="Agent specialized in executing code and shell commands",
    allowed_transfers=["axel"]  # Can receive transfers from Axel agent
)