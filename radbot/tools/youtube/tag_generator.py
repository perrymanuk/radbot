"""Generate educational tags for YouTube videos using transcript + description.

Uses a small fast model (gemini-2.5-flash) to analyze video content and
produce relevant tags for children's video curation.
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def fetch_transcript(video_id: str) -> Optional[str]:
    """Fetch the transcript/captions for a YouTube video.

    Args:
        video_id: YouTube video ID.

    Returns:
        Transcript text or None if unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Prefer manually created, then auto-generated
        transcript = None
        try:
            transcript = transcript_list.find_manually_created_transcript(
                ["en", "en-US", "en-GB"]
            )
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(
                    ["en", "en-US", "en-GB"]
                )
            except Exception:
                # Try any available transcript and translate
                try:
                    for t in transcript_list:
                        transcript = t.translate("en")
                        break
                except Exception:
                    pass

        if transcript is None:
            logger.debug(f"No transcript available for video {video_id}")
            return None

        snippets = transcript.fetch()
        text = " ".join(s.get("text", "") for s in snippets)
        # Truncate to ~4000 chars to keep LLM costs low
        if len(text) > 4000:
            text = text[:4000] + "..."
        return text

    except Exception as e:
        logger.debug(f"Failed to fetch transcript for {video_id}: {e}")
        return None


def generate_tags(
    title: str,
    description: str,
    transcript: Optional[str] = None,
    channel_title: Optional[str] = None,
) -> List[str]:
    """Generate educational tags for a video using a small fast model.

    Args:
        title: Video title.
        description: Video description.
        transcript: Optional transcript text.
        channel_title: Optional channel name.

    Returns:
        List of lowercase tag strings.
    """
    from google import genai

    # Build context for the model
    parts = [f"Title: {title}"]
    if channel_title:
        parts.append(f"Channel: {channel_title}")
    if description:
        # Truncate description to ~1000 chars
        desc = description[:1000] + ("..." if len(description) > 1000 else "")
        parts.append(f"Description: {desc}")
    if transcript:
        parts.append(f"Transcript excerpt: {transcript}")

    video_context = "\n".join(parts)

    prompt = f"""Analyze this children's YouTube video and generate relevant tags for categorization.

{video_context}

Generate 3-8 tags that describe:
- The main subject/topic (e.g. dinosaurs, outer space, math, animals)
- The type of content (e.g. crafting, storytime, music, science experiment, documentary)
- The educational domain (e.g. science, art, language, social skills, nature)
- Age-appropriate descriptors if obvious (e.g. toddler, preschool)

Rules:
- Return ONLY a comma-separated list of tags, nothing else
- All lowercase
- Keep tags short (1-3 words each)
- Be specific over generic (prefer "marine animals" over just "animals" if that's the focus)
- Do not include generic tags like "kids", "children", "educational", "youtube"
"""

    try:
        from radbot.config.adk_config import get_google_api_key

        api_key = get_google_api_key()
        if not api_key:
            logger.warning("No Google API key available for tag generation")
            return []

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=200,
            ),
        )

        raw = response.text.strip()
        # Parse comma-separated tags
        tags = [
            tag.strip().lower().strip('"\'')
            for tag in raw.split(",")
            if tag.strip()
        ]
        # Remove any tags that are too long or empty
        tags = [t for t in tags if 0 < len(t) <= 50]

        logger.info(f"Generated {len(tags)} tags for '{title}': {tags}")
        return tags

    except Exception as e:
        logger.error(f"Tag generation failed for '{title}': {e}")
        return []


def generate_tags_for_video(video_details: Dict[str, Any]) -> List[str]:
    """Generate tags for a video using its details from the YouTube API.

    Convenience function that handles transcript fetching and passes
    everything to generate_tags.

    Args:
        video_details: Dict with keys: video_id, title, description,
            channel_title (as returned by youtube_client.get_video_details
            or youtube_client.search_videos).

    Returns:
        List of tag strings.
    """
    video_id = video_details.get("video_id", "")
    title = video_details.get("title", "")
    description = video_details.get("description", "")
    channel_title = video_details.get("channel_title")

    # Fetch transcript
    transcript = None
    if video_id:
        transcript = fetch_transcript(video_id)

    return generate_tags(
        title=title,
        description=description,
        transcript=transcript,
        channel_title=channel_title,
    )
