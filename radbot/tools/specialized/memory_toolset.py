"""Memory toolset for specialized agents.

This module provides tools for managing conversation history,
searching past conversations, and working with the knowledge base.
"""

import logging
from typing import List, Any, Optional

# Import memory tools
try:
    from radbot.tools.memory.memory_tools import (
        search_past_conversations,
        store_important_information
    )
except ImportError:
    # Define placeholder if not available
    search_past_conversations = None
    store_important_information = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)

def create_memory_toolset() -> List[Any]:
    """Create the set of tools for the memory specialized agent.
    
    Returns:
        List of tools for memory management and information retrieval
    """
    toolset = []
    
    # Add basic memory search tool
    if search_past_conversations:
        try:
            toolset.append(search_past_conversations)
            logger.info("Added search_past_conversations to memory toolset")
        except Exception as e:
            logger.error(f"Failed to add search_past_conversations: {e}")
    
    # Add store information tool
    if store_important_information:
        try:
            toolset.append(store_important_information)
            logger.info("Added store_important_information to memory toolset")
        except Exception as e:
            logger.error(f"Failed to add store_important_information: {e}")
    
    return toolset

# Register the toolset with the system
register_toolset(
    name="memory",
    toolset_func=create_memory_toolset,
    description="Agent specialized in memory management and information retrieval",
    allowed_transfers=[]  # Only allows transfer back to main orchestrator
)