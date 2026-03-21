"""Alert remediation pipeline.

Receives parsed alert payloads, checks policies, and dispatches
remediation tasks to Claude Code CLI.  Sends ntfy notifications at each stage.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

# ── Defaults for per-alert resource limits ────────────────────
DEFAULT_TIMEOUT_SECONDS = 300  # wall-clock timeout for Claude Code execution
DEFAULT_MAX_LLM_CALLS = 30  # unused now but kept for policy schema compat
RECONCILE_TIMEOUT_SECONDS = 180

logger = logging.getLogger(__name__)


async def _notify(
    title: str,
    message: str,
    priority: str = "default",
    tags: str = "robot",
) -> None:
    """Send an ntfy notification (best-effort, never raises)."""
    try:
        from radbot.tools.ntfy.ntfy_client import get_ntfy_client

        client = get_ntfy_client()
        if client:
            await client.publish(title=title, message=message, priority=priority, tags=tags)
    except Exception as e:
        logger.warning(f"ntfy notification failed: {e}")


async def _broadcast(payload: Dict[str, Any]) -> None:
    """Broadcast a message to all WebSocket connections (best-effort)."""
    try:
        from radbot.web.app import manager

        await manager.broadcast_to_all_sessions(payload)
    except Exception as e:
        logger.warning(f"WebSocket broadcast failed: {e}")


def _severity_to_priority(severity: Optional[str]) -> str:
    """Map alertmanager severity to ntfy priority."""
    mapping = {
        "critical": "max",
        "error": "high",
        "warning": "default",
        "info": "low",
    }
    return mapping.get((severity or "").lower(), "default")


def _get_nomad_env() -> str:
    """Return Nomad connection info for inclusion in Claude Code prompts."""
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("nomad", {})
    except Exception:
        cfg = {}

    addr = cfg.get("addr") or os.environ.get("NOMAD_ADDR") or ""
    token = cfg.get("token") or os.environ.get("NOMAD_TOKEN") or ""

    if not token:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                token = store.get("nomad_token") or ""
        except Exception:
            pass

    parts = []
    if addr:
        parts.append(f"NOMAD_ADDR={addr}")
    if token:
        parts.append(f"NOMAD_TOKEN={token}")
    return "\n".join(parts)


def _ensure_workspace() -> Optional[str]:
    """Clone or update hashi-homelab and return the local path."""
    try:
        from radbot.tools.claude_code.claude_code_tools import clone_repository

        result = clone_repository("perrymanuk", "hashi-homelab", "main")
        if result.get("status") == "success":
            return result["work_folder"]
        logger.warning(f"Failed to prepare workspace: {result.get('message')}")
    except Exception as e:
        logger.warning(f"Failed to prepare workspace: {e}")
    return None


async def process_alert_from_payload(alert: Dict[str, Any]) -> None:
    """Process a single alert from an alertmanager payload.

    This is the main entry point called by both the ntfy handler and
    the direct webhook endpoint.

    Args:
        alert: A single alert object from the alertmanager ``alerts[]`` array,
               containing ``status``, ``labels``, ``annotations``, ``fingerprint``.
    """
    from radbot.tools.alertmanager.db import (
        count_recent_remediations,
        create_alert_event,
        get_matching_policy,
        get_unresolved_by_fingerprint,
        update_alert_status,
    )

    # Extract fields from alertmanager format
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    alertname = labels.get("alertname", "unknown")
    severity = labels.get("severity")
    instance = labels.get("instance")
    job_label = labels.get("job")
    summary = annotations.get("summary", "")
    description = annotations.get("description", "")
    fingerprint = alert.get("fingerprint", "")
    alert_status = alert.get("status", "firing")

    logger.info(
        f"Processing alert: {alertname} (status={alert_status}, "
        f"severity={severity}, instance={instance})"
    )

    # ── Handle resolved alerts ────────────────────────────────
    if alert_status == "resolved":
        existing = get_unresolved_by_fingerprint(fingerprint)
        if existing:
            update_alert_status(existing["alert_id"], "resolved")
            await _notify(
                title=f"Alert Resolved: {alertname}",
                message=f"Instance: {instance}\n{summary}",
                priority="low",
                tags="white_check_mark",
            )
            logger.info(f"Alert resolved: {alertname} ({existing['alert_id']})")

            # Trigger repo reconciliation if we made runtime changes
            if existing.get("remediation_action"):
                asyncio.create_task(
                    _reconcile_to_repo(
                        alertname=alertname,
                        remediation_action=existing["remediation_action"],
                        fingerprint=fingerprint,
                    )
                )
        else:
            logger.debug(f"Resolved alert {alertname} has no matching unresolved event")
        return

    # ── Deduplication ─────────────────────────────────────────
    existing = get_unresolved_by_fingerprint(fingerprint)
    if existing:
        logger.info(
            f"Alert {alertname} already being handled "
            f"(status={existing['status']}, id={existing['alert_id']})"
        )
        return

    # ── Create alert event ────────────────────────────────────
    event = create_alert_event(
        fingerprint=fingerprint,
        alertname=alertname,
        raw_payload=alert,
        severity=severity,
        instance=instance,
        job_label=job_label,
        summary=summary,
        description=description,
    )
    alert_id = event["alert_id"]

    await _notify(
        title=f"Alert Received: {alertname}",
        message=f"Severity: {severity}\nInstance: {instance}\n{summary}",
        priority=_severity_to_priority(severity),
        tags="warning,robot",
    )

    # ── Policy lookup ─────────────────────────────────────────
    policy = get_matching_policy(alertname, severity)

    if policy and policy["action"] == "ignore":
        update_alert_status(alert_id, "ignored")
        logger.info(f"Alert {alertname} ignored by policy")
        return

    # ── Rate limit check ──────────────────────────────────────
    if policy:
        max_remediations = policy["max_auto_remediations"]
        window = policy["window_minutes"]
    else:
        # Default policy: auto with rate limit
        max_remediations = 3
        window = 60

    recent_count = count_recent_remediations(alertname, window)
    if recent_count >= max_remediations:
        update_alert_status(
            alert_id, "failed",
            remediation_result=f"Rate limit exceeded: {recent_count}/{max_remediations} in {window}min",
        )
        await _notify(
            title=f"Rate Limit: {alertname}",
            message=(
                f"Auto-remediation limit reached ({recent_count}/{max_remediations} "
                f"in {window}min). Manual intervention needed.\n{summary}"
            ),
            priority="high",
            tags="rotating_light",
        )
        logger.warning(
            f"Rate limit exceeded for {alertname}: "
            f"{recent_count}/{max_remediations} in {window}min"
        )
        return

    # ── Investigating ─────────────────────────────────────────
    update_alert_status(alert_id, "analyzing")
    await _notify(
        title=f"Investigating: {alertname}",
        message=f"Severity: {severity}\nInstance: {instance}\n{summary}",
        tags="mag,robot",
    )

    # ── Construct remediation prompt ──────────────────────────
    nomad_env = _get_nomad_env()
    prompt = f"""INFRASTRUCTURE ALERT — AUTOMATIC REMEDIATION

Alert: {alertname}
Severity: {severity or 'unknown'}
Instance: {instance or 'unknown'}
Job: {job_label or 'unknown'}
Summary: {summary}
Description: {description}

Environment variables for Nomad API access:
{nomad_env}

You are in the hashi-homelab repo which contains all Nomad job specs.
Nomad job files are under nomad_jobs/ organized by category.

Investigate and fix this alert:
1. Query Nomad API via curl to check the job status and allocation logs:
   - curl -s -H "X-Nomad-Token: $NOMAD_TOKEN" $NOMAD_ADDR/v1/job/<jobname> | jq .
   - curl -s -H "X-Nomad-Token: $NOMAD_TOKEN" $NOMAD_ADDR/v1/job/<jobname>/allocations | jq .
   - For logs: curl -s -H "X-Nomad-Token: $NOMAD_TOKEN" "$NOMAD_ADDR/v1/client/fs/logs/<alloc_id>?task=<task>&type=stderr&plain=true"
2. Determine the root cause from logs and allocation status
3. Take corrective action:
   - For allocation crashes: restart via POST $NOMAD_ADDR/v1/job/<jobname>/allocations (stop alloc, Nomad reschedules)
   - For resource issues or config fixes: edit the Nomad job file in this repo, then submit:
     curl -s -H "X-Nomad-Token: $NOMAD_TOKEN" -X POST $NOMAD_ADDR/v1/jobs -d @<(nomad job run -output <jobfile>)
     Or: parse the HCL to JSON, POST to /v1/jobs/parse, then POST to /v1/job/<name>/plan and /v1/jobs
4. Verify the fix by checking status again
5. If you edited job files, commit with: git commit -am "fix: auto-remediation for {alertname} [radbot]"
6. Report concisely: what you found, what you did, and whether it worked"""

    # ── Resource limits ──────────────────────────────────────
    timeout = DEFAULT_TIMEOUT_SECONDS
    if policy:
        timeout = policy.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS

    # ── Prepare workspace ─────────────────────────────────────
    workspace = _ensure_workspace()
    if not workspace:
        update_alert_status(
            alert_id, "failed",
            remediation_result="Could not prepare hashi-homelab workspace",
        )
        await _notify(
            title=f"Workspace Error: {alertname}",
            message="Failed to clone/update hashi-homelab. Check GitHub App config.",
            priority="high",
            tags="x,robot",
        )
        return

    # ── Run remediation via Claude Code ───────────────────────
    update_alert_status(alert_id, "remediating")

    response_text = ""
    cc_session_id: Optional[str] = None
    try:
        from radbot.tools.claude_code.claude_code_client import ClaudeCodeClient

        cc = ClaudeCodeClient()
        logger.info(
            f"Alert {alertname}: starting Claude Code remediation "
            f"(timeout={timeout}s, cwd={workspace})"
        )

        result = await cc.run_execute(
            working_dir=workspace,
            prompt=prompt,
            timeout=timeout,
        )
        response_text = result.get("output", "")
        cc_session_id = result.get("session_id")
        return_code = result.get("return_code", -1)

        if result.get("status") == "success":
            update_alert_status(
                alert_id,
                "remediated",
                remediation_action=_extract_action_summary(response_text),
                remediation_result=response_text[:2000],
                remediation_session_id=cc_session_id,
            )
            await _notify(
                title=f"Remediated: {alertname}",
                message=response_text[:500],
                tags="white_check_mark,robot",
            )
            logger.info(f"Alert {alertname} remediated (id={alert_id})")
        else:
            error_detail = result.get("stderr") or response_text or "Unknown error"
            update_alert_status(
                alert_id,
                "failed",
                remediation_result=f"Claude Code exited {return_code}: {error_detail[:1500]}",
                remediation_session_id=cc_session_id,
            )
            await _notify(
                title=f"Remediation Failed: {alertname}",
                message=f"Claude Code exited {return_code}:\n{error_detail[:400]}",
                priority="high",
                tags="x,robot",
            )
            logger.warning(f"Alert {alertname} Claude Code failed (rc={return_code})")

    except Exception as e:
        error_msg = str(e)
        update_alert_status(
            alert_id,
            "failed",
            remediation_result=f"Remediation failed: {error_msg}",
            remediation_session_id=cc_session_id,
        )
        await _notify(
            title=f"Remediation Failed: {alertname}",
            message=f"Error: {error_msg}\n\nOriginal alert: {summary}",
            priority="high",
            tags="x,robot",
        )
        logger.error(f"Alert {alertname} remediation failed: {e}", exc_info=True)

    # ── Broadcast result ──────────────────────────────────────
    from datetime import datetime

    await _broadcast({
        "type": "alert_result",
        "alert_id": alert_id,
        "alertname": alertname,
        "severity": severity,
        "prompt": prompt[:500],
        "response": response_text[:1000],
        "timestamp": datetime.now().isoformat(),
    })


async def _reconcile_to_repo(
    alertname: str, remediation_action: str, fingerprint: str
) -> None:
    """Push committed changes from a remediation session.

    Called when an alert that radbot fixed is marked as resolved.
    Resumes the same Claude Code session so it has full context.
    """
    workspace = _ensure_workspace()
    if not workspace:
        logger.warning(f"Repo reconciliation skipped for {alertname}: no workspace")
        return

    prompt = f"""The alert "{alertname}" is now resolved. The following runtime changes were made:
{remediation_action}

If you already committed changes to the Nomad job file during remediation, push them now with git push.
If the remediation was just a restart (no file changes), report that no code changes were needed."""

    try:
        from radbot.tools.claude_code.claude_code_client import ClaudeCodeClient

        cc = ClaudeCodeClient()
        result = await cc.run_execute(
            working_dir=workspace,
            prompt=prompt,
            timeout=RECONCILE_TIMEOUT_SECONDS,
        )
        response = result.get("output", "")

        if result.get("status") == "success":
            await _notify(
                title=f"Repo Synced: {alertname}",
                message=response[:500],
                tags="package,robot",
            )
            logger.info(f"Repo reconciliation complete for {alertname}")
        else:
            logger.warning(
                f"Repo reconciliation for {alertname} exited {result.get('return_code')}: "
                f"{result.get('stderr', '')[:200]}"
            )
    except Exception as e:
        logger.error(f"Repo reconciliation failed for {alertname}: {e}", exc_info=True)
        await _notify(
            title=f"Repo Sync Failed: {alertname}",
            message=f"Could not sync changes to hashi-homelab: {e}",
            priority="high",
            tags="x,package",
        )


def _extract_action_summary(response: str) -> str:
    """Extract a brief action summary from the agent's response."""
    # Take first 200 chars as a rough summary
    if not response:
        return "No response from agent"
    lines = response.strip().splitlines()
    # Try to find a summary line
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in ("restarted", "updated", "fixed", "cloned", "pushed", "changed")):
            return line.strip()[:200]
    # Fall back to first non-empty line
    for line in lines:
        if line.strip():
            return line.strip()[:200]
    return response[:200]
