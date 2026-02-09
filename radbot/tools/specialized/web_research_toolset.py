"""Web research toolset for specialized agents.

This module provides tools for web searching, content retrieval,
and information extraction from online sources.
"""

import logging
from typing import List, Any, Optional

# Import web search tools
try:
    from radbot.tools.web_search.web_search_tools import create_tavily_search_tool
except ImportError:
    create_tavily_search_tool = None

# Import base toolset for registration
from .base_toolset import register_toolset

logger = logging.getLogger(__name__)

def create_web_research_toolset() -> List[Any]:
    """Create the set of tools for the web research specialized agent.

    Returns:
        List of tools for web search and information retrieval
    """
    toolset = []

    # Add basic web search tool
    if create_tavily_search_tool:
        try:
            search_tool = create_tavily_search_tool()
            if search_tool:
                toolset.append(search_tool)
                logger.info("Added web_search to web research toolset")
        except Exception as e:
            logger.error(f"Failed to add web_search: {e}")

    return toolset

# Register the toolset with the system
register_toolset(
    name="web_research",
    toolset_func=create_web_research_toolset,
    description="Agent specialized in web research and information retrieval",
    allowed_transfers=[]  # Scout can transfer to this agent, handled elsewhere
)
