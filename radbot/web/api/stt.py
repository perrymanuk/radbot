"""
FastAPI router for Speech-to-Text transcription.
"""

import logging

from fastapi import APIRouter, HTTPException, UploadFile, File

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stt", tags=["stt"])


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Transcribe uploaded audio to text.

    Accepts a WebM/Opus audio file (from browser MediaRecorder)
    and returns the transcribed text.
    """
    if not audio.filename and not audio.content_type:
        raise HTTPException(status_code=400, detail="No audio file provided")

    try:
        audio_bytes = await audio.read()
    except Exception as e:
        logger.error(f"Error reading uploaded audio: {e}")
        raise HTTPException(status_code=400, detail="Could not read audio data")

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    try:
        from radbot.tools.stt.stt_service import STTService

        service = STTService.get_instance()
        if service is None:
            service = STTService.create_instance()

        transcript = service.transcribe(audio_bytes)
        return {"text": transcript}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError as e:
        logger.error(f"STT dependency not available: {e}")
        raise HTTPException(
            status_code=503,
            detail="Speech-to-Text service not available.",
        )
    except Exception as e:
        logger.error(f"STT transcription error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"STT transcription failed: {str(e)}")
