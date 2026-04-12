"""Kideo tools for adding curated videos to the kids video library.

Provides FunctionTool-wrapped functions for submitting YouTube videos
to Kideo, managing collections, and checking video status.
"""

import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

from radbot.tools.shared.tool_decorator import tool_error_handler

logger = logging.getLogger(__name__)


@tool_error_handler("add video to Kideo")
def add_video_to_kideo(
    url: str,
    collection_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a YouTube video to the Kideo kids video library for safe offline viewing.

    Kideo downloads and transcodes the video so children can watch it in a
    safe, ad-free player without access to YouTube directly.

    Args:
        url: The full YouTube video URL (e.g. "https://www.youtube.com/watch?v=abc123").
        collection_id: Optional Kideo collection UUID to organize the video into.
            Use list_kideo_collections to find existing collections first.

    Returns:
        On success: {"status": "success", "video": {...}} with video id, title, processing status.
        On failure: {"status": "error", "message": "..."}
    """
    logger.info(f"Adding video to Kideo: {url}")
    from radbot.tools.youtube.kideo_client import add_video

    result = add_video(url=url, collection_id=collection_id)
    return {
        "status": "success",
        "video": result,
        "message": f"Video '{result.get('title', url)}' added to Kideo (status: {result.get('status', 'pending')})",
    }


@tool_error_handler("batch add videos to Kideo")
def add_videos_to_kideo_batch(
    urls: List[str],
    collection_id: str,
) -> Dict[str, Any]:
    """Add multiple YouTube videos to a Kideo collection at once.

    Use this when adding several videos from a search to a collection.
    More efficient than adding one at a time.

    Args:
        urls: List of YouTube video URLs to add.
        collection_id: The Kideo collection UUID to add all videos to.
            Use list_kideo_collections to find existing collections.

    Returns:
        On success: {"status": "success", "results": [...]} with per-video status.
        On failure: {"status": "error", "message": "..."}
    """
    logger.info(f"Batch adding {len(urls)} videos to Kideo collection {collection_id}")
    from radbot.tools.youtube.kideo_client import add_videos_batch

    results = add_videos_batch(urls=urls, collection_id=collection_id)
    queued = sum(1 for r in results if r.get("status") == "queued")
    existing = sum(1 for r in results if r.get("status") == "existing")
    return {
        "status": "success",
        "results": results,
        "message": f"Added {queued} new videos, {existing} already existed",
    }


@tool_error_handler("list Kideo collections")
def list_kideo_collections() -> Dict[str, Any]:
    """List all video collections in Kideo.

    Use this to find the right collection ID before adding videos.
    Collections organize videos by topic or child.

    Returns:
        On success: {"status": "success", "collections": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    from radbot.tools.youtube.kideo_client import list_collections

    collections = list_collections()
    return {
        "status": "success",
        "collections": collections,
        "count": len(collections),
    }


@tool_error_handler("create Kideo collection")
def create_kideo_collection(
    name: str,
    color: str = "#4F46E5",
    icon: str = "star",
) -> Dict[str, Any]:
    """Create a new video collection in Kideo.

    Use this to organize videos by topic (e.g. "Dinosaurs for Leon",
    "Space Science", "Art Projects").

    Args:
        name: Collection name (e.g. "Dinosaur Videos").
        color: Hex color for the collection card (default "#4F46E5" indigo).
        icon: Icon name for the collection (default "star").

    Returns:
        On success: {"status": "success", "collection": {...}} with the new collection details.
        On failure: {"status": "error", "message": "..."}
    """
    logger.info(f"Creating Kideo collection: {name}")
    from radbot.tools.youtube.kideo_client import create_collection

    result = create_collection(name=name, color=color, icon=icon)
    return {
        "status": "success",
        "collection": result,
        "message": f"Collection '{name}' created",
    }


@tool_error_handler("generate tags for video")
def generate_video_tags(
    video_id: str,
    title: str,
    description: str = "",
    channel_title: str = "",
) -> Dict[str, Any]:
    """Generate educational tags for a YouTube video using AI.

    Analyzes the video's title, description, and transcript (fetched automatically)
    to produce relevant categorization tags like "dinosaurs", "crafting",
    "outer space", "math", etc. Uses a small fast model for efficiency.

    Call this BEFORE or AFTER adding a video to Kideo. The generated tags
    can then be applied with set_kideo_video_tags.

    Args:
        video_id: The YouTube video ID (the part after "v=" in the URL).
        title: The video title.
        description: The video description (from YouTube search or details).
        channel_title: The channel name.

    Returns:
        On success: {"status": "success", "tags": ["tag1", "tag2", ...]}
        On failure: {"status": "error", "message": "..."}
    """
    logger.info(f"Generating tags for video '{title}' ({video_id})")
    from radbot.tools.youtube.tag_generator import generate_tags_for_video

    tags = generate_tags_for_video(
        {
            "video_id": video_id,
            "title": title,
            "description": description,
            "channel_title": channel_title,
        }
    )
    return {
        "status": "success",
        "tags": tags,
        "count": len(tags),
        "message": f"Generated {len(tags)} tags: {', '.join(tags)}" if tags else "No tags generated",
    }


@tool_error_handler("set tags on Kideo video")
def set_kideo_video_tags(
    video_id: str,
    tags: List[str],
) -> Dict[str, Any]:
    """Set tags on a video in Kideo.

    Use this after adding a video to Kideo and generating tags.
    The video_id here is the Kideo video UUID (returned when adding),
    NOT the YouTube video ID.

    Args:
        video_id: The Kideo video UUID (from add_video_to_kideo response).
        tags: List of tag strings to apply (e.g. ["dinosaurs", "science", "paleontology"]).

    Returns:
        On success: {"status": "success", "video": {...}} with updated video.
        On failure: {"status": "error", "message": "..."}
    """
    logger.info(f"Setting {len(tags)} tags on Kideo video {video_id}")
    from radbot.tools.youtube.kideo_client import set_video_tags

    result = set_video_tags(video_id=video_id, tags=tags)
    return {
        "status": "success",
        "video": result,
        "message": f"Applied {len(tags)} tags to video",
    }


@tool_error_handler("get popular videos from Kideo")
def get_kideo_popular_videos(
    collection_id: str,
    limit: int = 20,
    days: Optional[int] = None,
) -> Dict[str, Any]:
    """Get the most-played videos in a Kideo collection.

    Use this to understand what content the children are enjoying most.
    Results are ranked by play count and include tags.

    Args:
        collection_id: The Kideo collection UUID.
        limit: Maximum number of results (default 20).
        days: Optional time window — only count plays from the last N days.

    Returns:
        On success: {"status": "success", "videos": [...]} with id, title, url, play_count, tags.
        On failure: {"status": "error", "message": "..."}
    """
    from radbot.tools.youtube.kideo_client import get_popular_videos

    videos = get_popular_videos(
        collection_id=collection_id, limit=limit, days=days
    )
    return {
        "status": "success",
        "videos": videos,
        "count": len(videos),
    }


@tool_error_handler("get popular tags from Kideo")
def get_kideo_tag_stats(
    collection_id: str,
    days: Optional[int] = None,
) -> Dict[str, Any]:
    """Get the most popular tags in a Kideo collection ranked by play count.

    Use this to discover what topics and categories children enjoy most,
    then search YouTube for more content matching those popular tags.

    Args:
        collection_id: The Kideo collection UUID.
        days: Optional time window — only count plays from the last N days.

    Returns:
        On success: {"status": "success", "tag_stats": [...]} with tag, play_count, video_count.
        On failure: {"status": "error", "message": "..."}
    """
    from radbot.tools.youtube.kideo_client import get_tag_stats

    stats = get_tag_stats(collection_id=collection_id, days=days)
    return {
        "status": "success",
        "tag_stats": stats,
        "count": len(stats),
    }


@tool_error_handler("get popular channels from Kideo")
def get_kideo_channel_stats(
    collection_id: str,
    days: Optional[int] = None,
) -> Dict[str, Any]:
    """Get the most popular YouTube channels in a Kideo collection ranked by play count.

    Use this to discover which channels produce content the children enjoy,
    then search those channels for new videos to add.

    Args:
        collection_id: The Kideo collection UUID.
        days: Optional time window — only count plays from the last N days.

    Returns:
        On success: {"status": "success", "channel_stats": [...]} with channel_name, play_count, video_count.
        On failure: {"status": "error", "message": "..."}
    """
    from radbot.tools.youtube.kideo_client import get_channel_stats

    stats = get_channel_stats(collection_id=collection_id, days=days)
    return {
        "status": "success",
        "channel_stats": stats,
        "count": len(stats),
    }


@tool_error_handler("retag untagged Kideo videos")
def retag_untagged_kideo_videos() -> Dict[str, Any]:
    """Find all videos in Kideo that have no tags and generate tags for them.

    Fetches all ready videos, filters to those with empty tags, then uses
    AI to generate tags from each video's title and channel name.
    Automatically applies the generated tags.

    Returns:
        On success: {"status": "success", "tagged_count": N, "results": [...]}
        On failure: {"status": "error", "message": "..."}
    """
    from radbot.tools.youtube.kideo_client import list_videos, set_video_tags
    from radbot.tools.youtube.tag_generator import generate_tags

    videos = list_videos(status="ready")
    untagged = [v for v in videos if not v.get("tags")]

    if not untagged:
        return {
            "status": "success",
            "tagged_count": 0,
            "message": "All videos already have tags",
        }

    results = []
    for video in untagged:
        title = video.get("title", "")
        # Extract YouTube video ID from URL for transcript fetching
        url = video.get("url", "")
        yt_video_id = ""
        if "v=" in url:
            yt_video_id = url.split("v=")[1].split("&")[0]

        # Generate tags using title, channel, and optionally transcript
        from radbot.tools.youtube.tag_generator import (
            fetch_transcript,
            generate_tags as _generate_tags,
        )

        transcript = fetch_transcript(yt_video_id) if yt_video_id else None
        tags = _generate_tags(
            title=title,
            description=video.get("description", ""),
            transcript=transcript,
            channel_title=video.get("channel_name", ""),
        )

        if tags:
            set_video_tags(video_id=str(video["id"]), tags=tags)
            results.append(
                {
                    "video_id": str(video["id"]),
                    "title": title,
                    "tags": tags,
                }
            )
            logger.info(f"Tagged '{title}' with: {tags}")

    return {
        "status": "success",
        "tagged_count": len(results),
        "total_untagged": len(untagged),
        "results": results,
        "message": f"Tagged {len(results)} of {len(untagged)} untagged videos",
    }


# Wrap as FunctionTools
add_video_to_kideo_tool = FunctionTool(add_video_to_kideo)
add_videos_to_kideo_batch_tool = FunctionTool(add_videos_to_kideo_batch)
list_kideo_collections_tool = FunctionTool(list_kideo_collections)
create_kideo_collection_tool = FunctionTool(create_kideo_collection)
generate_video_tags_tool = FunctionTool(generate_video_tags)
set_kideo_video_tags_tool = FunctionTool(set_kideo_video_tags)
get_kideo_popular_videos_tool = FunctionTool(get_kideo_popular_videos)
get_kideo_tag_stats_tool = FunctionTool(get_kideo_tag_stats)
get_kideo_channel_stats_tool = FunctionTool(get_kideo_channel_stats)
retag_untagged_kideo_videos_tool = FunctionTool(retag_untagged_kideo_videos)

KIDEO_TOOLS = [
    add_video_to_kideo_tool,
    add_videos_to_kideo_batch_tool,
    list_kideo_collections_tool,
    create_kideo_collection_tool,
    generate_video_tags_tool,
    set_kideo_video_tags_tool,
    get_kideo_popular_videos_tool,
    get_kideo_tag_stats_tool,
    get_kideo_channel_stats_tool,
    retag_untagged_kideo_videos_tool,
]
