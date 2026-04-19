
"""
Health check endpoints for RadBot monitoring.
"""

import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from radbot.config.config_loader import config_loader
from radbot.db.connection import get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class ComponentStatus(BaseModel):
    status: str
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str
    components: Dict[str, ComponentStatus]
    version: str = "0.1.0"


@router.get("/health/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
@router.get("/health/detailed", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def detailed_health_check(response: Response):
    """
    Perform a deep health check of all critical components.
    Returns 503 Service Unavailable if any critical component is down.
    """
    components = {}
    overall_status = "ok"
    
    # 1. Check Database (Critical)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        components["database"] = ComponentStatus(status="ok")
    except Exception as e:
        logger.error(f"Health check failed for database: {e}")
        components["database"] = ComponentStatus(status="error", message=str(e))
        overall_status = "error"

    # 2. Check Agent Initialization (Critical)
    try:
        from radbot.agent.agent_core import root_agent
        if root_agent:
            components["agent"] = ComponentStatus(status="ok", details={"name": root_agent.name})
        else:
            components["agent"] = ComponentStatus(status="error", message="Root agent not initialized")
            overall_status = "error"
    except ImportError:
        components["agent"] = ComponentStatus(status="error", message="Agent module not found")
        overall_status = "error"
    except Exception as e:
        components["agent"] = ComponentStatus(status="error", message=str(e))
        overall_status = "error"

    # 3. Check Memory Service (Qdrant) (Non-critical for startup, but important)
    try:
        from radbot.agent.agent_core import memory_service
        if memory_service and hasattr(memory_service, "client"):
            # Simple check: get collections
            collections = memory_service.client.get_collections()
            components["memory"] = ComponentStatus(
                status="ok",
                details={"collections": [c.name for c in collections.collections]}
            )
        else:
            components["memory"] = ComponentStatus(status="warning", message="Memory service not initialized")
    except Exception as e:
        logger.warning(f"Health check failed for memory service: {e}")
        components["memory"] = ComponentStatus(status="error", message=str(e))
        # Decide if this should fail overall health. Usually, apps can run without vector DB for some features.
        # Let's keep it as error but maybe not fail the whole app if it's just a readiness probe for traffic?
        # Actually, for an agent, memory is pretty critical. Let's fail it.
        overall_status = "error"

    # Determine final status code
    if overall_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return HealthResponse(status=overall_status, components=components)
