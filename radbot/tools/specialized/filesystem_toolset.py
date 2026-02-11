"""Filesystem toolset for specialized agents.

This module provides tools for file system operations, including reading,
writing, searching, and managing files and directories.
"""

import functools
import logging
from typing import Any, Dict, List, Optional

# Import filesystem tools
try:
    from radbot.filesystem.tools import (
        copy,
        delete,
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
    copy = None
    delete = None

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


def create_copy_func(fn):
    """Create a copy function tool."""

    @functools.wraps(fn)
    def copy_func(params):
        source = params.get("source", "")
        destination = params.get("destination", "")
        return fn(source, destination)

    copy_func.__name__ = "copy_func"
    return copy_func


def create_delete_func(fn):
    """Create a delete function tool."""

    @functools.wraps(fn)
    def delete_func(params):
        path = params.get("path", "")
        return fn(path)

    delete_func.__name__ = "delete_func"
    return delete_func


def create_filesystem_toolset() -> List[Any]:
    """Create the set of tools for the filesystem specialized agent.

    Returns:
        List of tools for file system operations
    """
    toolset = []

    # Add filesystem functions wrapped as ADK function tools
    fs_tools = [
        (read_file, create_read_file_func, "read_file_func"),
        (write_file, create_write_file_func, "write_file_func"),
        (edit_file, create_edit_file_func, "edit_file_func"),
        (list_directory, create_list_directory_func, "list_directory_func"),
        (search, create_search_func, "search_func"),
        (get_info, create_get_info_func, "get_info_func"),
        (copy, create_copy_func, "copy_func"),
        (delete, create_delete_func, "delete_func"),
    ]

    for fn, wrapper, name in fs_tools:
        if fn:
            try:
                toolset.append(wrapper(fn))
                logger.info(f"Added {name} to filesystem toolset")
            except Exception as e:
                logger.error(f"Failed to add {name}: {e}")

    return toolset


# Register the toolset with the system
register_toolset(
    name="filesystem",
    toolset_func=create_filesystem_toolset,
    description="Agent specialized in filesystem operations",
    allowed_transfers=[],  # Only allows transfer back to main orchestrator
)
