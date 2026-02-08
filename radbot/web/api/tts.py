"""
FastAPI router for Text-to-Speech synthesis.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tts", tags=["tts"])


class SynthesizeRequest(BaseModel):
    text: str
    voice_name: Optional[str] = None
    language_code: Optional[str] = None
    speaking_rate: Optional[float] = None
    pitch: Optional[float] = None


@router.post("/synthesize")
async def synthesize(body: SynthesizeRequest):
    """
    Synthesize text to speech and return MP3 audio.

    Returns audio/mpeg bytes directly for immediate playback.
    """
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    try:
        from radbot.tools.tts.tts_service import TTSService

        service = TTSService.get_instance()
        if service is None:
            # Create a default instance
            service = TTSService.create_instance()

        # Override voice settings if provided in the request
        original_voice = service.voice_name
        original_lang = service.language_code
        original_rate = service.speaking_rate
        original_pitch = service.pitch

        try:
            if body.voice_name:
                service.voice_name = body.voice_name
            if body.language_code:
                service.language_code = body.language_code
            if body.speaking_rate is not None:
                service.speaking_rate = body.speaking_rate
            if body.pitch is not None:
                service.pitch = body.pitch

            audio_bytes = service.synthesize(body.text)
        finally:
            # Restore original settings
            service.voice_name = original_voice
            service.language_code = original_lang
            service.speaking_rate = original_rate
            service.pitch = original_pitch

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError as e:
        logger.error(f"TTS dependency not available: {e}")
        raise HTTPException(
            status_code=503,
            detail="Text-to-Speech service not available.",
        )
    except Exception as e:
        logger.error(f"TTS synthesis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {str(e)}")
