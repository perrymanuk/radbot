"""CuriosityStream search tools for the kids video curation agent.

Provides FunctionTool-wrapped functions for searching CuriosityStream's
documentary catalog, which includes high-quality educational content
for children.
"""

import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from radbot.tools.shared.tool_decorator import tool_error_handler

logger = logging.getLogger(__name__)


@tool_error_handler("search CuriosityStream videos")
def search_curiositystream(
    query: str,
    max_results: int = 10,
    kid_friendly_only: bool = True,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Search CuriosityStream for documentary and educational videos.

    CuriosityStream is a premium documentary streaming service with
    high-quality, professionally produced educational content. Great for
    science, nature, history, and technology topics.

    No API key needed — uses CuriosityStream's public search index.

    Args:
        query: Search terms (e.g. "dinosaurs", "solar system", "ancient egypt").
        max_results: Number of results to return (1-50, default 10).
        kid_friendly_only: Only return child-friendly content (default True).
            Always keep True when searching for children's content.
        categories: Optional list of categories to filter by.
            Available: "science", "history", "technology", "nature", "society",
            "kids", "biography", "earth", "prehistoric-creatures", "prehistory",
            "space", "engineering", "mathematics".

    Returns:
        On success: {"status": "success", "videos": [...], "total_results": N}
        On failure: {"status": "error", "message": "..."}
    """
    logger.info(
        f"Searching CuriosityStream: query='{query}', kid_friendly={kid_friendly_only}"
    )
    from radbot.tools.youtube.curiositystream_client import search_videos

    result = search_videos(
        query=query,
        max_results=max_results,
        kid_friendly_only=kid_friendly_only,
        categories=categories,
    )

    return {
        "status": "success",
        "videos": result["items"],
        "total_results": result["total_results"],
        "result_count": len(result["items"]),
        "source": "curiositystream",
    }


@tool_error_handler("list CuriosityStream categories")
def list_curiositystream_categories() -> Dict[str, Any]:
    """List all available CuriosityStream content categories.

    Use this to understand what topics are available on CuriosityStream
    before searching, or to browse by category.

    Returns:
        On success: {"status": "success", "categories": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    from radbot.tools.youtube.curiositystream_client import get_categories

    categories = get_categories()
    return {
        "status": "success",
        "categories": categories,
        "count": len(categories),
    }


# Wrap as FunctionTools
search_curiositystream_tool = FunctionTool(search_curiositystream)
list_curiositystream_categories_tool = FunctionTool(list_curiositystream_categories)

CURIOSITYSTREAM_TOOLS = [
    search_curiositystream_tool,
    list_curiositystream_categories_tool,
]
