"""YouTube Data API v3 client for video search.

Uses the google-api-python-client library (already installed for Calendar).
API key is resolved via the standard integration config pattern.
"""

import logging
from typing import Any, Dict, List, Optional

from radbot.tools.shared.config_helper import get_integration_config

logger = logging.getLogger(__name__)

_client = None


def _get_config() -> Dict[str, Any]:
    """Resolve YouTube API configuration."""
    return get_integration_config(
        "youtube",
        fields={"api_key": "YOUTUBE_API_KEY"},
        credential_keys={"api_key": "youtube_api_key"},
    )


def _get_client():
    """Get or create the YouTube API client singleton."""
    global _client
    if _client is not None:
        return _client

    config = _get_config()
    api_key = config.get("api_key")
    if not api_key:
        raise RuntimeError(
            "YouTube API key not configured. "
            "Set via Admin UI (config:integrations → youtube.api_key), "
            "credential store (youtube_api_key), or YOUTUBE_API_KEY env var."
        )

    from googleapiclient.discovery import build

    _client = build("youtube", "v3", developerKey=api_key)
    logger.info("YouTube API client initialized")
    return _client


def reset_youtube_client():
    """Reset the singleton client (for hot-reload)."""
    global _client
    _client = None
    logger.debug("YouTube client reset")


def search_videos(
    query: str,
    max_results: int = 10,
    safe_search: str = "strict",
    video_duration: Optional[str] = None,
    order: str = "relevance",
    published_after: Optional[str] = None,
    channel_id: Optional[str] = None,
    region_code: Optional[str] = None,
    relevance_language: Optional[str] = None,
) -> Dict[str, Any]:
    """Search YouTube videos via Data API v3.

    Args:
        query: Search query string.
        max_results: Number of results (1-50, default 10).
        safe_search: Safety level — "strict", "moderate", or "none".
        video_duration: Filter by duration — "short" (<4min), "medium" (4-20min), "long" (>20min).
        order: Sort order — "relevance", "date", "rating", "viewCount".
        published_after: ISO 8601 datetime (e.g. "2024-01-01T00:00:00Z").
        channel_id: Restrict to a specific channel.
        region_code: ISO 3166-1 alpha-2 country code.
        relevance_language: ISO 639-1 language code for relevance ranking.

    Returns:
        Dict with "items" list and pagination info.
    """
    client = _get_client()

    params = {
        "q": query,
        "part": "snippet",
        "type": "video",
        "maxResults": min(max(1, max_results), 50),
        "safeSearch": safe_search,
        "order": order,
    }

    if video_duration:
        params["videoDuration"] = video_duration
    if published_after:
        params["publishedAfter"] = published_after
    if channel_id:
        params["channelId"] = channel_id
    if region_code:
        params["regionCode"] = region_code
    if relevance_language:
        params["relevanceLanguage"] = relevance_language

    response = client.search().list(**params).execute()

    items = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        items.append(
            {
                "video_id": item["id"].get("videoId"),
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "channel_title": snippet.get("channelTitle"),
                "channel_id": snippet.get("channelId"),
                "published_at": snippet.get("publishedAt"),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "url": f"https://www.youtube.com/watch?v={item['id'].get('videoId')}",
            }
        )

    return {
        "items": items,
        "total_results": response.get("pageInfo", {}).get("totalResults", 0),
        "next_page_token": response.get("nextPageToken"),
    }


def get_video_details(video_ids: List[str]) -> List[Dict[str, Any]]:
    """Get detailed info for specific videos (duration, stats, tags).

    Args:
        video_ids: List of YouTube video IDs (max 50).

    Returns:
        List of video detail dicts.
    """
    client = _get_client()

    response = (
        client.videos()
        .list(
            part="snippet,contentDetails,statistics",
            id=",".join(video_ids[:50]),
        )
        .execute()
    )

    details = []
    for item in response.get("items", []):
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        stats = item.get("statistics", {})
        details.append(
            {
                "video_id": item["id"],
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "channel_title": snippet.get("channelTitle"),
                "channel_id": snippet.get("channelId"),
                "published_at": snippet.get("publishedAt"),
                "tags": snippet.get("tags", []),
                "category_id": snippet.get("categoryId"),
                "duration": content.get("duration"),  # ISO 8601 duration
                "content_rating": content.get("contentRating", {}),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
            }
        )

    return details


def get_channel_info(channel_id: str) -> Optional[Dict[str, Any]]:
    """Get channel information.

    Args:
        channel_id: YouTube channel ID.

    Returns:
        Channel info dict or None.
    """
    client = _get_client()

    response = (
        client.channels()
        .list(
            part="snippet,statistics,brandingSettings",
            id=channel_id,
        )
        .execute()
    )

    items = response.get("items", [])
    if not items:
        return None

    item = items[0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    return {
        "channel_id": item["id"],
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "country": snippet.get("country"),
        "is_kids_channel": snippet.get("madeForKids", False),
    }
