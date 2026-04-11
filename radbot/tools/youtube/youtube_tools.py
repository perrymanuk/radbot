"""YouTube search tools for the kids video curation agent.

Provides FunctionTool-wrapped functions for searching YouTube,
getting video details, and checking channel info.
"""

import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from radbot.tools.shared.tool_decorator import tool_error_handler

logger = logging.getLogger(__name__)


@tool_error_handler("search YouTube videos")
def search_youtube_videos(
    query: str,
    max_results: int = 10,
    safe_search: str = "strict",
    video_duration: Optional[str] = None,
    order: str = "relevance",
    channel_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Search YouTube for videos with safety filtering.

    Args:
        query: Search terms (e.g. "dinosaur facts for kids").
        max_results: Number of results to return (1-50, default 10).
        safe_search: Safety filter level — always use "strict" for children's content.
            Options: "strict", "moderate", "none".
        video_duration: Filter by length — "short" (<4min), "medium" (4-20min), "long" (>20min).
            Leave empty for any duration.
        order: Sort order — "relevance" (default), "date", "rating", "viewCount".
        channel_id: Optional YouTube channel ID to restrict search to a specific channel.

    Returns:
        On success: {"status": "success", "videos": [...], "total_results": N}
        On failure: {"status": "error", "message": "..."}
    """
    logger.info(f"search_youtube_videos called with query='{query}', max_results={max_results}")
    from radbot.tools.youtube.youtube_client import search_videos

    result = search_videos(
        query=query,
        max_results=max_results,
        safe_search=safe_search,
        video_duration=video_duration,
        order=order,
        channel_id=channel_id,
    )

    return {
        "status": "success",
        "videos": result["items"],
        "total_results": result["total_results"],
        "result_count": len(result["items"]),
    }


@tool_error_handler("get YouTube video details")
def get_youtube_video_details(
    video_ids: List[str],
) -> Dict[str, Any]:
    """Get detailed information about specific YouTube videos.

    Use this to check duration, view counts, tags, and content ratings
    before recommending videos. Useful for verifying video suitability.

    Args:
        video_ids: List of YouTube video IDs to look up (max 50).
            Video IDs are the part after "v=" in YouTube URLs.

    Returns:
        On success: {"status": "success", "videos": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    from radbot.tools.youtube.youtube_client import get_video_details

    details = get_video_details(video_ids)

    return {
        "status": "success",
        "videos": details,
        "count": len(details),
    }


@tool_error_handler("get YouTube channel info")
def get_youtube_channel_info(
    channel_id: str,
) -> Dict[str, Any]:
    """Get information about a YouTube channel.

    Use this to verify a channel is trustworthy and appropriate
    for children before recommending its content.

    Args:
        channel_id: The YouTube channel ID to look up.

    Returns:
        On success: {"status": "success", "channel": {...}}
        On failure: {"status": "error", "message": "..."}
    """
    from radbot.tools.youtube.youtube_client import get_channel_info

    info = get_channel_info(channel_id)
    if info is None:
        return {"status": "error", "message": f"Channel {channel_id} not found"}

    return {
        "status": "success",
        "channel": info,
    }


# Wrap as FunctionTools
search_youtube_videos_tool = FunctionTool(search_youtube_videos)
get_youtube_video_details_tool = FunctionTool(get_youtube_video_details)
get_youtube_channel_info_tool = FunctionTool(get_youtube_channel_info)

YOUTUBE_TOOLS = [
    search_youtube_videos_tool,
    get_youtube_video_details_tool,
    get_youtube_channel_info_tool,
]
