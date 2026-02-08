"""
TTS service using Google Cloud Text-to-Speech REST API.

Singleton that synthesizes text to MP3 audio with an in-memory LRU cache.
Text is cleaned of markdown/HTML/code blocks before synthesis.
Uses the Google API key from config.yaml (same key as Gemini) via the REST API,
so no Application Default Credentials are needed.
"""

import base64
import hashlib
import json
import logging
import re
from collections import OrderedDict
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

# Singleton
_instance: Optional["TTSService"] = None

# REST endpoints for Google Cloud TTS
TTS_API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
TTS_API_URL_BETA = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"

# Voice prefixes that require the v1beta1 endpoint
_BETA_VOICE_PREFIXES = ("Chirp", "chirp")


class TTSService:
    """Google Cloud TTS wrapper using REST API with API key auth."""

    DEFAULT_VOICE = "en-US-Neural2-D"
    DEFAULT_LANGUAGE = "en-US"
    DEFAULT_SPEAKING_RATE = 1.0
    DEFAULT_PITCH = 0.0
    MAX_TEXT_LENGTH = 5000
    CACHE_MAX_SIZE = 100

    def __init__(
        self,
        voice_name: Optional[str] = None,
        language_code: Optional[str] = None,
        speaking_rate: Optional[float] = None,
        pitch: Optional[float] = None,
        api_key: Optional[str] = None,
    ):
        self.voice_name = voice_name or self.DEFAULT_VOICE
        self.language_code = language_code or self.DEFAULT_LANGUAGE
        self.speaking_rate = speaking_rate if speaking_rate is not None else self.DEFAULT_SPEAKING_RATE
        self.pitch = pitch if pitch is not None else self.DEFAULT_PITCH
        self._api_key = api_key
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    @classmethod
    def get_instance(cls) -> Optional["TTSService"]:
        return _instance

    @classmethod
    def create_instance(cls, **kwargs) -> "TTSService":
        global _instance
        if _instance is None:
            _instance = cls(**kwargs)
        return _instance

    def _get_api_key(self) -> str:
        """Get the Google API key, resolving lazily from config if needed."""
        if self._api_key:
            return self._api_key

        # Try to get from config (same key used for Gemini)
        try:
            from radbot.config.adk_config import get_google_api_key
            key = get_google_api_key()
            if key:
                self._api_key = key
                return key
        except Exception as e:
            logger.warning(f"Could not get API key from config: {e}")

        raise ValueError(
            "No Google API key found for TTS. "
            "Set GOOGLE_API_KEY env var or api_keys.google in config.yaml. "
            "The Text-to-Speech API must be enabled in your Google Cloud project."
        )

    @staticmethod
    def clean_text(text: str) -> str:
        """Strip markdown, HTML tags, and code blocks from text for cleaner speech."""
        # Remove code blocks (``` ... ```)
        text = re.sub(r"```[\s\S]*?```", " code block omitted ", text)
        # Remove inline code (`...`)
        text = re.sub(r"`[^`]+`", "", text)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Remove markdown headers (# ## ### etc.)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove markdown bold/italic markers
        text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
        text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
        # Remove markdown links [text](url)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Remove markdown images ![alt](url)
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        # Remove horizontal rules
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
        # Remove bullet points
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        # Remove numbered lists prefix
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        # Collapse multiple whitespace/newlines
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _cache_key(self, text: str) -> str:
        """Create a cache key from text + voice config."""
        raw = f"{text}|{self.voice_name}|{self.language_code}|{self.speaking_rate}|{self.pitch}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to MP3 audio bytes via the REST API.

        Text is cleaned and truncated before synthesis.
        Results are cached in an in-memory LRU cache.

        Args:
            text: The raw text (may include markdown/HTML).

        Returns:
            MP3 audio bytes.

        Raises:
            Exception if API key is missing or synthesis fails.
        """
        cleaned = self.clean_text(text)
        if not cleaned:
            raise ValueError("No speakable text after cleaning")

        # Truncate
        if len(cleaned) > self.MAX_TEXT_LENGTH:
            cleaned = cleaned[: self.MAX_TEXT_LENGTH]
            logger.warning(f"Text truncated to {self.MAX_TEXT_LENGTH} chars for TTS")

        # Check cache
        key = self._cache_key(cleaned)
        if key in self._cache:
            self._cache.move_to_end(key)
            logger.debug("TTS cache hit")
            return self._cache[key]

        # Build REST API request
        api_key = self._get_api_key()

        # Chirp3-HD and other newer voices require the v1beta1 endpoint
        use_beta = any(p in self.voice_name for p in _BETA_VOICE_PREFIXES)
        base_url = TTS_API_URL_BETA if use_beta else TTS_API_URL
        url = f"{base_url}?key={api_key}"

        audio_config = {"audioEncoding": "MP3"}
        # Chirp3-HD voices don't support pitch/rate parameters
        if not use_beta:
            audio_config["speakingRate"] = self.speaking_rate
            audio_config["pitch"] = self.pitch

        payload = {
            "input": {"text": cleaned},
            "voice": {
                "languageCode": self.language_code,
                "name": self.voice_name,
            },
            "audioConfig": audio_config,
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
            logger.error(f"TTS API HTTP error {e.code}: {error_body}")
            raise RuntimeError(f"TTS API error ({e.code}): {error_body}") from e
        except URLError as e:
            logger.error(f"TTS API connection error: {e}")
            raise RuntimeError(f"TTS API connection error: {e}") from e

        # Decode base64 audio content
        audio_content_b64 = response_data.get("audioContent")
        if not audio_content_b64:
            raise RuntimeError("TTS API returned no audio content")

        audio_bytes = base64.b64decode(audio_content_b64)
        logger.info(f"TTS synthesized {len(audio_bytes)} bytes for {len(cleaned)} chars")

        # Cache (LRU eviction)
        self._cache[key] = audio_bytes
        if len(self._cache) > self.CACHE_MAX_SIZE:
            self._cache.popitem(last=False)

        return audio_bytes
