"""Kideo API client for submitting YouTube videos to a curated kids video library.

Kideo downloads, transcodes, and serves videos in a child-safe player.
Videos are organized into collections.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from radbot.tools.shared.config_helper import get_integration_config

logger = logging.getLogger(__name__)

_client: Optional[httpx.Client] = None


def _get_config() -> Dict[str, Any]:
    """Resolve Kideo configuration."""
    return get_integration_config(
        "kideo",
        fields={"url": "KIDEO_URL", "api_key": "KIDEO_API_KEY"},
        credential_keys={"api_key": "kideo_api_key"},
    )


def _get_client() -> httpx.Client:
    """Get or create the Kideo HTTP client singleton."""
    global _client
    if _client is not None:
        return _client

    config = _get_config()
    url = config.get("url")
    if not url:
        raise RuntimeError(
            "Kideo URL not configured. "
            "Set via Admin UI (config:integrations → kideo.url), "
            "or KIDEO_URL env var."
        )

    headers = {"Content-Type": "application/json"}
    api_key = config.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    _client = httpx.Client(
        base_url=url.rstrip("/"),
        headers=headers,
        timeout=30.0,
    )
    logger.info("Kideo client initialized: %s", url)
    return _client


def reset_kideo_client():
    """Reset the singleton client (for hot-reload)."""
    global _client
    if _client is not None:
        _client.close()
    _client = None
    logger.debug("Kideo client reset")


def add_video(url: str, collection_id: Optional[str] = None) -> Dict[str, Any]:
    """Add a single video to Kideo.

    Args:
        url: YouTube video URL.
        collection_id: Optional collection UUID to add the video to.

    Returns:
        Video response dict with id, title, status, etc.
    """
    client = _get_client()
    payload: Dict[str, Any] = {"url": url}
    if collection_id:
        payload["collection_id"] = collection_id

    resp = client.post("/api/videos", json=payload)
    resp.raise_for_status()
    return resp.json()


def add_videos_batch(
    urls: List[str], collection_id: str
) -> List[Dict[str, Any]]:
    """Add multiple videos to a Kideo collection.

    Args:
        urls: List of YouTube video URLs.
        collection_id: Collection UUID to add videos to.

    Returns:
        List of batch add results with video_id, url, and status.
    """
    client = _get_client()
    resp = client.post(
        f"/api/collections/{collection_id}/videos/batch",
        json={"urls": urls},
    )
    resp.raise_for_status()
    return resp.json()


def list_collections() -> List[Dict[str, Any]]:
    """List all Kideo collections.

    Returns:
        List of collection dicts with id, name, color, icon, video_count.
    """
    client = _get_client()
    resp = client.get("/api/collections")
    resp.raise_for_status()
    return resp.json()


def create_collection(
    name: str, color: str = "#4F46E5", icon: str = "star"
) -> Dict[str, Any]:
    """Create a new Kideo collection.

    Args:
        name: Collection name.
        color: Hex color (default indigo).
        icon: Icon name (default star).

    Returns:
        Created collection dict.
    """
    client = _get_client()
    resp = client.post(
        "/api/collections",
        json={"name": name, "color": color, "icon": icon},
    )
    resp.raise_for_status()
    return resp.json()


def set_video_tags(video_id: str, tags: List[str]) -> Dict[str, Any]:
    """Set tags on a Kideo video.

    Args:
        video_id: Kideo video UUID.
        tags: List of tag strings.

    Returns:
        Updated video response dict.
    """
    client = _get_client()
    resp = client.put(
        f"/api/videos/{video_id}/tags",
        json={"tags": tags},
    )
    resp.raise_for_status()
    return resp.json()


def list_all_tags() -> List[str]:
    """List all existing tags in Kideo.

    Returns:
        List of tag strings.
    """
    client = _get_client()
    resp = client.get("/api/videos/tags/all")
    resp.raise_for_status()
    return resp.json()


def get_collection(collection_id: str) -> Dict[str, Any]:
    """Get a collection with its videos.

    Args:
        collection_id: Collection UUID.

    Returns:
        Collection dict with videos list.
    """
    client = _get_client()
    resp = client.get(f"/api/collections/{collection_id}")
    resp.raise_for_status()
    return resp.json()


def list_videos(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all videos, optionally filtered by status.

    Args:
        status: Optional filter — "pending", "downloading", "transcoding", "ready", "error".

    Returns:
        List of video response dicts (includes tags, channel_name, etc.).
    """
    client = _get_client()
    params = {}
    if status:
        params["status"] = status
    resp = client.get("/api/videos", params=params)
    resp.raise_for_status()
    return resp.json()


def find_video_by_url(url: str) -> Optional[Dict[str, Any]]:
    """Look up a Kideo video by its source URL.

    Tries a direct query first (``GET /api/videos?url=<encoded>``) and falls
    back to scanning the full list if the server doesn't honor the filter.
    Returns the matching video dict (id, title, status, ...) or None.

    Used by :func:`radbot.tools.shared.card_protocol._lookup_kideo_status`
    to set library status on rendered video cards.
    """
    if not url:
        return None
    client = _get_client()
    try:
        resp = client.get("/api/videos", params={"url": url})
        resp.raise_for_status()
    except httpx.HTTPError:
        return None
    body = resp.json()
    if isinstance(body, dict):
        body = body.get("videos") or body.get("items") or [body]
    if not isinstance(body, list):
        return None
    for item in body:
        if isinstance(item, dict) and item.get("url") == url:
            return item
    return None


def get_popular_videos(
    collection_id: str, limit: int = 20, days: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get most-played videos in a collection.

    Args:
        collection_id: Collection UUID.
        limit: Max results (default 20).
        days: Optional time window in days.

    Returns:
        List of PopularVideo dicts (id, title, url, play_count, tags).
    """
    client = _get_client()
    params: Dict[str, Any] = {"limit": limit}
    if days is not None:
        params["days"] = days
    resp = client.get(
        f"/api/collections/{collection_id}/popular", params=params
    )
    resp.raise_for_status()
    return resp.json()


def get_tag_stats(
    collection_id: str, days: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get most popular tags in a collection ranked by play count.

    Args:
        collection_id: Collection UUID.
        days: Optional time window in days.

    Returns:
        List of TagStats dicts (tag, play_count, video_count).
    """
    client = _get_client()
    params: Dict[str, Any] = {}
    if days is not None:
        params["days"] = days
    resp = client.get(
        f"/api/collections/{collection_id}/tag-stats", params=params
    )
    resp.raise_for_status()
    return resp.json()


def get_channel_stats(
    collection_id: str, days: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get most popular channels in a collection ranked by play count.

    Args:
        collection_id: Collection UUID.
        days: Optional time window in days.

    Returns:
        List of ChannelStats dicts (channel_name, channel_url, platform, play_count, video_count).
    """
    client = _get_client()
    params: Dict[str, Any] = {}
    if days is not None:
        params["days"] = days
    resp = client.get(
        f"/api/collections/{collection_id}/channel-stats", params=params
    )
    resp.raise_for_status()
    return resp.json()
