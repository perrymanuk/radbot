"""Shared client utilities for singleton management and tool helpers."""

import logging
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def client_or_error(
    get_client_fn: Callable[[], Optional[T]],
    service_name: str,
) -> Tuple[Optional[T], Optional[Dict[str, Any]]]:
    """Return ``(client, None)`` or ``(None, error_dict)``.

    Replaces the duplicated ``_client_or_error()`` helpers found in every
    tool module.

    Args:
        get_client_fn: Callable that returns the client instance or ``None``.
        service_name: Human-readable service name for error messages.

    Returns:
        Tuple of ``(client, None)`` on success or ``(None, error_dict)``
        on failure.
    """
    client = get_client_fn()
    if client is None:
        return None, {
            "status": "error",
            "message": (
                f"{service_name} is not configured. "
                f"Set integrations.{service_name.lower().replace(' ', '_')} "
                f"in the admin UI or set the appropriate environment variables."
            ),
        }
    return client, None
