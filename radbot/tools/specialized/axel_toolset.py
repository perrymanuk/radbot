"""Axel toolset for specialized agents.

This module provides tools specific to the Axel agent, which focuses on
implementation and execution capabilities.
"""

import logging
from typing import List, Any, Optional

# Import filesystem tools for Axel
try:
    from radbot.filesystem.tools import (
        read_file_func,
        list_directory_func,
        search_func,
        write_file_func,
        edit_file_func
    )
except ImportError:
    # Define placeholders if not available
    read_file_func = None
    list_directory_func = None
    search_func = None
    write_file_func = None
    edit_file_func = None

# Import code execution tools for Axel
try:
    from radbot.tools.shell.shell_tool import execute_shell_command
except ImportError:
    execute_shell_command = None

# Import dynamic worker system if available
try:
    from radbot.agent.research_agent.sequential_thinking import create_sequential_thinking_tool
except ImportError:
    create_sequential_thinking_tool = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)

def create_axel_toolset() -> List[Any]:
    """Create the set of tools for the Axel specialized agent.
    
    Axel is a powerful execution agent that combines filesystem operations,
    code execution, and dynamic worker capabilities.
    
    Returns:
        List of tools for implementation and execution
    """
    toolset = []
    
    # Add essential filesystem tools
    fs_tools = [
        (read_file_func, "read_file_func"),
        (list_directory_func, "list_directory_func"),
        (search_func, "search_func"),
        (write_file_func, "write_file_func"),
        (edit_file_func, "edit_file_func")
    ]
    
    for tool, name in fs_tools:
        if tool:
            try:
                toolset.append(tool)
                logger.info(f"Added {name} to Axel toolset")
            except Exception as e:
                logger.error(f"Failed to add {name}: {e}")
    
    # Add shell command execution
    if execute_shell_command:
        try:
            toolset.append(execute_shell_command)
            logger.info("Added execute_shell_command to Axel toolset")
        except Exception as e:
            logger.error(f"Failed to add execute_shell_command: {e}")
    
    # Add sequential thinking for structured implementation
    if create_sequential_thinking_tool:
        try:
            seq_thinking_tool = create_sequential_thinking_tool()
            if seq_thinking_tool:
                toolset.append(seq_thinking_tool)
                logger.info("Added sequential_thinking tool to Axel toolset")
        except Exception as e:
            logger.error(f"Failed to add sequential_thinking tool: {e}")
    
    return toolset

# Register the toolset with the system
register_toolset(
    name="axel",
    toolset_func=create_axel_toolset,
    description="Agent specialized in implementation and execution",
    allowed_transfers=["scout", "code_execution"]  # Axel can transfer to these agents
)