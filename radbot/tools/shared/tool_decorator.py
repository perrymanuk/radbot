"""Shared decorator for tool function error handling."""

import functools
import logging
import traceback
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


def tool_error_handler(operation_name: str) -> Callable:
    """Decorator that wraps tool functions with consistent error handling.

    Catches exceptions and returns a standardised error dict.

    Args:
        operation_name: Human-readable name for the operation
                        (used in error messages).

    Usage::

        @tool_error_handler("search media")
        def search_overseerr_media(query: str) -> dict:
            ...
    """

    def decorator(
        func: Callable[..., Dict[str, Any]],
    ) -> Callable[..., Dict[str, Any]]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Dict[str, Any]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                msg = f"Failed to {operation_name}: {e}"
                logger.error(msg)
                logger.debug(traceback.format_exc())
                return {"status": "error", "message": msg[:300]}

        return wrapper

    return decorator
