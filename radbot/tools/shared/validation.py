"""Shared validation helpers for agent tool inputs."""

import uuid
from typing import Any, Dict, Optional, Tuple


def validate_uuid(
    value: str, field_name: str = "ID"
) -> Tuple[Optional[uuid.UUID], Optional[Dict[str, Any]]]:
    """Parse *value* as UUID.

    Returns (uuid, None) on success or (None, error_dict) on failure.

    Usage::

        parsed, err = validate_uuid(task_id, "task ID")
        if err:
            return err
    """
    try:
        return uuid.UUID(value), None
    except (ValueError, AttributeError):
        return None, {
            "status": "error",
            "message": (
                f"Invalid {field_name} format: {value}. " "Must be a valid UUID."
            ),
        }
