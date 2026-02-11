"""
Adapter for transitioning from MCP fileserver to direct filesystem implementation.

This module maintains backward compatibility with the MCP fileserver API while
using the new direct filesystem implementation internally.
"""

import logging
import os
from typing import List, Optional

from google.adk.tools import FunctionTool

# Import the direct filesystem implementation
from radbot.filesystem.adapter import (
    create_fileserver_toolset as direct_create_fileserver_toolset,
)

logger = logging.getLogger(__name__)


def create_fileserver_toolset() -> List[FunctionTool]:
    """
    Create filesystem tools using the direct implementation.

    This function maintains backward compatibility with the MCP fileserver client API
    but uses the new direct filesystem implementation internally.

    Returns:
        List of FunctionTool instances
    """
    logger.info("Creating filesystem tools using direct implementation")

    try:
        # Call the direct implementation
        tools = direct_create_fileserver_toolset()

        if tools:
            tool_names = [getattr(tool, "name", str(tool)) for tool in tools]
            logger.info(
                f"Successfully created {len(tools)} filesystem tools: {', '.join(tool_names)}"
            )
        else:
            logger.warning("No filesystem tools created")

        return tools
    except Exception as e:
        logger.error(f"Error creating filesystem tools: {e}")
        return []


async def create_fileserver_toolset_async():
    """
    Create filesystem tools asynchronously using the direct implementation.

    This function maintains backward compatibility with the MCP fileserver client API
    but uses the new direct filesystem implementation internally.

    Returns:
        Tuple of (List[FunctionTool], None) - no exit stack is needed with direct implementation
    """
    logger.info("Creating filesystem tools asynchronously using direct implementation")

    try:
        # Call the synchronous implementation for now since no async is needed
        tools = create_fileserver_toolset()

        # Return the tools and None for the exit stack (which is not needed for direct implementation)
        return tools, None
    except Exception as e:
        logger.error(f"Error creating filesystem tools asynchronously: {e}")
        return [], None
