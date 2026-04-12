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


# Wrap as FunctionTools
add_video_to_kideo_tool = FunctionTool(add_video_to_kideo)
add_videos_to_kideo_batch_tool = FunctionTool(add_videos_to_kideo_batch)
list_kideo_collections_tool = FunctionTool(list_kideo_collections)
create_kideo_collection_tool = FunctionTool(create_kideo_collection)
generate_video_tags_tool = FunctionTool(generate_video_tags)
set_kideo_video_tags_tool = FunctionTool(set_kideo_video_tags)

KIDEO_TOOLS = [
    add_video_to_kideo_tool,
    add_videos_to_kideo_batch_tool,
    list_kideo_collections_tool,
    create_kideo_collection_tool,
    generate_video_tags_tool,
    set_kideo_video_tags_tool,
]
