"""Unit tests for the prompt caching system."""

from unittest.mock import MagicMock

from radbot.cache.cache_telemetry import CacheTelemetry
from radbot.cache.prompt_cache import PromptCache


class TestPromptCache:
    """Tests for the PromptCache class."""

    def test_init(self):
        """Test initialization of the PromptCache."""
        cache = PromptCache(max_cache_size=100)
        assert cache.max_cache_size == 100
        assert cache.cache == {}

    def test_get_missing(self):
        """Test getting a non-existent key."""
        cache = PromptCache()
        assert cache.get("missing_key") is None

    def test_put_and_get(self):
        """Test putting and getting a value."""
        cache = PromptCache()
        mock_response = MagicMock()
        cache.put("test_key", mock_response)
        assert cache.get("test_key") == mock_response

    def test_cache_eviction(self):
        """Test cache eviction when max size is reached."""
        cache = PromptCache(max_cache_size=2)
        mock_response1 = MagicMock()
        mock_response2 = MagicMock()
        mock_response3 = MagicMock()

        cache.put("key1", mock_response1)
        cache.put("key2", mock_response2)
        assert len(cache.cache) == 2

        # Adding a third item should evict the first one
        cache.put("key3", mock_response3)
        assert len(cache.cache) == 2
        assert "key1" not in cache.cache or "key2" not in cache.cache
        assert "key3" in cache.cache

    def test_generate_cache_key(self):
        """Test cache key generation."""
        cache = PromptCache()

        # Mock LlmRequest
        mock_request = MagicMock()
        mock_request.model = "test-model"

        # Mock content
        mock_content = MagicMock()
        mock_content.role = "user"
        mock_part = MagicMock()
        mock_part.text = "test query"
        mock_content.parts = [mock_part]
        mock_request.contents = [mock_content]

        # Mock config
        mock_config = MagicMock()
        mock_config.temperature = 0.7
        mock_request.config = mock_config

        # Generate key
        key = cache.generate_cache_key(mock_request)

        # Verify key is a string
        assert isinstance(key, str)

        # Verify key is deterministic
        assert cache.generate_cache_key(mock_request) == key

        # Change request and verify key changes
        mock_part.text = "different query"
        assert cache.generate_cache_key(mock_request) != key


class TestCacheTelemetry:
    """Tests for the CacheTelemetry class."""

    def test_init(self):
        """Test initialization of the CacheTelemetry."""
        telemetry = CacheTelemetry()
        assert telemetry.hits == 0
        assert telemetry.misses == 0
        assert telemetry.entry_hit_counts == {}

    def test_record_hit(self):
        """Test recording a cache hit."""
        telemetry = CacheTelemetry()
        telemetry.record_hit("test_key", 10.5, 100)

        assert telemetry.hits == 1
        assert telemetry.hit_latency_total == 10.5
        assert telemetry.estimated_token_savings == 100
        assert telemetry.entry_hit_counts["test_key"] == 1

        # Record another hit for the same key
        telemetry.record_hit("test_key", 5.5, 50)
        assert telemetry.hits == 2
        assert telemetry.hit_latency_total == 16.0
        assert telemetry.estimated_token_savings == 150
        assert telemetry.entry_hit_counts["test_key"] == 2

    def test_record_miss(self):
        """Test recording a cache miss."""
        telemetry = CacheTelemetry()
        telemetry.record_miss("test_key", 20.0)

        assert telemetry.misses == 1
        assert telemetry.miss_latency_total == 20.0

        # Record another miss
        telemetry.record_miss("another_key", 15.0)
        assert telemetry.misses == 2
        assert telemetry.miss_latency_total == 35.0

    def test_get_stats_no_activity(self):
        """Test getting stats with no activity."""
        telemetry = CacheTelemetry()
        stats = telemetry.get_stats()

        assert "error" in stats
        assert stats["error"] == "No cache activity recorded"

    def test_get_stats(self):
        """Test getting stats with some activity."""
        telemetry = CacheTelemetry()

        # Record some activity
        telemetry.record_hit("key1", 10.0, 100)
        telemetry.record_hit("key2", 15.0, 150)
        telemetry.record_miss("key3", 30.0)

        stats = telemetry.get_stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["total_requests"] == 3
        assert abs(stats["hit_rate"] - 2 / 3) < 0.0001
        assert abs(stats["miss_rate"] - 1 / 3) < 0.0001
        assert stats["avg_hit_latency_ms"] == 12.5
        assert stats["avg_miss_latency_ms"] == 30.0
        assert stats["estimated_token_savings"] == 250

        # Verify most frequent entries
        most_frequent = stats["most_frequent_entries"]
        assert len(most_frequent) == 2
        assert ("key1", 1) in most_frequent
        assert ("key2", 1) in most_frequent
