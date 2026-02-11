"""
Core filesystem operation tools.

This module provides the implementation of filesystem operations
that can be used by ADK agents.
"""

import difflib
import fnmatch
import logging
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from radbot.filesystem.security import create_parent_directory, validate_path

logger = logging.getLogger(__name__)


def read_file(path: str) -> str:
    """
    Read the entire content of a specified file.

    Args:
        path: Path to the file to read

    Returns:
        File content as a string

    Raises:
        PermissionError: If path is outside allowed directories
        FileNotFoundError: If file doesn't exist
        ValueError: If path is not a file
        IOError: If file cannot be read
    """
    try:
        # Validate path
        full_path = validate_path(path, must_exist=True)

        # Check if it's a file
        if not os.path.isfile(full_path):
            raise ValueError(f"Path is not a file: {path}")

        # Read file with UTF-8 encoding
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return content
    except (PermissionError, FileNotFoundError, ValueError) as e:
        # Re-raise known exceptions
        logger.warning(f"Error reading file {path}: {str(e)}")
        raise
    except Exception as e:
        # Log and wrap other exceptions
        logger.error(f"Error reading file {path}: {str(e)}")
        raise IOError(f"Error reading file: {str(e)}")


def write_file(path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    Write content to a specified file.

    Args:
        path: Path to the file to write
        content: Content to write to the file
        overwrite: If True, overwrite existing file; if False, fail if file exists

    Returns:
        Dict with operation results

    Raises:
        PermissionError: If path is outside allowed directories
        FileExistsError: If file exists and overwrite is False
        IOError: If file cannot be written
    """
    try:
        # Validate path
        full_path = validate_path(path)

        # Check if file exists and overwrite is False
        if not overwrite and os.path.exists(full_path):
            raise FileExistsError(f"File already exists: {path}")

        # Create parent directory if needed
        create_parent_directory(full_path)

        # Write file with UTF-8 encoding
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "path": path,
            "operation": "write",
            "status": "success",
            "size": len(content),
            "overwrite": os.path.exists(full_path) and overwrite,
        }
    except (PermissionError, FileExistsError) as e:
        # Re-raise known exceptions
        logger.warning(f"Error writing file {path}: {str(e)}")
        raise
    except Exception as e:
        # Log and wrap other exceptions
        logger.error(f"Error writing file {path}: {str(e)}")
        raise IOError(f"Error writing file: {str(e)}")


def _normalize_line_endings(text: str) -> str:
    """
    Normalize line endings to \n.

    Args:
        text: Text to normalize

    Returns:
        Text with normalized line endings
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _find_text_match(content: str, old_text: str) -> Optional[int]:
    """
    Find the position of old_text in content.

    Handles both exact matches and line-by-line comparisons.

    Args:
        content: The content to search in
        old_text: The text to find

    Returns:
        Index of the match or None if not found
    """
    # First try exact match
    index = content.find(old_text)
    if index != -1:
        return index

    # If exact match fails, try line-by-line comparison
    content_lines = content.split("\n")
    old_text_lines = old_text.split("\n")

    # Need at least as many lines in content as in old_text
    if len(content_lines) < len(old_text_lines):
        return None

    # Try to find a match
    for i in range(len(content_lines) - len(old_text_lines) + 1):
        match = True

        for j in range(len(old_text_lines)):
            # Compare lines, but ignore whitespace differences
            if content_lines[i + j].strip() != old_text_lines[j].strip():
                match = False
                break

        if match:
            # Calculate the character index
            index = 0
            for k in range(i):
                index += len(content_lines[k]) + 1  # +1 for the newline
            return index

    return None


def _preserve_indentation(original_line: str, new_text: str) -> str:
    """
    Preserve indentation from original line in new text.

    Args:
        original_line: The original line with indentation
        new_text: The new text to indent

    Returns:
        Indented new text
    """
    # Determine leading whitespace
    leading_whitespace = ""
    for char in original_line:
        if char in (" ", "\t"):
            leading_whitespace += char
        else:
            break

    # Apply indentation to each line
    lines = new_text.split("\n")
    for i in range(1, len(lines)):
        lines[i] = leading_whitespace + lines[i]

    return "\n".join(lines)


def edit_file(path: str, edits: List[Dict[str, str]], dry_run: bool = False) -> str:
    """
    Edit a file by applying a list of changes.

    Args:
        path: Path to the file to edit
        edits: List of edits, each with 'oldText' and 'newText' keys
        dry_run: If True, return diff without applying changes

    Returns:
        Unified diff of changes

    Raises:
        PermissionError: If path is outside allowed directories
        FileNotFoundError: If file doesn't exist
        ValueError: If edits are invalid or text cannot be found
        IOError: If file cannot be read or written
    """
    try:
        # Validate path
        full_path = validate_path(path, must_exist=True)

        # Check if it's a file
        if not os.path.isfile(full_path):
            raise ValueError(f"Path is not a file: {path}")

        # Read file with UTF-8 encoding
        with open(full_path, "r", encoding="utf-8") as f:
            original_content = f.read()

        # Normalize line endings
        content = _normalize_line_endings(original_content)

        # Apply each edit
        for i, edit in enumerate(edits):
            if "oldText" not in edit or "newText" not in edit:
                raise ValueError(f"Edit {i} is missing 'oldText' or 'newText'")

            old_text = _normalize_line_endings(edit["oldText"])
            new_text = _normalize_line_endings(edit["newText"])

            # Find the match
            index = _find_text_match(content, old_text)
            if index is None:
                raise ValueError(f"Could not find text to replace for edit {i}")

            # Identify the original indentation for preserving in new text
            if "\n" in old_text:
                # Find the original line at this position
                original_line = original_content.split("\n")[
                    len(content[:index].split("\n")) - 1
                ]
                # Preserve indentation in new text
                new_text = _preserve_indentation(original_line, new_text)

            # Apply the edit
            content = content[:index] + new_text + content[index + len(old_text) :]

        # Generate the diff
        original_lines = original_content.splitlines(keepends=True)
        new_lines = content.splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(
                original_lines,
                new_lines,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=3,  # Context lines
            )
        )

        # Write the changes if not dry run
        if not dry_run:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

        return diff
    except (PermissionError, FileNotFoundError, ValueError) as e:
        # Re-raise known exceptions
        logger.warning(f"Error editing file {path}: {str(e)}")
        raise
    except Exception as e:
        # Log and wrap other exceptions
        logger.error(f"Error editing file {path}: {str(e)}")
        raise IOError(f"Error editing file: {str(e)}")


def copy(source_path: str, destination_path: str) -> Dict[str, Any]:
    """
    Copy a file or directory.

    Args:
        source_path: Source path
        destination_path: Destination path

    Returns:
        Dict with operation results

    Raises:
        PermissionError: If path is outside allowed directories
        FileNotFoundError: If source doesn't exist
        FileExistsError: If destination exists
        IOError: If copy fails
    """
    try:
        # Validate paths
        src_path = validate_path(source_path, must_exist=True)
        dst_path = validate_path(destination_path)

        # Check if source is a file or directory
        is_dir = os.path.isdir(src_path)

        # Check if destination exists
        if os.path.exists(dst_path):
            raise FileExistsError(f"Destination already exists: {destination_path}")

        # Create parent directory if needed
        create_parent_directory(dst_path)

        # Copy file or directory
        if is_dir:
            shutil.copytree(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)

        return {
            "source": source_path,
            "destination": destination_path,
            "operation": "copy",
            "status": "success",
            "type": "directory" if is_dir else "file",
        }
    except (PermissionError, FileNotFoundError, FileExistsError) as e:
        # Re-raise known exceptions
        logger.warning(f"Error copying {source_path} to {destination_path}: {str(e)}")
        raise
    except Exception as e:
        # Log and wrap other exceptions
        logger.error(f"Error copying {source_path} to {destination_path}: {str(e)}")
        raise IOError(f"Error copying: {str(e)}")


def delete(path: str) -> Dict[str, Any]:
    """
    Delete a file or directory.

    Args:
        path: Path to delete

    Returns:
        Dict with operation results

    Raises:
        PermissionError: If path is outside allowed directories
        FileNotFoundError: If path doesn't exist
        IOError: If delete fails
    """
    try:
        # Validate path
        full_path = validate_path(path, must_exist=True)

        # Check if it's a file or directory
        is_dir = os.path.isdir(full_path)

        # Delete file or directory
        if is_dir:
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)

        return {
            "path": path,
            "operation": "delete",
            "status": "success",
            "type": "directory" if is_dir else "file",
        }
    except (PermissionError, FileNotFoundError) as e:
        # Re-raise known exceptions
        logger.warning(f"Error deleting {path}: {str(e)}")
        raise
    except Exception as e:
        # Log and wrap other exceptions
        logger.error(f"Error deleting {path}: {str(e)}")
        raise IOError(f"Error deleting: {str(e)}")


def list_directory(path: str = "") -> List[Dict[str, Any]]:
    """
    List the contents of a directory.

    Args:
        path: Directory path to list

    Returns:
        List of file and directory information

    Raises:
        PermissionError: If path is outside allowed directories
        FileNotFoundError: If directory doesn't exist
        ValueError: If path is not a directory
        IOError: If directory cannot be listed
    """
    try:
        # Special case for empty path - use first allowed directory
        if not path:
            from radbot.filesystem.security import get_allowed_directories

            allowed_dirs = get_allowed_directories()
            if not allowed_dirs:
                raise PermissionError("No allowed directories configured")
            path = allowed_dirs[0]

        # Validate path
        full_path = validate_path(path, must_exist=True)

        # Check if it's a directory
        if not os.path.isdir(full_path):
            raise ValueError(f"Path is not a directory: {path}")

        # List directory contents
        contents = []
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            is_dir = os.path.isdir(item_path)

            contents.append(
                {
                    "name": item,
                    "path": os.path.join(path, item),
                    "type": "[DIR]" if is_dir else "[FILE]",
                    "size": 0 if is_dir else os.path.getsize(item_path),
                }
            )

        return contents
    except (PermissionError, FileNotFoundError, ValueError) as e:
        # Re-raise known exceptions
        logger.warning(f"Error listing directory {path}: {str(e)}")
        raise
    except Exception as e:
        # Log and wrap other exceptions
        logger.error(f"Error listing directory {path}: {str(e)}")
        raise IOError(f"Error listing directory: {str(e)}")


def get_info(path: str) -> Dict[str, Any]:
    """
    Get detailed information about a file or directory.

    Args:
        path: Path to get information for

    Returns:
        Dict with file or directory metadata

    Raises:
        PermissionError: If path is outside allowed directories
        FileNotFoundError: If path doesn't exist
        IOError: If information cannot be retrieved
    """
    try:
        # Validate path
        full_path = validate_path(path, must_exist=True)

        # Get file stat info
        stat_info = os.stat(full_path)
        is_dir = os.path.isdir(full_path)

        # Format the information
        info = {
            "path": path,
            "name": os.path.basename(full_path),
            "type": "directory" if is_dir else "file",
            "size": stat_info.st_size,
            "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            "accessed": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
            "permissions": stat_info.st_mode & 0o777,
        }

        return info
    except (PermissionError, FileNotFoundError) as e:
        # Re-raise known exceptions
        logger.warning(f"Error getting info for {path}: {str(e)}")
        raise
    except Exception as e:
        # Log and wrap other exceptions
        logger.error(f"Error getting info for {path}: {str(e)}")
        raise IOError(f"Error getting file info: {str(e)}")


def search(
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

    Raises:
        PermissionError: If path is outside allowed directories
        FileNotFoundError: If base path doesn't exist
        ValueError: If path is not a directory
        IOError: If search fails
    """
    exclude_patterns = exclude_patterns or []
    results = []

    try:
        # Validate path
        full_path = validate_path(path, must_exist=True)

        # Check if it's a directory
        if not os.path.isdir(full_path):
            raise ValueError(f"Path is not a directory: {path}")

        # Walk the directory tree
        for root, dirs, files in os.walk(full_path):
            # Filter directories to exclude
            dirs[:] = [
                d
                for d in dirs
                if not any(fnmatch.fnmatch(d, p) for p in exclude_patterns)
            ]

            # Check files
            for name in files:
                if fnmatch.fnmatch(name, pattern) and not any(
                    fnmatch.fnmatch(name, p) for p in exclude_patterns
                ):
                    file_path = os.path.join(root, name)
                    # Get path relative to the search path
                    rel_path = os.path.relpath(file_path, full_path)
                    results.append(
                        {
                            "name": name,
                            "path": os.path.join(path, rel_path),
                            "type": "[FILE]",
                            "size": os.path.getsize(file_path),
                        }
                    )

            # Check directories
            for name in dirs:
                if fnmatch.fnmatch(name, pattern) and not any(
                    fnmatch.fnmatch(name, p) for p in exclude_patterns
                ):
                    dir_path = os.path.join(root, name)
                    # Get path relative to the search path
                    rel_path = os.path.relpath(dir_path, full_path)
                    results.append(
                        {
                            "name": name,
                            "path": os.path.join(path, rel_path),
                            "type": "[DIR]",
                            "size": 0,
                        }
                    )

        return results
    except (PermissionError, FileNotFoundError, ValueError) as e:
        # Re-raise known exceptions
        logger.warning(f"Error searching in {path} for {pattern}: {str(e)}")
        raise
    except Exception as e:
        # Log and wrap other exceptions
        logger.error(f"Error searching in {path} for {pattern}: {str(e)}")
        raise IOError(f"Error searching: {str(e)}")
