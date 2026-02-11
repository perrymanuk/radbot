"""Simple Axel toolset for specialized agents.

This module provides a simplified version of the Axel toolset that doesn't
depend on external MCP servers for sequential thinking.
"""

import functools
import logging
from typing import Any, Dict, List, Optional

# Import filesystem tools for Axel
try:
    from radbot.filesystem.tools import (
        edit_file,
        get_info,
        list_directory,
        read_file,
        search,
        write_file,
    )
except ImportError:
    # Define placeholders if not available
    read_file = None
    write_file = None
    edit_file = None
    list_directory = None
    search = None
    get_info = None

# Import code execution tools for Axel
try:
    from radbot.tools.shell.shell_tool import execute_shell_command
except ImportError:
    execute_shell_command = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)


# Create function tools for filesystem operations
def create_read_file_func(fn):
    """Create a read file function tool."""

    @functools.wraps(fn)
    def read_file_func(params):
        path = params.get("path", "")
        return fn(path)

    read_file_func.__name__ = "read_file_func"
    return read_file_func


def create_write_file_func(fn):
    """Create a write file function tool."""

    @functools.wraps(fn)
    def write_file_func(params):
        path = params.get("path", "")
        content = params.get("content", "")
        overwrite = params.get("overwrite", False)
        return fn(path, content, overwrite)

    write_file_func.__name__ = "write_file_func"
    return write_file_func


def create_edit_file_func(fn):
    """Create an edit file function tool."""

    @functools.wraps(fn)
    def edit_file_func(params):
        path = params.get("path", "")
        edits = params.get("edits", [])
        dry_run = params.get("dry_run", False)
        return fn(path, edits, dry_run)

    edit_file_func.__name__ = "edit_file_func"
    return edit_file_func


def create_list_directory_func(fn):
    """Create a list directory function tool."""

    @functools.wraps(fn)
    def list_directory_func(params):
        path = params.get("path", "")
        return fn(path)

    list_directory_func.__name__ = "list_directory_func"
    return list_directory_func


def create_search_func(fn):
    """Create a search function tool."""

    @functools.wraps(fn)
    def search_func(params):
        path = params.get("path", "")
        pattern = params.get("pattern", "*")
        exclude_patterns = params.get("exclude_patterns", [])
        return fn(path, pattern, exclude_patterns)

    search_func.__name__ = "search_func"
    return search_func


def create_get_info_func(fn):
    """Create a get info function tool."""

    @functools.wraps(fn)
    def get_info_func(params):
        path = params.get("path", "")
        return fn(path)

    get_info_func.__name__ = "get_info_func"
    return get_info_func


def create_simple_axel_toolset() -> List[Any]:
    """Create a simplified set of tools for the Axel specialized agent.

    This version doesn't depend on external MCP servers for sequential thinking.

    Returns:
        List of tools for implementation and execution
    """
    toolset = []

    # Add filesystem functions wrapped as ADK function tools
    if read_file:
        try:
            toolset.append(create_read_file_func(read_file))
            logger.info("Added read_file_func to Simple Axel toolset")
        except Exception as e:
            logger.error(f"Failed to add read_file_func: {e}")

    if write_file:
        try:
            toolset.append(create_write_file_func(write_file))
            logger.info("Added write_file_func to Simple Axel toolset")
        except Exception as e:
            logger.error(f"Failed to add write_file_func: {e}")

    if edit_file:
        try:
            toolset.append(create_edit_file_func(edit_file))
            logger.info("Added edit_file_func to Simple Axel toolset")
        except Exception as e:
            logger.error(f"Failed to add edit_file_func: {e}")

    if list_directory:
        try:
            toolset.append(create_list_directory_func(list_directory))
            logger.info("Added list_directory_func to Simple Axel toolset")
        except Exception as e:
            logger.error(f"Failed to add list_directory_func: {e}")

    if search:
        try:
            toolset.append(create_search_func(search))
            logger.info("Added search_func to Simple Axel toolset")
        except Exception as e:
            logger.error(f"Failed to add search_func: {e}")

    if get_info:
        try:
            toolset.append(create_get_info_func(get_info))
            logger.info("Added get_info_func to Simple Axel toolset")
        except Exception as e:
            logger.error(f"Failed to add get_info_func: {e}")

    # Add shell command execution
    if execute_shell_command:
        try:
            toolset.append(execute_shell_command)
            logger.info("Added execute_shell_command to Simple Axel toolset")
        except Exception as e:
            logger.error(f"Failed to add execute_shell_command: {e}")

    return toolset


# Register the toolset with the system
register_toolset(
    name="axel",
    toolset_func=create_simple_axel_toolset,
    description="Agent specialized in implementation and execution",
    allowed_transfers=["scout", "code_execution"],  # Axel can transfer to these agents
)
