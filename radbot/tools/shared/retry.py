"""Retry decorator for transient failures."""

import functools
import logging
import time
from typing import Callable, Tuple, Type

logger = logging.getLogger(__name__)


def retry_on_error(
    max_retries: int = 3,
    backoff_base: float = 1.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    ),
) -> Callable:
    """Decorator that retries a function on transient errors with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (in addition to the
                     initial call).
        backoff_base: Base delay in seconds (doubles each retry).
        retryable_exceptions: Tuple of exception types that trigger a retry.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = backoff_base * (2**attempt)
                        logger.warning(
                            "%s failed (attempt %d/%d), retrying in %.1fs: %s",
                            func.__name__,
                            attempt + 1,
                            max_retries + 1,
                            delay,
                            e,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__,
                            max_retries + 1,
                            e,
                        )
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator
