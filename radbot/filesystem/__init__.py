"""
Filesystem access functionality for Python ADK.

This module provides direct filesystem access capabilities integrated into
the Python Agent Development Kit (ADK), allowing agents to interact with
the local filesystem without requiring external processes or servers.
"""

from radbot.filesystem.security import get_allowed_directories, set_allowed_directories
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

__all__ = [
    "read_file",
    "write_file",
    "edit_file",
    "copy",
    "delete",
    "list_directory",
    "get_info",
    "search",
    "set_allowed_directories",
    "get_allowed_directories",
]
