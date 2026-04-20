"""FunctionTool wrappers for the Nomad HTTP API.

These tools are added to the Axel execution agent so beto can route
infrastructure management requests to it.
"""

import logging
from typing import Any, Dict, List, Optional

from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)


def _get_client():
    """Lazy import to avoid import-time failures."""
    from radbot.tools.nomad.nomad_client import get_nomad_client

    client = get_nomad_client()
    if not client:
        return None
    return client


async def list_nomad_jobs(prefix: Optional[str] = None) -> Dict[str, Any]:
    """List Nomad jobs with their status.

    Args:
        prefix: Optional job ID prefix to filter results.

    Returns:
        A dict with status and a list of jobs (id, name, type, status,
        submit_time).
    """
    client = _get_client()
    if not client:
        return {"status": "error", "error": "Nomad integration not configured"}

    try:
        jobs = await client.list_jobs(prefix=prefix)
        summary = [
            {
                "id": j.get("ID"),
                "name": j.get("Name"),
                "type": j.get("Type"),
                "status": j.get("Status"),
                "status_description": j.get("StatusDescription"),
                "submit_time": j.get("SubmitTime"),
            }
            for j in jobs
        ]
        return {"status": "success", "jobs": summary, "count": len(summary)}
    except Exception as e:
        logger.error(f"list_nomad_jobs failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def get_nomad_job_status(job_id: str) -> Dict[str, Any]:
    """Get detailed status for a Nomad job including allocation health.

    Args:
        job_id: The Nomad job ID to check.

    Returns:
        A dict with job info, allocation summaries, and latest deployment.
    """
    client = _get_client()
    if not client:
        return {"status": "error", "error": "Nomad integration not configured"}

    try:
        job = await client.get_job(job_id)
        allocs = await client.get_job_allocations(job_id)

        # Summarize allocations
        alloc_summaries = []
        for a in allocs[:10]:  # Limit to 10 most recent
            tasks = {}
            for task_name, task_state in (a.get("TaskStates") or {}).items():
                events = task_state.get("Events") or []
                recent_events = [
                    {
                        "type": e.get("Type"),
                        "message": e.get("DisplayMessage"),
                        "time": e.get("Time"),
                    }
                    for e in events[-3:]  # Last 3 events per task
                ]
                tasks[task_name] = {
                    "state": task_state.get("State"),
                    "failed": task_state.get("Failed"),
                    "restarts": task_state.get("Restarts"),
                    "recent_events": recent_events,
                }

            alloc_summaries.append(
                {
                    "id": a.get("ID"),
                    "node_id": a.get("NodeID"),
                    "client_status": a.get("ClientStatus"),
                    "desired_status": a.get("DesiredStatus"),
                    "task_states": tasks,
                    "create_time": a.get("CreateTime"),
                }
            )

        # Get latest deployment if available
        deployment = None
        try:
            deployments = await client.get_job_deployments(job_id)
            if deployments:
                latest = deployments[0]
                deployment = {
                    "id": latest.get("ID"),
                    "status": latest.get("Status"),
                    "status_description": latest.get("StatusDescription"),
                }
        except Exception:
            pass

        return {
            "status": "success",
            "job": {
                "id": job.get("ID"),
                "name": job.get("Name"),
                "type": job.get("Type"),
                "status": job.get("Status"),
                "status_description": job.get("StatusDescription"),
                "task_groups": [
                    {
                        "name": tg.get("Name"),
                        "count": tg.get("Count"),
                        "tasks": [t.get("Name") for t in (tg.get("Tasks") or [])],
                    }
                    for tg in (job.get("TaskGroups") or [])
                ],
            },
            "allocations": alloc_summaries,
            "deployment": deployment,
        }
    except Exception as e:
        logger.error(f"get_nomad_job_status failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def get_nomad_allocation_logs(
    job_id: str,
    task: Optional[str] = None,
    log_type: str = "stderr",
    lines: int = 100,
) -> Dict[str, Any]:
    """Fetch recent logs from the latest allocation of a Nomad job.

    Args:
        job_id: The Nomad job ID.
        task: Specific task name. If omitted, uses the first task found.
        log_type: "stderr" or "stdout".
        lines: Approximate number of lines to return (used as byte hint).

    Returns:
        A dict with the log content and allocation/task metadata.
    """
    client = _get_client()
    if not client:
        return {"status": "error", "error": "Nomad integration not configured"}

    try:
        allocs = await client.get_job_allocations(job_id)
        if not allocs:
            return {
                "status": "error",
                "error": f"No allocations found for job {job_id}",
            }

        # Find the most recent running allocation, or fall back to latest
        running = [a for a in allocs if a.get("ClientStatus") == "running"]
        alloc = running[0] if running else allocs[0]
        alloc_id = alloc["ID"]

        # Determine task name
        if not task:
            task_states = alloc.get("TaskStates") or {}
            if task_states:
                task = next(iter(task_states))
            else:
                # Fall back to job definition
                job = await client.get_job(job_id)
                groups = job.get("TaskGroups") or []
                if groups and groups[0].get("Tasks"):
                    task = groups[0]["Tasks"][0].get("Name")
            if not task:
                return {
                    "status": "error",
                    "error": f"No tasks found for job {job_id}",
                }

        log_text = await client.get_alloc_logs(
            alloc_id=alloc_id,
            task=task,
            log_type=log_type,
        )

        # Trim to approximate line count
        log_lines = log_text.splitlines()
        if len(log_lines) > lines:
            log_lines = log_lines[-lines:]

        return {
            "status": "success",
            "job_id": job_id,
            "alloc_id": alloc_id,
            "task": task,
            "log_type": log_type,
            "lines": len(log_lines),
            "logs": "\n".join(log_lines),
        }
    except Exception as e:
        logger.error(f"get_nomad_allocation_logs failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def restart_nomad_allocation(
    job_id: str, task: Optional[str] = None
) -> Dict[str, Any]:
    """Restart the latest allocation for a Nomad job.

    Args:
        job_id: The Nomad job ID.
        task: Specific task to restart. If omitted, restarts entire allocation.

    Returns:
        A dict with the restart result.
    """
    client = _get_client()
    if not client:
        return {"status": "error", "error": "Nomad integration not configured"}

    try:
        allocs = await client.get_job_allocations(job_id)
        if not allocs:
            return {
                "status": "error",
                "error": f"No allocations found for job {job_id}",
            }

        # Pick the most recent allocation (running preferred)
        running = [a for a in allocs if a.get("ClientStatus") == "running"]
        alloc = running[0] if running else allocs[0]
        alloc_id = alloc["ID"]

        result = await client.restart_allocation(alloc_id, task=task)
        return {
            "status": "success",
            "job_id": job_id,
            "alloc_id": alloc_id,
            "task": task,
            "message": f"Allocation {alloc_id[:8]} restarted"
            + (f" (task: {task})" if task else ""),
            "result": result,
        }
    except Exception as e:
        logger.error(f"restart_nomad_allocation failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def plan_nomad_job_update(job_id: str, job_hcl: str) -> Dict[str, Any]:
    """Parse an HCL job spec and plan the update (dry-run with diff).

    Args:
        job_id: The Nomad job ID being updated.
        job_hcl: The HCL job specification as a string.

    Returns:
        A dict with the plan diff and resource impact, without applying changes.
    """
    client = _get_client()
    if not client:
        return {"status": "error", "error": "Nomad integration not configured"}

    try:
        # Parse HCL to JSON
        parsed = await client.parse_jobspec(job_hcl)

        # Plan the update
        plan_result = await client.plan_job(parsed)

        return {
            "status": "success",
            "job_id": job_id,
            "diff": plan_result.get("Diff"),
            "annotations": plan_result.get("Annotations"),
            "warnings": plan_result.get("Warnings"),
            "created_evals": plan_result.get("CreatedEvals"),
            "job_modify_index": plan_result.get("JobModifyIndex"),
        }
    except Exception as e:
        logger.error(f"plan_nomad_job_update failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def submit_nomad_job_update(job_id: str, job_spec_json: str) -> Dict[str, Any]:
    """Submit a job update to Nomad. Always run plan_nomad_job_update first.

    Args:
        job_id: The Nomad job ID being updated.
        job_spec_json: The job specification as a JSON string.

    Returns:
        A dict with the submission result including eval ID.
    """
    import json

    client = _get_client()
    if not client:
        return {"status": "error", "error": "Nomad integration not configured"}

    try:
        job_spec = json.loads(job_spec_json)

        # Always plan first to validate
        plan_result = await client.plan_job(job_spec)
        warnings = plan_result.get("Warnings")
        if warnings:
            logger.warning(f"Nomad job plan warnings for {job_id}: {warnings}")

        # Submit the job
        result = await client.submit_job(job_spec)
        return {
            "status": "success",
            "job_id": job_id,
            "eval_id": result.get("EvalID"),
            "warnings": warnings,
            "message": f"Job {job_id} updated successfully",
        }
    except json.JSONDecodeError as e:
        return {"status": "error", "error": f"Invalid JSON: {e}"}
    except Exception as e:
        logger.error(f"submit_nomad_job_update failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def check_nomad_service_health(service_name: str) -> Dict[str, Any]:
    """Check health of a service registered in Nomad's service discovery.

    Args:
        service_name: The service name to check.

    Returns:
        A dict with the service health status and instances.
    """
    client = _get_client()
    if not client:
        return {"status": "error", "error": "Nomad integration not configured"}

    try:
        # Use Nomad's built-in service discovery
        services = await client._get(f"/v1/service/{service_name}")
        instances = [
            {
                "id": s.get("ID"),
                "node_id": s.get("NodeID"),
                "address": s.get("Address"),
                "port": s.get("Port"),
                "tags": s.get("Tags"),
                "job_id": s.get("JobID"),
                "alloc_id": s.get("AllocID"),
            }
            for s in (services or [])
        ]
        return {
            "status": "success",
            "service_name": service_name,
            "healthy_instances": len(instances),
            "instances": instances,
        }
    except Exception as e:
        logger.error(f"check_nomad_service_health failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ── Tool list for agent registration ─────────────────────────

NOMAD_TOOLS: List[FunctionTool] = [
    FunctionTool(list_nomad_jobs),
    FunctionTool(get_nomad_job_status),
    FunctionTool(get_nomad_allocation_logs),
    FunctionTool(restart_nomad_allocation),
    FunctionTool(plan_nomad_job_update),
    FunctionTool(submit_nomad_job_update),
    FunctionTool(check_nomad_service_health),
]
