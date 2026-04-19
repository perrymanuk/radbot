"""Kid-video REST endpoints for direct-action buttons in VideoCard.

Thin wrappers over :mod:`radbot.tools.youtube.kideo_client` so the frontend
can add a video to Kideo (and check library status) without a full LLM
roundtrip — mirrors the casa/Overseerr setup in :mod:`radbot.web.api.media`.

Endpoints:
  * ``GET  /api/videos/collections``                — list Kideo collections
  * ``GET  /api/videos/kideo-status?url=...``       — check Kideo status
  * ``POST /api/videos/add-to-kideo``               — add a video to Kideo
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/videos", tags=["videos"])


# ── Status mapping ───────────────────────────────────────────────────────
# Kideo's per-video status strings → the four UI states VideoCard renders.
_KIDEO_STATUS_MAP = {
    "ready": "in_library",
    "available": "in_library",
    "downloaded": "in_library",
    "queued": "queued",
    "pending": "queued",
    "downloading": "processing",
    "transcoding": "processing",
    "error": "error",
    "failed": "error",
}


def _map_status(raw: Optional[str]) -> str:
    return _KIDEO_STATUS_MAP.get((raw or "").lower(), "in_library")


# ── Routes ───────────────────────────────────────────────────────────────


@router.get("/collections")
async def list_collections() -> Dict[str, Any]:
    """List Kideo collections for the add-to-Kideo collection picker."""
    from radbot.tools.youtube.kideo_client import list_collections

    try:
        collections = list_collections()
    except Exception as e:
        logger.error("Kideo list_collections failed: %s", e)
        raise HTTPException(502, f"Kideo unreachable: {e}")
    return {"collections": collections or []}


@router.get("/kideo-status")
async def get_kideo_status(url: str = Query(..., min_length=1)) -> Dict[str, Any]:
    """Look up a video by URL and report its Kideo library status."""
    from radbot.tools.youtube.kideo_client import find_video_by_url

    try:
        match = find_video_by_url(url)
    except Exception as e:
        logger.error("Kideo find_video_by_url failed: %s", e)
        raise HTTPException(502, f"Kideo unreachable: {e}")
    if not match:
        return {"status": "not_added", "kideo_video_id": None}
    return {
        "status": _map_status(match.get("status")),
        "kideo_video_id": match.get("id"),
    }


class AddToKideoBody(BaseModel):
    url: str
    collection_id: Optional[str] = None
    generate_tags: bool = True


def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def _extract_youtube_id(url: str) -> Optional[str]:
    if "v=" in url:
        return url.split("v=", 1)[1].split("&", 1)[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/", 1)[1].split("?", 1)[0]
    return None


def _maybe_generate_tags(url: str, kideo_video_id: str) -> List[str]:
    """Generate + apply educational tags for a YouTube video. Best-effort."""
    if not _is_youtube(url):
        return []
    yt_id = _extract_youtube_id(url)
    if not yt_id:
        return []
    try:
        from radbot.tools.youtube.kideo_client import set_video_tags
        from radbot.tools.youtube.tag_generator import generate_tags_for_video
        from radbot.tools.youtube.youtube_client import get_video_details

        details_list = get_video_details([yt_id])
        if not details_list:
            return []
        details = details_list[0]
        details["video_id"] = yt_id
        tags = generate_tags_for_video(details)
        if tags:
            set_video_tags(kideo_video_id, tags)
        return tags
    except Exception as e:
        logger.warning("Tag generation failed for %s: %s", url, e)
        return []


@router.post("/add-to-kideo")
async def add_to_kideo(body: AddToKideoBody) -> Dict[str, Any]:
    """Add a video to Kideo. Optionally generate + apply educational tags."""
    if "/shorts/" in body.url:
        raise HTTPException(
            400, "YouTube Shorts are not allowed — only full-length videos"
        )
    from radbot.tools.youtube.kideo_client import add_video

    try:
        result = add_video(url=body.url, collection_id=body.collection_id)
    except Exception as e:
        logger.error("Kideo add_video failed: %s", e)
        raise HTTPException(502, f"Kideo add failed: {e}")

    kideo_video_id = result.get("id")
    tags: List[str] = []
    if body.generate_tags and kideo_video_id:
        tags = _maybe_generate_tags(body.url, kideo_video_id)

    return {
        "status": _map_status(result.get("status")),
        "kideo_video_id": kideo_video_id,
        "title": result.get("title"),
        "collection_id": body.collection_id,
        "tags": tags,
    }


def register_videos_router(app):
    app.include_router(router)
    logger.debug("Videos router registered")
