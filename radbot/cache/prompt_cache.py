"""PromptCache for caching LLM responses to reduce duplicate API calls."""

import collections
import hashlib
import json
from typing import Any, Dict, Optional

from google.adk.models import LlmRequest, LlmResponse


class PromptCache:
    """Manages caching of LLM responses to reduce duplicate API calls."""

    def __init__(self, max_cache_size: int = 1000):
        """Initialize the prompt cache.

        Args:
            max_cache_size: Maximum number of responses to cache
        """
        self.cache: collections.OrderedDict[str, LlmResponse] = (
            collections.OrderedDict()
        )
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

        # Include model, user text, and generation config in the cache key
        key_components = {
            "model": llm_request.model,
            "user_message": user_message.strip(),
        }

        # Include relevant GenerateContentConfig fields that affect output
        config = getattr(llm_request, "config", None)
        if config:
            for attr in ("temperature", "top_p", "top_k", "max_output_tokens"):
                val = getattr(config, attr, None)
                if isinstance(val, (int, float)):
                    key_components[attr] = val

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
        """Get a cached response by key (LRU: moves accessed entry to end).

        Args:
            key: Cache key

        Returns:
            Cached LlmResponse or None if not found
        """
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, key: str, response: LlmResponse) -> None:
        """Put a response in the cache.

        Args:
            key: Cache key
            response: LlmResponse to cache
        """
        # LRU eviction: remove the least recently used (oldest) entry
        if len(self.cache) >= self.max_cache_size:
            self.cache.popitem(last=False)

        self.cache[key] = response
