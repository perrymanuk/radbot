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
