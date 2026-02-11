"""
Security layer for filesystem operations.

This module provides security validation for all filesystem operations,
ensuring that paths are safely within allowed directories.
"""

import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

# Global configuration
_ALLOWED_DIRECTORIES: List[str] = []


def set_allowed_directories(directories: List[str]) -> None:
    """
    Configure the list of allowed directories for filesystem operations.

    All filesystem operations will be restricted to these directories.
    Paths must be absolute and will be normalized.

    Args:
        directories: List of allowed directory paths
    """
    global _ALLOWED_DIRECTORIES
    _ALLOWED_DIRECTORIES = [os.path.abspath(os.path.normpath(d)) for d in directories]
    logger.info(
        f"Filesystem security: Set allowed directories to {_ALLOWED_DIRECTORIES}"
    )


def get_allowed_directories() -> List[str]:
    """
    Get the list of currently allowed directories.

    Returns:
        List of allowed directory paths
    """
    return _ALLOWED_DIRECTORIES.copy()


def validate_path(path: str, must_exist: bool = False) -> str:
    """
    Validate that a path is within an allowed directory.

    This function is a critical security function that prevents
    access to unauthorized parts of the filesystem.

    Args:
        path: Path to validate
        must_exist: If True, verify that the path exists

    Returns:
        Normalized absolute path

    Raises:
        PermissionError: If path is outside allowed directories
        FileNotFoundError: If must_exist is True and path doesn't exist
    """
    if not _ALLOWED_DIRECTORIES:
        logger.warning(
            "No allowed directories configured, blocking all filesystem access"
        )
        raise PermissionError(
            "Filesystem security error: No allowed directories configured"
        )

    # Convert to absolute path and resolve symlinks
    abs_path = os.path.abspath(os.path.normpath(path))
    real_path = os.path.realpath(abs_path)

    # Check if the path is within any allowed directory
    for allowed_dir in _ALLOWED_DIRECTORIES:
        if real_path.startswith(allowed_dir + os.sep) or real_path == allowed_dir:
            # Path is allowed
            if must_exist and not os.path.exists(real_path):
                logger.warning(f"Path not found: {path}")
                raise FileNotFoundError(f"Path not found: {path}")
            return real_path

    # Path is outside allowed directories
    logger.warning(
        f"Security violation: Attempted access to path outside allowed directories: {path}"
    )
    raise PermissionError(
        f"Filesystem security error: Path is outside allowed directories: {path}"
    )


def create_parent_directory(path: str) -> None:
    """
    Create the parent directory of a path if it doesn't exist.

    This function will create all necessary parent directories,
    but only if they are within allowed directories.

    Args:
        path: Path whose parent directory should be created

    Raises:
        PermissionError: If parent directory is outside allowed directories
    """
    parent_dir = os.path.dirname(path)

    # Validate parent directory is within allowed directories
    parent_dir = validate_path(parent_dir)

    # Create if it doesn't exist
    if not os.path.exists(parent_dir):
        logger.debug(f"Creating parent directory: {parent_dir}")
        os.makedirs(parent_dir, exist_ok=True)
