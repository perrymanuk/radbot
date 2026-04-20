"""Unit tests for the SemanticDistiller worker (EX8/PT32)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from radbot.tools.memory._distiller_schema import (
    DistilledRule,
    DistillationResult,
    MAX_STATEMENT_WORDS,
)
from radbot.tools.memory.semantic_distiller import (
    CURSOR_POINT_ID,
    rollback_distillation,
    run_distillation,
)


# ---------------------------------------------------------------------------
# Schema validators
# ---------------------------------------------------------------------------


def test_statement_word_cap_rejects_over_25():
    words = " ".join(["word"] * (MAX_STATEMENT_WORDS + 1))
    with pytest.raises(ValueError):
        DistilledRule(statement=words, relation_to_prior="novel", supersedes=[])


def test_statement_word_cap_accepts_exactly_25():
    words = " ".join(["word"] * MAX_STATEMENT_WORDS)
    r = DistilledRule(statement=words, relation_to_prior="novel", supersedes=[])
    assert r.statement == words


def test_refines_requires_supersedes():
    with pytest.raises(ValueError):
        DistilledRule(statement="rule", relation_to_prior="refines", supersedes=[])


def test_contradicts_requires_supersedes():
    with pytest.raises(ValueError):
        DistilledRule(
            statement="rule", relation_to_prior="contradicts", supersedes=[]
        )


def test_novel_allows_empty_supersedes():
    r = DistilledRule(statement="rule", relation_to_prior="novel", supersedes=[])
    assert r.supersedes == []


# ---------------------------------------------------------------------------
# Fake Qdrant client
# ---------------------------------------------------------------------------


def _ep(pid: str, ts: str, text: str = "ep", attempts: int = 0, status: Optional[str] = None):
    payload = {
        "text": text,
        "memory_class": "episodic",
        "timestamp": ts,
        "distillation_attempts": attempts,
        "source_agent": "beto",
        "user_id": "web_user",
    }
    if status:
        payload["status"] = status
    return SimpleNamespace(id=pid, vector=[1.0, 0.0, 0.0], payload=payload)


class _FakeQdrant:
    def __init__(self, episodes: List[Any], prior_rules: Optional[List[Any]] = None):
        # Episodes are stored by id in a dict so set_payload mutates them.
        self._points: Dict[str, Any] = {p.id: p for p in episodes}
        # A mutable "cursor" holder.
        self._cursor: Dict[str, Any] = {}
        self._prior_rules = prior_rules or []
        self.upserts: List[Any] = []
        self.payload_updates: List[Dict[str, Any]] = []
        self._scroll_served = False
        self._retrieve_calls: List[List[str]] = []

    def scroll(self, *, scroll_filter=None, offset=None, **kwargs):
        # Pagination: if caller passes an offset (truthy), we've already served.
        if offset:
            return [], None
        must = list(getattr(scroll_filter, "must", None) or [])
        must_not = list(getattr(scroll_filter, "must_not", None) or [])

        def _match_eq(cond, payload):
            key = getattr(cond, "key", None)
            match = getattr(cond, "match", None)
            if match is not None and hasattr(match, "value"):
                return payload.get(key) == match.value
            return None

        eligible = []
        for p in self._points.values():
            payload = p.payload or {}
            ok = True
            for c in must:
                m = _match_eq(c, payload)
                if m is False:
                    ok = False
                    break
                # Ignore range/other conditions in this fake.
            if not ok:
                continue
            for c in must_not:
                if _match_eq(c, payload) is True:
                    ok = False
                    break
            if not ok:
                continue
            eligible.append(p)
        return eligible, None

    def retrieve(self, *, ids, **kwargs):
        self._retrieve_calls.append(list(ids))
        out = []
        for pid in ids:
            if pid == CURSOR_POINT_ID:
                if self._cursor:
                    out.append(
                        SimpleNamespace(id=pid, payload=dict(self._cursor), vector=None)
                    )
                continue
            if pid in self._points:
                p = self._points[pid]
                out.append(
                    SimpleNamespace(id=p.id, payload=dict(p.payload), vector=p.vector)
                )
        return out

    def upsert(self, *, collection_name, points):
        for p in points:
            # Cursor point tracked separately.
            if getattr(p, "id", None) == CURSOR_POINT_ID:
                self._cursor = dict(p.payload or {})
                continue
            self._points[p.id] = SimpleNamespace(
                id=p.id, vector=list(p.vector or []), payload=dict(p.payload or {})
            )
        self.upserts.append(list(points))

    def set_payload(self, *, collection_name, payload, points):
        self.payload_updates.append(
            {"payload": dict(payload), "points": list(points)}
        )
        for pid in points:
            if pid in self._points:
                self._points[pid].payload.update(payload)

    def query_points(self, *, query, query_filter=None, limit=10, **kwargs):
        pts = [
            SimpleNamespace(id=r.id, payload=dict(r.payload), score=1.0)
            for r in self._prior_rules
        ][:limit]
        return SimpleNamespace(points=pts)


def _service(episodes, prior_rules=None):
    svc = MagicMock()
    svc.collection_name = "test_col"
    svc.client = _FakeQdrant(episodes, prior_rules)
    svc.vector_size = 3
    svc.embedding_model = None
    return svc


# Patch embedding to avoid network.
@pytest.fixture(autouse=True)
def _patch_embed(monkeypatch):
    import radbot.tools.memory.semantic_distiller as sd

    monkeypatch.setattr(sd, "_embed_statement", lambda svc, text: [0.5, 0.5, 0.0])


# ---------------------------------------------------------------------------
# Fake pydantic-ai agent
# ---------------------------------------------------------------------------


class _FakeAgent:
    def __init__(self, rules=None, raise_exc: Optional[Exception] = None):
        self._rules = rules or []
        self._exc = raise_exc
        self.calls = 0

    async def run(self, prompt: str):
        self.calls += 1
        if self._exc:
            raise self._exc
        return SimpleNamespace(data=DistillationResult(rules=self._rules))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_when_below_threshold():
    svc = _service([_ep(f"e{i}", f"2026-04-20T00:0{i}:00+00:00") for i in range(3)])
    result = await run_distillation(
        memory_service=svc, agent=_FakeAgent(rules=[]), min_episodes=5
    )
    assert result["status"] == "skipped"
    assert result["reason"] == "below_threshold"
    # No writes occurred.
    assert svc.client.upserts == []
    assert svc.client.payload_updates == []


@pytest.mark.asyncio
async def test_happy_path_writes_rule_and_archives():
    episodes = [_ep(f"e{i}", f"2026-04-20T00:0{i}:00+00:00") for i in range(5)]
    svc = _service(episodes)
    rule = DistilledRule(
        statement="user prefers terse replies over verbose explanations",
        relation_to_prior="novel",
        supersedes=[],
    )
    agent = _FakeAgent(rules=[rule])
    result = await run_distillation(memory_service=svc, agent=agent, min_episodes=5)

    assert result["status"] == "ok"
    assert result["rules_written"] == 1
    assert result["episodes_archived"] == 5

    # Every source episode ended up with status=archived.
    for ep in episodes:
        assert svc.client._points[ep.id].payload.get("status") == "archived"

    # The new implicit rule is active.
    rule_points = [
        p
        for p in svc.client._points.values()
        if (p.payload or {}).get("memory_class") == "implicit"
    ]
    assert len(rule_points) == 1
    assert rule_points[0].payload["status"] == "active"
    assert rule_points[0].payload["batch"] == result["job_run_id"]

    # Cursor was written.
    assert svc.client._cursor.get("last_run_ts")


@pytest.mark.asyncio
async def test_llm_failure_increments_attempts_no_writes():
    episodes = [_ep(f"e{i}", f"2026-04-20T00:0{i}:00+00:00") for i in range(5)]
    svc = _service(episodes)
    agent = _FakeAgent(raise_exc=RuntimeError("validator rejected 26-word statement"))

    result = await run_distillation(memory_service=svc, agent=agent, min_episodes=5)

    assert result["status"] == "error"
    assert result["reason"] == "llm_failure"
    # Attempts incremented to 1.
    for ep in episodes:
        assert svc.client._points[ep.id].payload["distillation_attempts"] == 1
    # No new implicit rule written.
    assert not any(
        (p.payload or {}).get("memory_class") == "implicit"
        for p in svc.client._points.values()
    )
    # Below max_attempts → no DLQ flags yet.
    for ep in episodes:
        assert svc.client._points[ep.id].payload.get("status") != "dead_letter"


@pytest.mark.asyncio
async def test_dlq_flags_after_max_attempts():
    # Episodes already at attempts=3 so this 4th failure pushes them over.
    episodes = [
        _ep(f"e{i}", f"2026-04-20T00:0{i}:00+00:00", attempts=3) for i in range(5)
    ]
    svc = _service(episodes)
    agent = _FakeAgent(raise_exc=RuntimeError("LLM down"))

    result = await run_distillation(
        memory_service=svc, agent=agent, min_episodes=5, max_attempts=3
    )

    assert result["status"] == "error"
    assert result["dead_lettered"] == 5
    for ep in episodes:
        assert svc.client._points[ep.id].payload["status"] == "dead_letter"


@pytest.mark.asyncio
async def test_rollback_reverts_tagged_mutations():
    episodes = [_ep(f"e{i}", f"2026-04-20T00:0{i}:00+00:00") for i in range(5)]
    svc = _service(episodes)
    rule = DistilledRule(
        statement="terse replies preferred",
        relation_to_prior="novel",
        supersedes=[],
    )
    agent = _FakeAgent(rules=[rule])
    result = await run_distillation(memory_service=svc, agent=agent, min_episodes=5)
    job_run_id = result["job_run_id"]

    # Simulate rollback call.
    rb = rollback_distillation(job_run_id, memory_service=svc)
    assert rb["status"] == "ok"

    # Episodes reverted to active.
    for ep in episodes:
        assert svc.client._points[ep.id].payload["status"] == "active"

    # The rule is marked rolled_back rather than active.
    rule_points = [
        p
        for p in svc.client._points.values()
        if (p.payload or {}).get("memory_class") == "implicit"
    ]
    assert rule_points and rule_points[0].payload["status"] == "rolled_back"
