"""Shared error-handling helpers for agent tools."""


def truncate_error(message: str, max_length: int = 200) -> str:
    """Truncate an error message if it exceeds *max_length*."""
    if len(message) <= max_length:
        return message
    return message[: max_length - 3] + "..."
