"""
Enhanced memory system for radbot.

This package implements the memory system upgrade described in the design document,
providing a multi-layered memory system with different resolutions and custom tagging.
"""

from radbot.memory.enhanced_memory.memory_detector import (
    MemoryDetector,
    get_memory_detector,
)
from radbot.memory.enhanced_memory.memory_manager import (
    EnhancedMemoryManager,
    create_enhanced_memory_manager,
)

__all__ = [
    "MemoryDetector",
    "get_memory_detector",
    "EnhancedMemoryManager",
    "create_enhanced_memory_manager",
]
