"""Specialized toolsets for different agent types.

This package contains modules that define toolsets for specialized agents,
focusing on specific domains to reduce token usage and improve performance.
"""

from typing import Any, Dict, List, Optional

# Export utility functions for specialized toolsets
from .base_toolset import (
    create_specialized_toolset,
    get_all_toolsets,
    get_toolset,
    register_toolset,
)
