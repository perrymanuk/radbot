"""Dream — scheduled memory consolidation over Qdrant.

Runs periodically (via scheduler defaults) to:
  * scan recent memory points,
  * cluster near-duplicates by cosine similarity over already-stored vectors
    (no re-embedding),
  * write one `memory_type="consolidated"` point per cluster referencing the
    originals via `merged_from`,
  * mark original duplicates with `archived=true` (soft archive — never
    delete, keep for audit),
  * surface promotion *candidates* (high-signal points) without touching
    durable storage.

eTAMP safety: points flagged `trust="low"` or with `source` in
{"alert","webhook"} are NEVER eligible for promotion candidacy, and
promotion itself is gated behind an explicit `promote=True` flag which
is intentionally a no-op in this first cut — promotion requires user
confirmation via a separate (not-yet-built) flow.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.97
LOW_TRUST_SOURCES = {"alert", "webhook"}


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _payload_is_low_trust(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    if str(payload.get("trust", "")).lower() == "low":
        return True
    if str(payload.get("source", "")).lower() in LOW_TRUST_SOURCES:
        return True
    return False


def _group_key(payload: Dict[str, Any]) -> str:
    return str(payload.get("source_agent") or payload.get("memory_type") or "_")


def _cluster(points: List[Any]) -> List[List[Any]]:
    """Greedy single-link cluster over cosine similarity ≥ threshold.

    Each `point` is expected to have `.id`, `.vector`, `.payload`.
    """
    clusters: List[List[Any]] = []
    for p in points:
        vec = getattr(p, "vector", None)
        if not vec:
            continue
        placed = False
        for cluster in clusters:
            head_vec = getattr(cluster[0], "vector", None)
            if head_vec and _cosine(vec, head_vec) >= SIMILARITY_THRESHOLD:
                cluster.append(p)
                placed = True
                break
        if not placed:
            clusters.append([p])
    return clusters


def _consolidated_payload(cluster: List[Any]) -> Dict[str, Any]:
    head = cluster[0]
    head_payload = dict(getattr(head, "payload", {}) or {})
    merged_from = [str(getattr(p, "id", "")) for p in cluster]
    texts = [str((getattr(p, "payload", {}) or {}).get("text", "")) for p in cluster]
    # Keep the longest textual content as the canonical consolidated text.
    canonical = max(texts, key=len) if texts else ""
    return {
        "text": canonical,
        "memory_type": "consolidated",
        "source_agent": head_payload.get("source_agent"),
        "user_id": head_payload.get("user_id"),
        "merged_from": merged_from,
        "merged_count": len(cluster),
        "promoted": False,
        "consolidated_at": datetime.now(timezone.utc).isoformat(),
    }


def _get_memory_service() -> Optional[Any]:
    """Lazy singleton accessor — returns None if Qdrant is unavailable."""
    try:
        from radbot.memory.qdrant_memory import QdrantMemoryService

        return QdrantMemoryService()
    except Exception as e:  # pragma: no cover - infra failure
        logger.warning("Dream: memory service unavailable: %s", e)
        return None


async def run_dream(
    *,
    lookback_hours: int = 24,
    promote: bool = False,
    dry_run: bool = False,
    memory_service: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run a single Dream pass.

    Args:
        lookback_hours: scan window for episodic points.
        promote: intentionally a no-op — promotion requires user confirmation
            (eTAMP). If True, promotion *candidates* are still only returned,
            not written to durable storage.
        dry_run: compute clusters without writing to Qdrant.
        memory_service: injectable for tests.

    Returns:
        Counts dict with keys: scanned, clusters, consolidated, archived,
        promotion_candidates, skipped_low_trust.
    """
    svc = memory_service or _get_memory_service()
    if svc is None:
        return {
            "scanned": 0,
            "clusters": 0,
            "consolidated": 0,
            "archived": 0,
            "promotion_candidates": 0,
            "skipped_low_trust": 0,
            "status": "skipped",
        }

    from qdrant_client import (
        models as qmodels,
    )  # local import keeps module importable without qdrant

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)

    scroll_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="timestamp",
                range=qmodels.DatetimeRange(gte=cutoff),
            ),
        ],
        must_not=[
            qmodels.FieldCondition(
                key="memory_type",
                match=qmodels.MatchValue(value="consolidated"),
            ),
            qmodels.FieldCondition(
                key="archived",
                match=qmodels.MatchValue(value=True),
            ),
        ],
    )

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

    scanned = len(points)
    skipped_low_trust = 0

    # Group by source_agent so we never cross-consolidate across scopes.
    groups: Dict[str, List[Any]] = {}
    for p in points:
        payload = getattr(p, "payload", {}) or {}
        groups.setdefault(_group_key(payload), []).append(p)

    consolidated_count = 0
    archived_count = 0
    cluster_count = 0
    promotion_candidates: List[str] = []

    for _group, members in groups.items():
        clusters = _cluster(members)
        for cluster in clusters:
            cluster_count += 1
            if len(cluster) < 2:
                # Single-point "cluster" — candidate for promotion only,
                # but not consolidated.
                only = cluster[0]
                payload = getattr(only, "payload", {}) or {}
                if _payload_is_low_trust(payload):
                    skipped_low_trust += 1
                    continue
                if payload.get("memory_type") in {"important", "explicit"}:
                    promotion_candidates.append(str(getattr(only, "id", "")))
                continue

            # 2+ points → consolidate.
            new_payload = _consolidated_payload(cluster)
            archive_ids = [str(getattr(p, "id", "")) for p in cluster]

            if dry_run:
                consolidated_count += 1
                archived_count += len(archive_ids)
                continue

            try:
                new_point = qmodels.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=list(getattr(cluster[0], "vector", []) or []),
                    payload=new_payload,
                )
                svc.client.upsert(
                    collection_name=svc.collection_name,
                    points=[new_point],
                )
                consolidated_count += 1
            except Exception as e:
                logger.warning("Dream: upsert failed: %s", e)
                continue

            try:
                svc.client.set_payload(
                    collection_name=svc.collection_name,
                    payload={"archived": True, "archived_by": "dream"},
                    points=archive_ids,
                )
                archived_count += len(archive_ids)
            except Exception as e:
                logger.warning("Dream: archive payload update failed: %s", e)

    result = {
        "scanned": scanned,
        "clusters": cluster_count,
        "consolidated": consolidated_count,
        "archived": archived_count,
        "promotion_candidates": len(promotion_candidates),
        "skipped_low_trust": skipped_low_trust,
        "status": "ok",
    }
    if promote:
        # Intentional no-op: returning candidates only. Actual promotion to
        # durable storage requires user confirmation via a separate flow.
        result["promotion_candidate_ids"] = promotion_candidates
        logger.info(
            "Dream: promote=True requested but no-op in this build "
            "(returning %d candidate ids only)",
            len(promotion_candidates),
        )
    logger.info("Dream pass complete: %s", result)
    return result
