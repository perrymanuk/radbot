"""
Configuration settings for the prompt caching system.
"""

import os
from typing import Any, Dict, Optional


def get_cache_config() -> Dict[str, Any]:
    """
    Load cache configuration from environment variables or use defaults.

    Environment variables:
    - RADBOT_CACHE_ENABLED: Enable/disable caching (default: true)
    - RADBOT_CACHE_TTL: TTL for cached entries in seconds (default: 3600)
    - RADBOT_CACHE_MAX_SIZE: Maximum entries in session cache (default: 1000)
    - RADBOT_CACHE_SELECTIVE: Only cache eligible requests (default: true)
    - RADBOT_CACHE_MIN_TOKENS: Minimum tokens in response to cache (default: 50)
    - REDIS_URL: Redis connection URL for global cache (default: None)

    Returns:
        Dictionary of cache configuration settings
    """

    # Parse boolean environment variables
    def parse_bool(env_var: str, default: bool = True) -> bool:
        value = os.getenv(env_var)
        if value is None:
            return default
        return value.lower() in ("true", "yes", "1", "t", "y")

    # Parse integer environment variables
    def parse_int(env_var: str, default: int) -> int:
        value = os.getenv(env_var)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    return {
        "enabled": parse_bool("RADBOT_CACHE_ENABLED", True),
        "ttl": parse_int("RADBOT_CACHE_TTL", 3600),
        "max_size": parse_int("RADBOT_CACHE_MAX_SIZE", 1000),
        "selective": parse_bool("RADBOT_CACHE_SELECTIVE", True),
        "min_tokens": parse_int("RADBOT_CACHE_MIN_TOKENS", 50),
        "redis_url": os.getenv("REDIS_URL"),
    }
