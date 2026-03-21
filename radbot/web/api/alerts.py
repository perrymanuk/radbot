"""FastAPI router for alert webhook and management endpoints.

Provides:
- POST /api/alerts/alertmanager — direct alertmanager webhook (secondary to ntfy)
- GET /api/alerts/ — list recent alerts
- GET /api/alerts/{alert_id} — alert detail
- POST /api/alerts/{alert_id}/dismiss — dismiss an alert
- CRUD for remediation policies
"""

import asyncio
import hashlib
import hmac
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ── Alertmanager webhook (secondary ingestion path) ───────────


@router.post("/alertmanager")
async def alertmanager_webhook(request: Request):
    """Receive an alertmanager v4 webhook payload.

    Processes each alert in the ``alerts[]`` array through the
    remediation pipeline.  Returns 202 immediately.
    """
    # Optional HMAC verification
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        secret = store.get("alertmanager_webhook_secret") if store.available else None
    except Exception:
        secret = None

    if secret:
        raw_body = await request.body()
        sig_header = (
            request.headers.get("X-Signature-256", "")
            or request.headers.get("X-Hub-Signature-256", "")
        )
        sig = sig_header.replace("sha256=", "")
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not sig or not hmac.compare_digest(expected, sig):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    alerts = payload.get("alerts", [])
    if not alerts:
        return {"status": "accepted", "alerts_received": 0}

    logger.info(
        f"Alertmanager webhook: received {len(alerts)} alerts "
        f"(status={payload.get('status')}, receiver={payload.get('receiver')})"
    )

    # Ensure fingerprints exist
    for alert in alerts:
        if not alert.get("fingerprint"):
            alert["fingerprint"] = str(uuid.uuid4())

    # Process asynchronously
    from radbot.tools.alertmanager.processor import process_alert_from_payload

    for alert in alerts:
        asyncio.create_task(process_alert_from_payload(alert))

    return {"status": "accepted", "alerts_received": len(alerts)}


# ── Alert management endpoints ────────────────────────────────


def _require_admin(request: Request):
    """Verify admin bearer token. Reuses the admin auth logic."""
    import os

    from radbot.credentials.store import get_credential_store

    expected = os.environ.get("RADBOT_ADMIN_TOKEN", "")
    if not expected:
        try:
            from radbot.config.config_loader import config_loader

            expected = config_loader.get_config().get("admin_token") or ""
        except Exception:
            pass
    if not expected:
        raise HTTPException(503, "Admin API disabled")

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and auth[7:] == expected:
        return
    raise HTTPException(401, "Invalid or missing admin bearer token")


@router.get("/")
async def list_alerts_endpoint(
    request: Request,
    status: Optional[str] = None,
    alertname: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    """List recent alert events with pagination."""
    _require_admin(request)
    try:
        from radbot.tools.alertmanager.db import count_alerts, list_alerts

        alerts = list_alerts(status=status, alertname=alertname, limit=limit, offset=offset)
        total = count_alerts(status=status, alertname=alertname)
        return {"alerts": alerts, "count": len(alerts), "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Failed to list alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{alert_id}")
async def get_alert_endpoint(alert_id: str, request: Request):
    """Get alert detail by ID."""
    _require_admin(request)
    try:
        uuid.UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        from radbot.tools.alertmanager.db import get_alert

        alert = get_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return alert
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get alert: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str, request: Request):
    """Dismiss (ignore) an alert."""
    _require_admin(request)
    try:
        from radbot.tools.alertmanager.db import update_alert_status

        success = update_alert_status(alert_id, "ignored")
        if success:
            return {"status": "ok", "alert_id": alert_id}
        raise HTTPException(status_code=404, detail="Alert not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Remediation policy CRUD ───────────────────────────────────


class PolicyCreateBody(BaseModel):
    alertname_pattern: str
    action: str = "auto"
    severity: Optional[str] = None
    max_auto_remediations: int = 3
    window_minutes: int = 60
    timeout_seconds: int = 120
    max_llm_calls: int = 30
    metadata: Optional[dict] = None


class PolicyUpdateBody(BaseModel):
    alertname_pattern: Optional[str] = None
    action: Optional[str] = None
    severity: Optional[str] = None
    max_auto_remediations: Optional[int] = None
    window_minutes: Optional[int] = None
    timeout_seconds: Optional[int] = None
    max_llm_calls: Optional[int] = None
    enabled: Optional[bool] = None
    metadata: Optional[dict] = None


@router.get("/policies/")
async def list_policies_endpoint(request: Request):
    """List all remediation policies."""
    _require_admin(request)
    try:
        from radbot.tools.alertmanager.db import list_policies

        policies = list_policies()
        return {"policies": policies, "count": len(policies)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/policies/")
async def create_policy_endpoint(body: PolicyCreateBody, request: Request):
    """Create a remediation policy."""
    _require_admin(request)
    try:
        from radbot.tools.alertmanager.db import create_policy

        result = create_policy(
            alertname_pattern=body.alertname_pattern,
            action=body.action,
            severity=body.severity,
            max_auto_remediations=body.max_auto_remediations,
            window_minutes=body.window_minutes,
            timeout_seconds=body.timeout_seconds,
            max_llm_calls=body.max_llm_calls,
            metadata=body.metadata,
        )
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/policies/{policy_id}")
async def update_policy_endpoint(
    policy_id: str, body: PolicyUpdateBody, request: Request
):
    """Update a remediation policy."""
    _require_admin(request)
    try:
        uuid.UUID(policy_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        from radbot.tools.alertmanager.db import update_policy

        fields = {k: v for k, v in body.dict().items() if v is not None}
        success = update_policy(policy_id, **fields)
        if success:
            return {"status": "ok", "policy_id": policy_id}
        raise HTTPException(status_code=404, detail="Policy not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/policies/{policy_id}")
async def delete_policy_endpoint(policy_id: str, request: Request):
    """Delete a remediation policy."""
    _require_admin(request)
    try:
        uuid.UUID(policy_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    try:
        from radbot.tools.alertmanager.db import delete_policy

        success = delete_policy(policy_id)
        if success:
            return {"status": "ok", "policy_id": policy_id}
        raise HTTPException(status_code=404, detail="Policy not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
