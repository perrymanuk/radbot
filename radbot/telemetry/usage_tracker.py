"""Singleton tracker for Gemini API token usage and estimated costs.

Thread-safe accumulator that records per-request token counts, cache hits,
and per-agent breakdowns.  Estimated costs use public Gemini pricing as of
2026-02 (Pro: $1.25/M input, $5.00/M output; Flash: $0.075/M input,
$0.30/M output; cached input: ~25% of base rate).
"""

import threading
import time
from collections import defaultdict
from typing import Any, Dict, Optional


# Gemini pricing per million tokens (USD)
_PRICING = {
    # model_prefix: (input_per_M, output_per_M, cached_input_per_M)
    "gemini-2.5-pro": (1.25, 10.00, 0.3125),
    "gemini-2.5-flash": (0.15, 0.60, 0.0375),
    "gemini-2.0-flash": (0.10, 0.40, 0.025),
    # Fallback for unknown models
    "_default": (1.25, 10.00, 0.3125),
}


def _get_pricing(model: str) -> tuple:
    """Return (input, output, cached_input) pricing per M tokens for *model*."""
    model_lower = (model or "").lower()
    for prefix, pricing in _PRICING.items():
        if prefix != "_default" and model_lower.startswith(prefix):
            return pricing
    return _PRICING["_default"]


class UsageTracker:
    """Accumulates token usage and estimates cost across all requests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.time()
        self._total_prompt_tokens = 0
        self._total_cached_tokens = 0
        self._total_output_tokens = 0
        self._total_requests = 0
        self._estimated_cost_usd = 0.0
        self._estimated_cost_without_cache_usd = 0.0
        # Per-agent breakdown: agent_name -> {prompt, cached, output, requests, cost}
        self._per_agent: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {
                "prompt_tokens": 0,
                "cached_tokens": 0,
                "output_tokens": 0,
                "requests": 0,
                "cost_usd": 0.0,
            }
        )

    def record(
        self,
        prompt_tokens: int = 0,
        cached_tokens: int = 0,
        output_tokens: int = 0,
        agent_name: str = "unknown",
        model: str = "",
    ) -> None:
        """Record a single LLM invocation's token usage."""
        input_price, output_price, cached_price = _get_pricing(model)

        # Non-cached input tokens = total prompt - cached portion
        fresh_input = max(0, prompt_tokens - cached_tokens)
        cost = (
            (fresh_input / 1_000_000) * input_price
            + (cached_tokens / 1_000_000) * cached_price
            + (output_tokens / 1_000_000) * output_price
        )
        cost_without_cache = (
            (prompt_tokens / 1_000_000) * input_price
            + (output_tokens / 1_000_000) * output_price
        )

        with self._lock:
            self._total_prompt_tokens += prompt_tokens
            self._total_cached_tokens += cached_tokens
            self._total_output_tokens += output_tokens
            self._total_requests += 1
            self._estimated_cost_usd += cost
            self._estimated_cost_without_cache_usd += cost_without_cache

            agent = self._per_agent[agent_name]
            agent["prompt_tokens"] += prompt_tokens
            agent["cached_tokens"] += cached_tokens
            agent["output_tokens"] += output_tokens
            agent["requests"] += 1
            agent["cost_usd"] += cost

    def get_stats(self) -> Dict[str, Any]:
        """Return a snapshot of accumulated usage statistics."""
        with self._lock:
            cache_rate = (
                (self._total_cached_tokens / self._total_prompt_tokens * 100)
                if self._total_prompt_tokens > 0
                else 0.0
            )
            savings = self._estimated_cost_without_cache_usd - self._estimated_cost_usd
            return {
                "uptime_seconds": round(time.time() - self._started_at, 1),
                "total_requests": self._total_requests,
                "total_prompt_tokens": self._total_prompt_tokens,
                "total_cached_tokens": self._total_cached_tokens,
                "total_output_tokens": self._total_output_tokens,
                "cache_hit_rate_pct": round(cache_rate, 1),
                "estimated_cost_usd": round(self._estimated_cost_usd, 6),
                "estimated_cost_without_cache_usd": round(
                    self._estimated_cost_without_cache_usd, 6
                ),
                "estimated_savings_usd": round(savings, 6),
                "per_agent": {
                    name: dict(data) for name, data in self._per_agent.items()
                },
            }

    def reset(self) -> None:
        """Clear all accumulated counters."""
        with self._lock:
            self._started_at = time.time()
            self._total_prompt_tokens = 0
            self._total_cached_tokens = 0
            self._total_output_tokens = 0
            self._total_requests = 0
            self._estimated_cost_usd = 0.0
            self._estimated_cost_without_cache_usd = 0.0
            self._per_agent.clear()


# Module-level singleton
usage_tracker = UsageTracker()
