"""
Serialization utilities for RadBot web interface.

This module provides serialization utilities for the session management.
"""

import json
import logging
from typing import Any

# Set up logging
logger = logging.getLogger(__name__)


def _safely_serialize(obj):
    """Safely serialize objects to JSON-compatible structures."""
    import json

    try:
        # Try direct JSON serialization
        json.dumps(obj)
        return obj
    except (TypeError, OverflowError, ValueError):
        # If that fails, try converting to string
        try:
            if hasattr(obj, "__dict__"):
                return str(obj.__dict__)
            elif hasattr(obj, "to_dict"):
                return str(obj.to_dict())
            else:
                return str(obj)
        except:
            return f"<Unserializable object of type {type(obj).__name__}>"
