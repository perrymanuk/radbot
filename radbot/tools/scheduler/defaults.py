"""Default scheduler jobs for proactive primitives (Dream + Heartbeat).

Registered as native APScheduler cron jobs inside `SchedulerEngine.start()`
so the primitives run as deterministic Python routines rather than
LLM-prompt-driven scheduled tasks. Config-gated via `config:dream` and
`config:heartbeat` sections (both enabled by default).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

DREAM_JOB_ID = "__dream__"
HEARTBEAT_JOB_ID = "__heartbeat__"

DEFAULT_DREAM_CRON = "0 3 * * *"       # 03:00 daily
DEFAULT_HEARTBEAT_CRON = "0 8 * * *"    # 08:00 daily


def _get_section(section: str) -> Dict[str, Any]:
    try:
        from radbot.config.config_loader import config_loader

        val = config_loader.get_config().get(section) or {}
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _cron_trigger(expr: str) -> CronTrigger:
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"invalid cron expression: {expr!r}")
    return CronTrigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
    )


async def _run_dream_job() -> None:
    """APScheduler entry-point for the Dream pass."""
    try:
        from radbot.tools.memory.memory_consolidation import run_dream

        cfg = _get_section("dream")
        lookback = int(cfg.get("lookback_hours", 24))
        promote = bool(cfg.get("promote", False))
        result = await run_dream(lookback_hours=lookback, promote=promote)
        logger.info("Dream job finished: %s", result)
    except Exception as e:
        logger.error("Dream job failed: %s", e, exc_info=True)


async def _run_heartbeat_job() -> None:
    """APScheduler entry-point for the Heartbeat digest."""
    try:
        from radbot.tools.heartbeat.delivery import deliver_digest
        from radbot.tools.heartbeat.digest import assemble_digest

        cfg = _get_section("heartbeat")
        horizon = int(cfg.get("horizon_hours", 24))
        markdown = await assemble_digest(horizon_hours=horizon)
        delivered = await deliver_digest(markdown)
        logger.info(
            "Heartbeat job finished: delivered=%s, length=%d",
            delivered,
            len(markdown),
        )
    except Exception as e:
        logger.error("Heartbeat job failed: %s", e, exc_info=True)


def register_default_jobs(engine: Any) -> None:
    """Register Dream + Heartbeat jobs on the given SchedulerEngine.

    Safe to call multiple times — replaces existing jobs by id. Never
    raises; logs and continues on error so scheduler startup is not
    blocked by a misconfigured primitive.
    """
    scheduler = getattr(engine, "_scheduler", None)
    if scheduler is None:
        logger.warning("register_default_jobs: engine has no _scheduler, skipping")
        return

    specs = [
        ("dream", DREAM_JOB_ID, DEFAULT_DREAM_CRON, _run_dream_job, "Dream (memory consolidation)"),
        ("heartbeat", HEARTBEAT_JOB_ID, DEFAULT_HEARTBEAT_CRON, _run_heartbeat_job, "Heartbeat (morning digest)"),
    ]

    for section, job_id, default_cron, callable_, label in specs:
        cfg = _get_section(section)
        enabled = cfg.get("enabled", True)
        if not enabled:
            logger.info("%s disabled via config:%s — not registering job", label, section)
            continue
        cron_expr = str(cfg.get("cron_expression") or default_cron)
        try:
            trigger = _cron_trigger(cron_expr)
        except Exception as e:
            logger.error("%s: bad cron %r (%s) — not registering", label, cron_expr, e)
            continue

        try:
            existing = scheduler.get_job(job_id)
            if existing:
                existing.remove()
            scheduler.add_job(
                callable_,
                trigger=trigger,
                id=job_id,
                name=label,
                replace_existing=True,
            )
            logger.info("%s registered (cron=%s)", label, cron_expr)
        except Exception as e:
            logger.error("%s: failed to register job: %s", label, e)
