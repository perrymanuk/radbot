"""Base toolset module for specialized agents.

This module provides the foundation for creating and managing specialized toolsets
for different agent types. It includes registration and retrieval mechanisms for
toolsets to support the specialized agent architecture.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Registry to store all available toolsets
_TOOLSET_REGISTRY: Dict[str, Callable[[], List[Any]]] = {}
_TOOLSET_DESCRIPTIONS: Dict[str, str] = {}
_TRANSFER_TARGETS: Dict[str, Set[str]] = {}


def register_toolset(
    name: str,
    toolset_func: Callable[[], List[Any]],
    description: str,
    allowed_transfers: Optional[List[str]] = None,
) -> None:
    """Register a specialized toolset with the system.

    Args:
        name: Unique identifier for the toolset
        toolset_func: Function that creates and returns the toolset
        description: Human-readable description of the toolset's purpose
        allowed_transfers: Optional list of specialized agent names this agent can transfer to
    """
    if name in _TOOLSET_REGISTRY:
        logger.warning(f"Overwriting existing toolset '{name}'")

    _TOOLSET_REGISTRY[name] = toolset_func
    _TOOLSET_DESCRIPTIONS[name] = description

    if allowed_transfers:
        _TRANSFER_TARGETS[name] = set(allowed_transfers)
    else:
        _TRANSFER_TARGETS[name] = set()

    logger.info(f"Registered toolset '{name}' with description: {description}")
    if allowed_transfers:
        logger.info(f"Toolset '{name}' can transfer to: {', '.join(allowed_transfers)}")


def get_toolset(name: str) -> List[Any]:
    """Get a specialized toolset by name.

    Args:
        name: Name of the toolset to retrieve

    Returns:
        List of tools for the requested specialization

    Raises:
        ValueError: If the requested toolset doesn't exist
    """
    if name not in _TOOLSET_REGISTRY:
        raise ValueError(f"Unknown toolset: {name}")

    try:
        return _TOOLSET_REGISTRY[name]()
    except Exception as e:
        logger.error(f"Error creating toolset '{name}': {e}")
        raise


def get_toolset_description(name: str) -> str:
    """Get the description for a specialized toolset.

    Args:
        name: Name of the toolset

    Returns:
        Human-readable description of the toolset

    Raises:
        ValueError: If the requested toolset doesn't exist
    """
    if name not in _TOOLSET_DESCRIPTIONS:
        raise ValueError(f"Unknown toolset: {name}")

    return _TOOLSET_DESCRIPTIONS[name]


def get_all_toolsets() -> Dict[str, Dict[str, Any]]:
    """Get all registered toolsets with their descriptions.

    Returns:
        Dictionary mapping toolset names to their information
    """
    return {
        name: {
            "description": _TOOLSET_DESCRIPTIONS.get(name, ""),
            "allowed_transfers": list(_TRANSFER_TARGETS.get(name, set())),
        }
        for name in _TOOLSET_REGISTRY
    }


def get_allowed_transfers(name: str) -> List[str]:
    """Get the list of allowed transfer targets for a toolset.

    Args:
        name: Name of the toolset

    Returns:
        List of specialized agent names this agent can transfer to

    Raises:
        ValueError: If the requested toolset doesn't exist
    """
    if name not in _TRANSFER_TARGETS:
        raise ValueError(f"Unknown toolset: {name}")

    return list(_TRANSFER_TARGETS[name])


def create_specialized_toolset(name: str) -> List[Any]:
    """Create a specialized toolset by name.

    This is a convenience function that wraps get_toolset() and adds any
    tools that all specialized agents should have (like transfer_to_agent).

    Args:
        name: Name of the toolset to create

    Returns:
        List of tools for the requested specialization, including common tools

    Raises:
        ValueError: If the requested toolset doesn't exist
    """
    tools = get_toolset(name)

    # TODO: Add transfer_to_agent tool to all specialized toolsets
    # We'll implement this when we create the TransferController

    return tools
