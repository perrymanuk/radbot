"""
Adapter for compatibility with the previous MCP fileserver implementation.

This module provides functions that maintain compatibility with code
that was using the previous MCP fileserver implementation.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from radbot.filesystem.integration import create_filesystem_tools

logger = logging.getLogger(__name__)


def get_filesystem_config() -> tuple[str, bool, bool, List[str]]:
    """
    Get the filesystem configuration from YAML config.

    Reads filesystem configuration directly from the YAML config file.

    Returns:
        Tuple of (root_dir, allow_write, allow_delete, allowed_directories)
    """
    allowed_directories: List[str] = []
    try:
        from radbot.config.config_loader import config_loader

        fs_config = config_loader.get_integrations_config().get("filesystem", {})

        # Read settings from config
        root_dir = fs_config.get("root_dir", os.path.expanduser("~"))
        allow_write = fs_config.get("allow_write", False)
        allow_delete = fs_config.get("allow_delete", False)
        allowed_directories = fs_config.get("allowed_directories", [])

        # Set environment variables for compatibility with components that might still use them
        os.environ["MCP_FS_ROOT_DIR"] = root_dir
        os.environ["MCP_FS_ALLOW_WRITE"] = "true" if allow_write else "false"
        os.environ["MCP_FS_ALLOW_DELETE"] = "true" if allow_delete else "false"
    except Exception as e:
        # If config loading fails, use reasonable defaults
        logger.error(f"Error loading filesystem config: {e}")
        root_dir = os.path.expanduser("~")
        allow_write = False
        allow_delete = False

    logger.info(
        f"Filesystem Config: root_dir={root_dir}, allow_write={allow_write}, "
        f"allow_delete={allow_delete}, allowed_directories={allowed_directories}"
    )

    return root_dir, allow_write, allow_delete, allowed_directories


def _get_workspace_dir() -> Optional[str]:
    """Get the Claude Code workspace directory if configured."""
    try:
        from radbot.tools.claude_code.claude_code_tools import (
            _get_workspace_dir as get_ws_dir,
        )

        ws_dir = get_ws_dir()
        if ws_dir and os.path.isabs(ws_dir):
            return ws_dir
    except Exception:
        pass
    return None


def reload_filesystem_config() -> None:
    """
    Reload filesystem security config from the current config state.

    Called by the admin API when filesystem config is updated via the UI,
    so that allowed directories take effect without a restart.
    """
    from radbot.filesystem.security import set_allowed_directories

    root_dir, allow_write, allow_delete, extra_dirs = get_filesystem_config()
    all_dirs = [root_dir] + [d for d in extra_dirs if d and d != root_dir]

    # Include workspace directory automatically
    ws_dir = _get_workspace_dir()
    if ws_dir and ws_dir not in all_dirs:
        all_dirs.append(ws_dir)

    set_allowed_directories(all_dirs)
    logger.info(f"Reloaded filesystem config: allowed_directories={all_dirs}")


def create_fileserver_toolset() -> List[FunctionTool]:
    """
    Create the filesystem tools using previous MCP fileserver environment variables.

    This function maintains compatibility with code that was using the
    previous MCP fileserver implementation.

    Returns:
        List of FunctionTool instances
    """
    root_dir, allow_write, allow_delete, extra_dirs = get_filesystem_config()

    # Build the full list of allowed directories
    all_dirs = [root_dir] + [d for d in extra_dirs if d and d != root_dir]

    # Automatically include the Claude Code workspace directory so that
    # filesystem tools can access cloned repositories without manual config.
    ws_dir = _get_workspace_dir()
    if ws_dir and ws_dir not in all_dirs:
        all_dirs.append(ws_dir)

    logger.info(
        f"Creating filesystem tools with allowed_directories={all_dirs}, "
        f"allow_write={allow_write}, allow_delete={allow_delete}"
    )

    # Create the tools with the configured directories and permissions
    return create_filesystem_tools(
        allowed_directories=all_dirs,
        enable_write=allow_write,
        enable_delete=allow_delete,
    )
