"""CacheTelemetry for tracking and reporting on cache performance metrics."""

import logging
import time
from typing import Any, Dict


class CacheTelemetry:
    """Tracks and reports on cache performance metrics."""

    def __init__(self):
        """Initialize the telemetry collector."""
        self.logger = logging.getLogger(__name__)
        self.hits = 0
        self.misses = 0
        self.hit_latency_total = 0  # ms
        self.miss_latency_total = 0  # ms
        self.estimated_token_savings = 0
        self.entry_hit_counts = {}  # cache_key -> hit_count
        self.start_time = time.time()

    def record_hit(
        self, cache_key: str, latency_ms: float, token_count: int = 0
    ) -> None:
        """Record a cache hit.

        Args:
            cache_key: The cache key that was hit
            latency_ms: Time taken to retrieve the cached response
            token_count: Estimated token count saved
        """
        self.hits += 1
        self.hit_latency_total += latency_ms
        self.estimated_token_savings += token_count
        self.entry_hit_counts[cache_key] = self.entry_hit_counts.get(cache_key, 0) + 1

    def record_miss(self, cache_key: str, latency_ms: float) -> None:
        """Record a cache miss.

        Args:
            cache_key: The cache key that was missed
            latency_ms: Time taken to determine the miss
        """
        self.misses += 1
        self.miss_latency_total += latency_ms

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics.

        Returns:
            Dictionary of statistics
        """
        total_requests = self.hits + self.misses
        if total_requests == 0:
            return {"error": "No cache activity recorded"}

        hit_rate = self.hits / total_requests
        avg_hit_latency = self.hit_latency_total / max(1, self.hits)
        avg_miss_latency = self.miss_latency_total / max(1, self.misses)
        latency_reduction = (
            1 - (avg_hit_latency / avg_miss_latency) if self.misses > 0 else 0
        )
        uptime_seconds = time.time() - self.start_time

        return {
            "hit_rate": hit_rate,
            "miss_rate": 1 - hit_rate,
            "total_requests": total_requests,
            "hits": self.hits,
            "misses": self.misses,
            "avg_hit_latency_ms": avg_hit_latency,
            "avg_miss_latency_ms": avg_miss_latency,
            "latency_reduction": latency_reduction,
            "estimated_token_savings": self.estimated_token_savings,
            "most_frequent_entries": sorted(
                self.entry_hit_counts.items(), key=lambda x: x[1], reverse=True
            )[:10],
            "uptime_seconds": uptime_seconds,
        }
