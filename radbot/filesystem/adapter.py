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


def get_filesystem_config() -> tuple[str, bool, bool]:
    """
    Get the filesystem configuration from YAML config.

    Reads filesystem configuration directly from the YAML config file.

    Returns:
        Tuple of (root_dir, allow_write, allow_delete)
    """
    try:
        from radbot.config.config_loader import config_loader

        fs_config = config_loader.get_integrations_config().get("filesystem", {})

        # Read settings from config
        root_dir = fs_config.get("root_dir", os.path.expanduser("~"))
        allow_write = fs_config.get("allow_write", False)
        allow_delete = fs_config.get("allow_delete", False)

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
        f"Filesystem Config: root_dir={root_dir}, allow_write={allow_write}, allow_delete={allow_delete}"
    )

    return root_dir, allow_write, allow_delete


def create_fileserver_toolset() -> List[FunctionTool]:
    """
    Create the filesystem tools using previous MCP fileserver environment variables.

    This function maintains compatibility with code that was using the
    previous MCP fileserver implementation.

    Returns:
        List of FunctionTool instances
    """
    root_dir, allow_write, allow_delete = get_filesystem_config()

    logger.info(
        f"Creating filesystem tools with root_dir={root_dir}, "
        f"allow_write={allow_write}, allow_delete={allow_delete}"
    )

    # Create the tools with the configured directories and permissions
    return create_filesystem_tools(
        allowed_directories=[root_dir],
        enable_write=allow_write,
        enable_delete=allow_delete,
    )
