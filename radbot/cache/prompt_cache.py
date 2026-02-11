"""PromptCache for caching LLM responses to reduce duplicate API calls."""

import hashlib
import json
import time
from typing import Any, Dict, Optional

from google.adk.models import LlmRequest, LlmResponse


class PromptCache:
    """Manages caching of LLM responses to reduce duplicate API calls."""

    def __init__(self, max_cache_size: int = 1000):
        """Initialize the prompt cache.

        Args:
            max_cache_size: Maximum number of responses to cache
        """
        self.cache: Dict[str, LlmResponse] = {}
        self.max_cache_size = max_cache_size

    def generate_cache_key(self, llm_request: LlmRequest) -> str:
        """Generate a cache key for the request.

        Args:
            llm_request: The LLM request to generate a key for

        Returns:
            A string cache key
        """
        # Get just the very last user message text
        user_message = ""

        # Extract only the last user message text, nothing else
        if hasattr(llm_request, "contents") and llm_request.contents:
            last_user_content = None

            # Find the last user message
            for content in reversed(llm_request.contents):
                if hasattr(content, "role") and content.role == "user":
                    last_user_content = content
                    break

            # Extract just the text from the last user message
            if (
                last_user_content
                and hasattr(last_user_content, "parts")
                and last_user_content.parts
            ):
                for part in last_user_content.parts:
                    if hasattr(part, "text"):
                        user_message = part.text
                        break

        # Create a super simple key that's just the model name and bare user text
        key_components = {
            "model": llm_request.model,
            "user_message": user_message.strip(),
        }

        # Create a deterministic string from the bare minimum components
        key_str = json.dumps(key_components, sort_keys=True)

        # Generate a hash for the key
        return hashlib.md5(key_str.encode("utf-8")).hexdigest()

    def _normalize_content(self, content: Any) -> Dict[str, Any]:
        """Normalize content for consistent key generation."""
        # Extract just the content role and text
        return {
            "role": getattr(content, "role", "unknown"),
            "parts": [
                {"text": getattr(p, "text", str(p))}
                for p in getattr(content, "parts", [])
            ],
        }

    def _normalize_config(self, config: Any) -> Dict[str, Any]:
        """Normalize config for consistent key generation."""
        # Extract relevant config parameters
        normalized = {}
        if hasattr(config, "temperature"):
            normalized["temperature"] = config.temperature
        if hasattr(config, "top_p"):
            normalized["top_p"] = config.top_p
        if hasattr(config, "top_k"):
            normalized["top_k"] = config.top_k
        return normalized

    def get(self, key: str) -> Optional[LlmResponse]:
        """Get a cached response by key.

        Args:
            key: Cache key

        Returns:
            Cached LlmResponse or None if not found
        """
        return self.cache.get(key)

    def put(self, key: str, response: LlmResponse) -> None:
        """Put a response in the cache.

        Args:
            key: Cache key
            response: LlmResponse to cache
        """
        # If cache is full, remove an entry
        if len(self.cache) >= self.max_cache_size:
            # Simple approach: remove a random entry
            self.cache.pop(next(iter(self.cache)))

        self.cache[key] = response
