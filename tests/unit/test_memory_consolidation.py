"""Unit tests for Dream memory consolidation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from radbot.tools.memory.memory_consolidation import (
    SIMILARITY_THRESHOLD,
    _cluster,
    _cosine,
    _payload_is_low_trust,
    run_dream,
)


def _pt(pid: str, vector, payload=None):
    return SimpleNamespace(id=pid, vector=vector, payload=payload or {})


def test_cosine_identical():
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_payload_low_trust_detection():
    assert _payload_is_low_trust({"trust": "low"}) is True
    assert _payload_is_low_trust({"source": "alert"}) is True
    assert _payload_is_low_trust({"source": "webhook"}) is True
    assert _payload_is_low_trust({"trust": "high"}) is False
    assert _payload_is_low_trust({}) is False


def test_cluster_groups_near_duplicates():
    v1 = [1.0, 0.0, 0.0]
    v1_close = [0.999, 0.01, 0.0]
    v_far = [0.0, 1.0, 0.0]
    pts = [_pt("a", v1), _pt("b", v1_close), _pt("c", v_far)]
    clusters = _cluster(pts)
    # Expect one cluster of 2 and one cluster of 1
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]


class _FakeClient:
    def __init__(self, points):
        self._points = points
        self.upserts = []
        self.payload_updates = []
        # signal at scroll: returns (points, None) on first call, empty on second
        self._served = False

    def scroll(self, **_kwargs):
        if self._served:
            return [], None
        self._served = True
        return list(self._points), None

    def upsert(self, collection_name, points):
        self.upserts.append((collection_name, list(points)))

    def set_payload(self, collection_name, payload, points):
        self.payload_updates.append((collection_name, payload, list(points)))


def _service(points):
    svc = MagicMock()
    svc.collection_name = "test_col"
    svc.client = _FakeClient(points)
    return svc


@pytest.mark.asyncio
async def test_dream_consolidates_duplicates():
    v = [1.0, 0.0, 0.0]
    v_close = [0.9995, 0.01, 0.0]
    v_other = [0.0, 1.0, 0.0]
    pts = [
        _pt("a", v, {"source_agent": "beto", "text": "fact A longer"}),
        _pt("b", v_close, {"source_agent": "beto", "text": "fact A"}),
        _pt("c", v_other, {"source_agent": "beto", "text": "different"}),
    ]
    svc = _service(pts)
    result = await run_dream(memory_service=svc)

    assert result["scanned"] == 3
    assert result["consolidated"] == 1
    assert result["archived"] == 2
    # Singleton cluster for the different point — no consolidation of it.
    assert result["clusters"] == 2
    # One upsert for the consolidated point, one set_payload archiving 2 ids.
    assert len(svc.client.upserts) == 1
    assert len(svc.client.payload_updates) == 1
    _, archive_payload, archive_ids = svc.client.payload_updates[0]
    assert archive_payload["archived"] is True
    assert set(archive_ids) == {"a", "b"}


@pytest.mark.asyncio
async def test_dream_skips_low_trust_from_promotion_candidates():
    v = [1.0, 0.0, 0.0]
    pts = [
        _pt("a", v, {"source_agent": "beto", "memory_type": "important", "trust": "low"}),
        _pt("b", [0.0, 1.0, 0.0], {"source_agent": "beto", "memory_type": "important"}),
    ]
    svc = _service(pts)
    result = await run_dream(memory_service=svc, promote=True)
    # The low-trust singleton must not be a promotion candidate.
    ids = result.get("promotion_candidate_ids", [])
    assert "a" not in ids
    assert "b" in ids
    assert result["skipped_low_trust"] == 1


@pytest.mark.asyncio
async def test_dream_promote_flag_is_noop_on_durable_storage():
    v = [1.0, 0.0, 0.0]
    pts = [_pt("a", v, {"source_agent": "beto", "memory_type": "important"})]
    svc = _service(pts)
    result = await run_dream(memory_service=svc, promote=True)
    # promote=True must NOT cause consolidated writes for a singleton.
    assert svc.client.upserts == []
    assert svc.client.payload_updates == []
    # Candidate id should be surfaced but nothing written.
    assert result["promotion_candidate_ids"] == ["a"]


@pytest.mark.asyncio
async def test_dream_dry_run_skips_writes():
    v = [1.0, 0.0, 0.0]
    v_close = [0.999, 0.01, 0.0]
    pts = [
        _pt("a", v, {"source_agent": "beto", "text": "x"}),
        _pt("b", v_close, {"source_agent": "beto", "text": "y"}),
    ]
    svc = _service(pts)
    result = await run_dream(memory_service=svc, dry_run=True)
    assert result["consolidated"] == 1
    assert result["archived"] == 2
    assert svc.client.upserts == []
    assert svc.client.payload_updates == []


@pytest.mark.asyncio
async def test_dream_no_service_returns_skipped():
    # monkeypatch factory to return None
    from radbot.tools.memory import memory_consolidation as mc

    original = mc._get_memory_service
    mc._get_memory_service = lambda: None
    try:
        result = await run_dream()
        assert result["status"] == "skipped"
    finally:
        mc._get_memory_service = original


def test_threshold_is_reasonable():
    # Sanity: threshold should reject clearly distinct vectors.
    assert _cosine([1.0, 0.0], [0.5, 0.5]) < SIMILARITY_THRESHOLD
