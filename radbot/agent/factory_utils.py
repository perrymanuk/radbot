"""Shared utilities for agent factory modules."""

import importlib
import logging
from typing import List

from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)


def load_tools(
    module_path: str,
    attr_name: str,
    agent_name: str,
    label: str,
) -> List[FunctionTool]:
    """Import a tools list from a module, logging success or failure.

    Args:
        module_path: Dotted module path (e.g., "radbot.tools.overseerr").
        attr_name: Attribute name on the module (e.g., "OVERSEERR_TOOLS").
        agent_name: Agent name for log messages.
        label: Human-readable tool group label (e.g., "Overseerr").

    Returns:
        The imported tools list, or an empty list on failure.
    """
    try:
        module = importlib.import_module(module_path)
        tools = getattr(module, attr_name)
        logger.info("Added %d %s tools to %s", len(tools), label, agent_name)
        return list(tools)
    except Exception as e:
        logger.warning("Failed to add %s tools to %s: %s", label, agent_name, e)
        return []
