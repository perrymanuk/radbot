"""
Integration of filesystem tools with the ADK.

This module provides the integration of filesystem operations with the
Google Agent Development Kit (ADK) by exposing the operations as function tools.
"""

import logging
from typing import Any, Dict, List, Optional

# Import ADK components for tool registration
from google.adk.tools import FunctionTool

from radbot.filesystem.security import (
    get_allowed_directories,
    set_allowed_directories,
)
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

logger = logging.getLogger(__name__)


def _create_read_file_tool() -> FunctionTool:
    """Create the read_file tool."""

    def read_file_func(path: str) -> str:
        """
        Read the contents of a file.

        Args:
            path: Path to the file to read

        Returns:
            Content of the file as a string
        """
        return read_file(path)

    return FunctionTool(func=read_file_func)


def _create_write_file_tool() -> FunctionTool:
    """Create the write_file tool."""

    def write_file_func(
        path: str, content: str, overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Write content to a file.

        Args:
            path: Path to the file to write
            content: Content to write to the file
            overwrite: If True, overwrite existing file

        Returns:
            Information about the operation
        """
        return write_file(path, content, overwrite)

    return FunctionTool(func=write_file_func)


def _create_edit_file_tool() -> FunctionTool:
    """Create the edit_file tool."""

    def edit_file_func(
        path: str, edits: List[Dict[str, str]], dry_run: bool = False
    ) -> str:
        """
        Edit a file by applying a list of changes.

        Args:
            path: Path to the file to edit
            edits: List of edits, each with 'oldText' and 'newText' keys
            dry_run: If True, return diff without applying changes

        Returns:
            Unified diff of changes
        """
        return edit_file(path, edits, dry_run)

    return FunctionTool(func=edit_file_func)


def _create_copy_tool() -> FunctionTool:
    """Create the copy tool."""

    def copy_func(source_path: str, destination_path: str) -> Dict[str, Any]:
        """
        Copy a file or directory.

        Args:
            source_path: Source path
            destination_path: Destination path

        Returns:
            Information about the operation
        """
        return copy(source_path, destination_path)

    return FunctionTool(func=copy_func)


def _create_delete_tool() -> FunctionTool:
    """Create the delete tool."""

    def delete_func(path: str) -> Dict[str, Any]:
        """
        Delete a file or directory.

        Args:
            path: Path to delete

        Returns:
            Information about the operation
        """
        return delete(path)

    return FunctionTool(func=delete_func)


def _create_list_directory_tool() -> FunctionTool:
    """Create the list_directory tool."""

    def list_directory_func(path: str = "") -> List[Dict[str, Any]]:
        """
        List the contents of a directory.

        Args:
            path: Directory path to list

        Returns:
            List of file and directory information
        """
        return list_directory(path)

    return FunctionTool(func=list_directory_func)


def _create_get_info_tool() -> FunctionTool:
    """Create the get_info tool."""

    def get_info_func(path: str) -> Dict[str, Any]:
        """
        Get detailed information about a file or directory.

        Args:
            path: Path to get information for

        Returns:
            Detailed file or directory metadata
        """
        return get_info(path)

    return FunctionTool(func=get_info_func)


def _create_search_tool() -> FunctionTool:
    """Create the search tool."""

    def search_func(
        path: str, pattern: str, exclude_patterns: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for files or directories matching a pattern.

        Args:
            path: Base path to search from
            pattern: Glob pattern to match filenames against
            exclude_patterns: Optional list of patterns to exclude

        Returns:
            List of matching file and directory information
        """
        return search(path, pattern, exclude_patterns)

    return FunctionTool(func=search_func)


def create_filesystem_tools(
    allowed_directories: List[str],
    enable_write: bool = False,
    enable_delete: bool = False,
) -> List[FunctionTool]:
    """
    Create the filesystem tools for use with ADK.

    Args:
        allowed_directories: List of directories to allow access to
        enable_write: If True, enable write operations
        enable_delete: If True, enable delete operations

    Returns:
        List of FunctionTool instances
    """
    logger.info(
        f"Creating filesystem tools with write={enable_write}, delete={enable_delete}"
    )

    # Configure security
    set_allowed_directories(allowed_directories)

    # Create the tools
    tools = [
        _create_read_file_tool(),
        _create_list_directory_tool(),
        _create_get_info_tool(),
        _create_search_tool(),
    ]

    # Add write tools if enabled
    if enable_write:
        tools.extend(
            [
                _create_write_file_tool(),
                _create_edit_file_tool(),
                _create_copy_tool(),
            ]
        )

    # Add delete tool if enabled
    if enable_delete:
        tools.append(_create_delete_tool())

    logger.info(f"Created {len(tools)} filesystem tools")
    return tools
