"""SemanticDistiller — distills episodic memories into implicit rules.

Based on Exploration EX8 (council-approved constraints):
  1. Chronological trigger: fetch episodic memories newer than the last
     run's cursor; skip unless at least `min_episodes` are available.
  2. Pydantic AI enforces the strict output schema (`DistilledRule` with a
     25-word-capped statement, mandatory `relation_to_prior`, and a
     `supersedes` list for revisions).
  3. Dead-letter queue via a `distillation_attempts` counter in the
     episode payload — episodes that fail `max_attempts` times are
     flagged `status: dead_letter` and skipped on future runs.
  4. Idempotent 3-step state machine with a `job_run_id` batch tag,
     because Qdrant lacks multi-document transactions:
        step 2: upsert new implicit rules as `status: pending` + batch tag
        step 3: flip old rules → `inactive`, episodes → `archived`
        step 4: flip new rules → `active`
     A matching `rollback_distillation(job_run_id)` helper reverts any
     partial state left behind by a mid-run crash.

Never issues a physical `DELETE` to Qdrant — all updates are soft.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CURSOR_POINT_ID = "00000000-0000-0000-0000-000000000d15"  # deterministic UUID
CURSOR_MEMORY_TYPE = "distiller_cursor"
DEFAULT_MIN_EPISODES = 5
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_PRIOR_RULES_K = 10
DEFAULT_MODEL = "gemini-2.5-flash"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_timestamp(payloads: List[Dict[str, Any]]) -> str:
    timestamps: List[str] = []
    for pl in payloads:
        ts = pl.get("timestamp")
        if isinstance(ts, str) and ts:
            timestamps.append(ts)
    if not timestamps:
        return _now_iso()
    return max(timestamps)


def _get_memory_service() -> Optional[Any]:
    try:
        from radbot.memory.qdrant_memory import QdrantMemoryService

        return QdrantMemoryService()
    except Exception as e:  # pragma: no cover - infra failure
        logger.warning("Distiller: memory service unavailable: %s", e)
        return None


def _read_cursor(svc: Any) -> Optional[str]:
    """Return ISO timestamp of last successful distillation, or None."""
    try:
        pts = svc.client.retrieve(
            collection_name=svc.collection_name,
            ids=[CURSOR_POINT_ID],
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        logger.warning("Distiller: cursor read failed: %s", e)
        return None
    if not pts:
        return None
    payload = getattr(pts[0], "payload", {}) or {}
    return payload.get("last_run_ts")


def _write_cursor(svc: Any, ts: str) -> None:
    from qdrant_client import models as qmodels

    try:
        vector_size = getattr(svc, "vector_size", None) or 768
        zero_vec = [0.0] * vector_size
        svc.client.upsert(
            collection_name=svc.collection_name,
            points=[
                qmodels.PointStruct(
                    id=CURSOR_POINT_ID,
                    vector=zero_vec,
                    payload={
                        "memory_type": CURSOR_MEMORY_TYPE,
                        "last_run_ts": ts,
                        "updated_at": _now_iso(),
                    },
                )
            ],
        )
    except Exception as e:
        logger.warning("Distiller: cursor write failed: %s", e)


def _scroll_candidate_episodes(
    svc: Any, since_ts: Optional[str], max_attempts: int
) -> List[Any]:
    from qdrant_client import models as qmodels

    must = [
        qmodels.FieldCondition(
            key="memory_class", match=qmodels.MatchValue(value="episodic")
        ),
    ]
    if since_ts:
        must.append(
            qmodels.FieldCondition(
                key="timestamp", range=qmodels.DatetimeRange(gt=since_ts)
            )
        )
    must_not = [
        qmodels.FieldCondition(
            key="status", match=qmodels.MatchValue(value="archived")
        ),
        qmodels.FieldCondition(
            key="status", match=qmodels.MatchValue(value="dead_letter")
        ),
        qmodels.FieldCondition(
            key="distillation_attempts",
            range=qmodels.Range(gt=max_attempts),
        ),
    ]
    scroll_filter = qmodels.Filter(must=must, must_not=must_not)

    points: List[Any] = []
    offset = None
    while True:
        batch, offset = svc.client.scroll(
            collection_name=svc.collection_name,
            scroll_filter=scroll_filter,
            limit=256,
            with_payload=True,
            with_vectors=True,
            offset=offset,
        )
        if not batch:
            break
        points.extend(batch)
        if offset is None:
            break
    # Stable chronological order for deterministic behavior.
    points.sort(key=lambda p: (getattr(p, "payload", {}) or {}).get("timestamp") or "")
    return points


def _centroid(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        for i in range(dim):
            acc[i] += v[i]
    n = float(len(vectors))
    return [x / n for x in acc]


def _fetch_prior_rules(svc: Any, centroid: List[float], k: int) -> List[Dict[str, Any]]:
    from qdrant_client import models as qmodels

    if not centroid:
        return []
    try:
        resp = svc.client.query_points(
            collection_name=svc.collection_name,
            query=centroid,
            query_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="memory_class",
                        match=qmodels.MatchValue(value="implicit"),
                    ),
                    qmodels.FieldCondition(
                        key="status", match=qmodels.MatchValue(value="active")
                    ),
                ]
            ),
            limit=k,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        logger.warning("Distiller: prior rules query failed: %s", e)
        return []
    out: List[Dict[str, Any]] = []
    for r in getattr(resp, "points", []) or []:
        payload = getattr(r, "payload", {}) or {}
        out.append({"id": str(getattr(r, "id", "")), "text": payload.get("text", "")})
    return out


def _increment_attempts(svc: Any, episode_ids: List[str]) -> None:
    """Increment `distillation_attempts` on each episode before LLM call."""
    if not episode_ids:
        return
    try:
        pts = svc.client.retrieve(
            collection_name=svc.collection_name,
            ids=episode_ids,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        logger.warning("Distiller: attempts read failed: %s", e)
        return
    for p in pts or []:
        pid = str(getattr(p, "id", ""))
        payload = getattr(p, "payload", {}) or {}
        attempts = int(payload.get("distillation_attempts") or 0) + 1
        try:
            svc.client.set_payload(
                collection_name=svc.collection_name,
                payload={
                    "distillation_attempts": attempts,
                    "last_distillation_attempt_at": _now_iso(),
                },
                points=[pid],
            )
        except Exception as e:
            logger.warning("Distiller: attempts write failed for %s: %s", pid, e)


def _flag_dead_letters(svc: Any, episode_ids: List[str], max_attempts: int) -> int:
    """Mark episodes whose attempts exceeded `max_attempts` as dead_letter."""
    if not episode_ids:
        return 0
    try:
        pts = svc.client.retrieve(
            collection_name=svc.collection_name,
            ids=episode_ids,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        logger.warning("Distiller: DLQ read failed: %s", e)
        return 0
    flagged = 0
    for p in pts or []:
        payload = getattr(p, "payload", {}) or {}
        attempts = int(payload.get("distillation_attempts") or 0)
        if attempts < max_attempts:
            continue
        pid = str(getattr(p, "id", ""))
        try:
            svc.client.set_payload(
                collection_name=svc.collection_name,
                payload={
                    "status": "dead_letter",
                    "dead_lettered_at": _now_iso(),
                },
                points=[pid],
            )
            flagged += 1
        except Exception as e:
            logger.warning("Distiller: DLQ write failed for %s: %s", pid, e)
    return flagged


def _embed_statement(svc: Any, text: str) -> List[float]:
    from radbot.memory.embedding import embed_text

    return embed_text(text, svc.embedding_model, is_query=False, source="agent_memory")


def _step2_insert_pending(
    svc: Any,
    rules: List[Any],
    job_run_id: str,
    source_agent: Optional[str],
    user_id: Optional[str],
) -> List[str]:
    """Step 2: upsert new rules as `status=pending` tagged with job_run_id."""
    from qdrant_client import models as qmodels

    point_ids: List[str] = []
    structs = []
    for rule in rules:
        pid = str(uuid.uuid4())
        point_ids.append(pid)
        vector = _embed_statement(svc, rule.statement)
        payload = {
            "text": rule.statement,
            "memory_class": "implicit",
            "memory_type": "distilled_rule",
            "status": "pending",
            "batch": job_run_id,
            "relation_to_prior": rule.relation_to_prior,
            "supersedes": list(rule.supersedes or []),
            "distilled_at": _now_iso(),
        }
        if source_agent:
            payload["source_agent"] = source_agent
        if user_id:
            payload["user_id"] = user_id
        structs.append(qmodels.PointStruct(id=pid, vector=vector, payload=payload))
    if structs:
        svc.client.upsert(collection_name=svc.collection_name, points=structs)
    return point_ids


def _step3_archive(
    svc: Any,
    superseded_ids: List[str],
    episode_ids: List[str],
    job_run_id: str,
) -> None:
    """Step 3: supersede old rules + archive source episodes."""
    now = _now_iso()
    if superseded_ids:
        try:
            svc.client.set_payload(
                collection_name=svc.collection_name,
                payload={
                    "status": "inactive",
                    "superseded_by_batch": job_run_id,
                    "superseded_at": now,
                },
                points=superseded_ids,
            )
        except Exception as e:
            logger.warning("Distiller: supersede failed: %s", e)
    if episode_ids:
        try:
            svc.client.set_payload(
                collection_name=svc.collection_name,
                payload={
                    "status": "archived",
                    "archived_by_batch": job_run_id,
                    "archived_at": now,
                },
                points=episode_ids,
            )
        except Exception as e:
            logger.warning("Distiller: archive failed: %s", e)


def _step4_activate(svc: Any, pending_ids: List[str], job_run_id: str) -> None:
    """Step 4: flip pending rules → active."""
    if not pending_ids:
        return
    try:
        svc.client.set_payload(
            collection_name=svc.collection_name,
            payload={
                "status": "active",
                "activated_at": _now_iso(),
                "activated_by_batch": job_run_id,
            },
            points=pending_ids,
        )
    except Exception as e:
        logger.warning("Distiller: activate failed: %s", e)


def rollback_distillation(
    job_run_id: str,
    *,
    memory_service: Optional[Any] = None,
) -> Dict[str, Any]:
    """Revert all mutations tagged with `job_run_id`.

    Safe to run multiple times. Used when a distillation pass crashes
    between step 2 and step 4.
    """
    from qdrant_client import models as qmodels

    svc = memory_service or _get_memory_service()
    if svc is None:
        return {"status": "skipped", "reason": "no_memory_service"}

    def _scroll_by(filter_: qmodels.Filter) -> List[str]:
        ids: List[str] = []
        offset = None
        while True:
            batch, offset = svc.client.scroll(
                collection_name=svc.collection_name,
                scroll_filter=filter_,
                limit=256,
                with_payload=False,
                with_vectors=False,
                offset=offset,
            )
            if not batch:
                break
            ids.extend(str(getattr(p, "id", "")) for p in batch)
            if offset is None:
                break
        return ids

    # Revert archived episodes + inactivated rules.
    superseded = _scroll_by(
        qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="superseded_by_batch",
                    match=qmodels.MatchValue(value=job_run_id),
                )
            ]
        )
    )
    archived = _scroll_by(
        qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="archived_by_batch",
                    match=qmodels.MatchValue(value=job_run_id),
                )
            ]
        )
    )
    pending_or_active = _scroll_by(
        qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="batch", match=qmodels.MatchValue(value=job_run_id)
                )
            ]
        )
    )

    if superseded:
        svc.client.set_payload(
            collection_name=svc.collection_name,
            payload={"status": "active"},
            points=superseded,
        )
    if archived:
        svc.client.set_payload(
            collection_name=svc.collection_name,
            payload={"status": "active"},
            points=archived,
        )
    if pending_or_active:
        svc.client.set_payload(
            collection_name=svc.collection_name,
            payload={"status": "rolled_back"},
            points=pending_or_active,
        )

    return {
        "status": "ok",
        "reverted_superseded": len(superseded),
        "reverted_archived": len(archived),
        "rolled_back_rules": len(pending_or_active),
    }


async def _run_pydantic_ai(
    agent: Any,
    prompt: str,
) -> Any:
    """Invoke pydantic-ai agent, returning the parsed DistillationResult."""
    result = await agent.run(prompt)
    # pydantic-ai returns a RunResult whose `.data` is the parsed model.
    return getattr(result, "data", result)


async def run_distillation(
    *,
    min_episodes: int = DEFAULT_MIN_EPISODES,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    prior_rules_k: int = DEFAULT_PRIOR_RULES_K,
    model: str = DEFAULT_MODEL,
    memory_service: Optional[Any] = None,
    agent: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run a single distillation pass.

    Returns a counters dict describing the outcome.
    """
    from ._distiller_schema import build_distiller_agent, format_prompt

    svc = memory_service or _get_memory_service()
    if svc is None:
        return {"status": "skipped", "reason": "no_memory_service"}

    since_ts = _read_cursor(svc)
    points = _scroll_candidate_episodes(svc, since_ts, max_attempts)

    scanned = len(points)
    if scanned < min_episodes:
        logger.info(
            "Distiller: %d episodes since %s (< min %d) — skipping",
            scanned,
            since_ts,
            min_episodes,
        )
        return {
            "status": "skipped",
            "reason": "below_threshold",
            "scanned": scanned,
            "min_episodes": min_episodes,
        }

    episode_ids = [str(getattr(p, "id", "")) for p in points]
    episode_payloads = [getattr(p, "payload", {}) or {} for p in points]
    vectors = [list(getattr(p, "vector", []) or []) for p in points]
    centroid = _centroid([v for v in vectors if v])

    # Representative metadata for tagging the new rules.
    source_agent = next(
        (pl.get("source_agent") for pl in episode_payloads if pl.get("source_agent")),
        None,
    )
    user_id = next(
        (pl.get("user_id") for pl in episode_payloads if pl.get("user_id")),
        None,
    )

    prior_rules = _fetch_prior_rules(svc, centroid, prior_rules_k)

    # Increment attempts BEFORE the LLM call so crashes still count.
    _increment_attempts(svc, episode_ids)

    episodes_for_prompt = [
        {"text": pl.get("text", ""), "timestamp": pl.get("timestamp", "")}
        for pl in episode_payloads
    ]
    prompt = format_prompt(episodes_for_prompt, prior_rules)

    llm_agent = agent or build_distiller_agent(model)
    try:
        result = await _run_pydantic_ai(llm_agent, prompt)
    except Exception as e:
        logger.warning("Distiller: pydantic-ai call failed: %s", e)
        flagged = _flag_dead_letters(svc, episode_ids, max_attempts)
        return {
            "status": "error",
            "reason": "llm_failure",
            "error": str(e),
            "scanned": scanned,
            "dead_lettered": flagged,
        }

    rules = list(getattr(result, "rules", []) or [])
    if not rules:
        # No rules produced — treat as a successful but empty pass.
        # Advance cursor so the same episodes aren't reconsidered forever.
        latest_ts = _latest_timestamp(episode_payloads)
        _write_cursor(svc, latest_ts)
        return {
            "status": "ok",
            "scanned": scanned,
            "rules_written": 0,
            "cursor": latest_ts,
        }

    superseded_ids: List[str] = []
    for r in rules:
        superseded_ids.extend(r.supersedes or [])

    if dry_run:
        return {
            "status": "dry_run",
            "scanned": scanned,
            "rules_proposed": len(rules),
            "supersede_count": len(superseded_ids),
        }

    job_run_id = str(uuid.uuid4())

    try:
        pending_ids = _step2_insert_pending(
            svc, rules, job_run_id, source_agent, user_id
        )
        _step3_archive(svc, superseded_ids, episode_ids, job_run_id)
        _step4_activate(svc, pending_ids, job_run_id)
    except Exception as e:
        logger.error(
            "Distiller: crash during 3-step update (job_run_id=%s): %s",
            job_run_id,
            e,
            exc_info=True,
        )
        rollback_distillation(job_run_id, memory_service=svc)
        return {
            "status": "error",
            "reason": "state_machine_crash",
            "job_run_id": job_run_id,
            "error": str(e),
            "scanned": scanned,
        }

    latest_ts = _latest_timestamp(episode_payloads)
    _write_cursor(svc, latest_ts)

    result_payload = {
        "status": "ok",
        "job_run_id": job_run_id,
        "scanned": scanned,
        "rules_written": len(pending_ids),
        "superseded": len(superseded_ids),
        "episodes_archived": len(episode_ids),
        "cursor": latest_ts,
    }
    logger.info("Distiller pass complete: %s", result_payload)
    return result_payload
