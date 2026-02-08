"""
STT service using Google Cloud Speech-to-Text REST API.

Singleton that transcribes audio bytes to text.
Uses the Google API key from config.yaml (same key as Gemini/TTS) via the REST API,
so no Application Default Credentials are needed.
"""

import base64
import json
import logging
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Singleton
_instance: Optional["STTService"] = None

# REST endpoint for Google Cloud Speech-to-Text
STT_API_URL = "https://speech.googleapis.com/v1/speech:recognize"


class STTService:
    """Google Cloud STT wrapper using REST API with API key auth."""

    DEFAULT_LANGUAGE = "en-US"
    DEFAULT_MODEL = "latest_long"

    def __init__(
        self,
        language_code: Optional[str] = None,
        model: Optional[str] = None,
        enable_automatic_punctuation: bool = True,
        api_key: Optional[str] = None,
    ):
        self.language_code = language_code or self.DEFAULT_LANGUAGE
        self.model = model or self.DEFAULT_MODEL
        self.enable_automatic_punctuation = enable_automatic_punctuation
        self._api_key = api_key

    @classmethod
    def get_instance(cls) -> Optional["STTService"]:
        return _instance

    @classmethod
    def create_instance(cls, **kwargs) -> "STTService":
        global _instance
        if _instance is None:
            _instance = cls(**kwargs)
        return _instance

    def _get_api_key(self) -> str:
        """Get the Google API key, resolving lazily from config if needed."""
        if self._api_key:
            return self._api_key

        try:
            from radbot.config.adk_config import get_google_api_key
            key = get_google_api_key()
            if key:
                self._api_key = key
                return key
        except Exception as e:
            logger.warning(f"Could not get API key from config: {e}")

        raise ValueError(
            "No Google API key found for STT. "
            "Set GOOGLE_API_KEY env var or api_keys.google in config.yaml. "
            "The Speech-to-Text API must be enabled in your Google Cloud project."
        )

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 48000) -> str:
        """
        Transcribe audio bytes to text via the REST API.

        Args:
            audio_bytes: Raw audio data (WebM/Opus from browser MediaRecorder).
            sample_rate: Audio sample rate in Hz (default 48000 for browser WebM).

        Returns:
            Transcribed text string.

        Raises:
            ValueError if no transcript is returned.
            RuntimeError if the API call fails.
        """
        if not audio_bytes:
            raise ValueError("No audio data provided")

        api_key = self._get_api_key()
        url = f"{STT_API_URL}?key={api_key}"

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        payload = {
            "config": {
                "encoding": "WEBM_OPUS",
                "sampleRateHertz": sample_rate,
                "languageCode": self.language_code,
                "model": self.model,
                "enableAutomaticPunctuation": self.enable_automatic_punctuation,
            },
            "audio": {
                "content": audio_b64,
            },
        }

        request_body = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=30) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error(f"STT API HTTP error {e.code}: {error_body}")
            raise RuntimeError(f"STT API error ({e.code}): {error_body}") from e
        except URLError as e:
            logger.error(f"STT API connection error: {e}")
            raise RuntimeError(f"STT API connection error: {e}") from e

        # Extract transcript from response
        results = response_data.get("results", [])
        if not results:
            raise ValueError("No speech detected in audio")

        # Concatenate all result transcripts
        transcript_parts = []
        for result in results:
            alternatives = result.get("alternatives", [])
            if alternatives:
                transcript_parts.append(alternatives[0].get("transcript", ""))

        transcript = " ".join(transcript_parts).strip()
        if not transcript:
            raise ValueError("No speech detected in audio")

        logger.info(f"STT transcribed {len(audio_bytes)} bytes to {len(transcript)} chars")
        return transcript
