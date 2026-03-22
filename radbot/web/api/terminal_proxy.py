"""Workspace proxy for Nomad-hosted terminal workers.

Manages the lifecycle of Nomad worker jobs keyed by workspace_id.
Each workspace gets at most one worker. The proxy handles spawning,
discovery, health checking, and stopping workers.
"""

import asyncio
import logging
import os
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# First pull can take minutes; subsequent starts are fast (image cached)
WORKER_STARTUP_TIMEOUT = 300  # 5 minutes
WORKER_HEALTH_POLL_INTERVAL = 5  # seconds

# Singleton cache of proxies per workspace
_proxies: Dict[str, "WorkspaceProxy"] = {}


def get_workspace_proxy(workspace_id: str) -> "WorkspaceProxy":
    """Get or create a WorkspaceProxy for a workspace."""
    if workspace_id not in _proxies:
        _proxies[workspace_id] = WorkspaceProxy(workspace_id)
    return _proxies[workspace_id]


class WorkspaceProxy:
    """Manages a Nomad worker for a single workspace."""

    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        self._worker_url: Optional[str] = None
        self._nomad_job_id: Optional[str] = None
        self._spawn_lock = asyncio.Lock()
        self._spawning = False

    async def ensure_worker(self) -> Optional[str]:
        """Make sure a Nomad worker is running for this workspace.

        Uses a lock to prevent multiple concurrent spawn attempts.
        Returns the worker's base URL, or None if unavailable.
        """
        # Fast path: cached and healthy
        if self._worker_url:
            if await self._check_health(self._worker_url):
                return self._worker_url
            self._worker_url = None

        # Discover existing worker (already running from previous call)
        url = await self._discover_worker()
        if url and await self._check_health(url):
            self._worker_url = url
            try:
                from radbot.worker.db import update_workspace_worker_status

                update_workspace_worker_status(
                    self.workspace_id, "healthy", worker_url=url
                )
            except Exception:
                pass
            return url

        # Check if already spawning (another coroutine is waiting)
        if self._spawning:
            logger.info(
                "Worker for %s already spawning — waiting for it",
                self.workspace_id,
            )
            return await self._wait_for_existing_spawn()

        # Spawn new worker (with lock to prevent races)
        async with self._spawn_lock:
            # Re-check after acquiring lock (another caller may have finished)
            url = await self._discover_worker()
            if url and await self._check_health(url):
                self._worker_url = url
                return url

            # Also check DB — if status is "starting", job was already submitted
            try:
                from radbot.worker.db import get_workspace_worker

                record = get_workspace_worker(self.workspace_id)
                if record and record.get("status") == "starting":
                    logger.info(
                        "Worker for %s already submitted (status=starting) — waiting",
                        self.workspace_id,
                    )
                    job_id = record.get("nomad_job_id", "")
                    self._nomad_job_id = job_id
                    self._spawning = True
                    try:
                        url = await self._wait_for_healthy(job_id)
                        if url:
                            self._worker_url = url
                            from radbot.worker.db import update_workspace_worker_status

                            update_workspace_worker_status(
                                self.workspace_id, "healthy", worker_url=url
                            )
                        return url
                    finally:
                        self._spawning = False
            except Exception:
                pass

            logger.info("Spawning workspace worker for %s", self.workspace_id)
            self._spawning = True
            try:
                url = await self._spawn_worker()
                if url:
                    self._worker_url = url
                return url
            finally:
                self._spawning = False

    async def _wait_for_existing_spawn(self) -> Optional[str]:
        """Wait for an in-progress spawn to complete."""
        for _ in range(int(WORKER_STARTUP_TIMEOUT / WORKER_HEALTH_POLL_INTERVAL)):
            await asyncio.sleep(WORKER_HEALTH_POLL_INTERVAL)
            if self._worker_url:
                return self._worker_url
            if not self._spawning:
                # Spawn finished (maybe failed) — try discover
                url = await self._discover_worker()
                if url and await self._check_health(url):
                    self._worker_url = url
                    return url
                return None
        return None

    async def stop_worker(self) -> bool:
        """Stop the Nomad worker job for this workspace."""
        try:
            from radbot.tools.nomad.nomad_client import get_nomad_client
            from radbot.worker.db import update_workspace_worker_status

            client = get_nomad_client()
            if not client:
                return False

            job_id = self._nomad_job_id
            if not job_id:
                from radbot.worker.db import get_workspace_worker

                record = get_workspace_worker(self.workspace_id)
                if record:
                    job_id = record.get("nomad_job_id")

            if not job_id:
                return False

            await client.stop_job(job_id)
            update_workspace_worker_status(self.workspace_id, "stopped")
            self._worker_url = None
            logger.info(
                "Stopped worker %s for workspace %s", job_id, self.workspace_id
            )
            return True
        except Exception as e:
            logger.error("Failed to stop workspace worker: %s", e)
            return False

    async def _discover_worker(self) -> Optional[str]:
        """Find an existing worker via Nomad service discovery or DB."""
        # Nomad service discovery
        try:
            from radbot.tools.nomad.nomad_client import get_nomad_client

            client = get_nomad_client()
            if client:
                tag = f"workspace_id={self.workspace_id}"
                svc = await client.find_service_by_tag("radbot-workspace", tag)
                if svc:
                    address = svc.get("Address", "")
                    port = svc.get("Port", 0)
                    if address and port:
                        url = f"http://{address}:{port}"
                        logger.debug("Discovered workspace worker: %s", url)
                        return url
        except Exception as e:
            logger.debug("Nomad service discovery failed: %s", e)

        # DB fallback — only if worker_url is known
        try:
            from radbot.worker.db import get_workspace_worker

            record = get_workspace_worker(self.workspace_id)
            if record and record.get("worker_url") and record.get("status") == "healthy":
                return record["worker_url"]
        except Exception as e:
            logger.debug("DB workspace worker lookup failed: %s", e)

        return None

    async def _spawn_worker(self) -> Optional[str]:
        """Submit a Nomad service job for this workspace."""
        try:
            from radbot.tools.nomad.nomad_client import get_nomad_client
            from radbot.worker.db import (
                count_active_workspace_workers,
                update_workspace_worker_status,
                upsert_workspace_worker,
            )
            from radbot.worker.nomad_template import build_workspace_worker_spec

            client = get_nomad_client()
            if not client:
                logger.warning("Nomad client not configured — cannot spawn worker")
                return None

            # Check concurrency limit
            max_workers = self._get_max_workers()
            active = count_active_workspace_workers()
            if active >= max_workers:
                logger.warning(
                    "Worker limit reached (%d/%d) — cannot spawn for workspace %s",
                    active,
                    max_workers,
                    self.workspace_id,
                )
                return None

            secrets = self._get_bootstrap_secrets()
            if not secrets:
                logger.error("Cannot spawn worker: missing bootstrap secrets")
                return None

            image_tag = self._get_image_tag()
            job_spec = build_workspace_worker_spec(
                workspace_id=self.workspace_id,
                image_tag=image_tag,
                credential_key=secrets["credential_key"],
                admin_token=secrets["admin_token"],
                postgres_pass=secrets["postgres_pass"],
                postgres_host=secrets.get("postgres_host", "postgres.service.consul"),
                postgres_db=secrets.get("postgres_db", "radbot_todos"),
            )

            job_id = job_spec["Job"]["ID"]
            self._nomad_job_id = job_id

            upsert_workspace_worker(
                workspace_id=self.workspace_id,
                nomad_job_id=job_id,
                status="starting",
                image_tag=image_tag,
            )

            result = await client.submit_job(job_spec)
            logger.info(
                "Submitted workspace worker %s for workspace %s: %s",
                job_id,
                self.workspace_id,
                result.get("EvalID", ""),
            )

            url = await self._wait_for_healthy(job_id)
            if url:
                update_workspace_worker_status(
                    self.workspace_id, "healthy", worker_url=url
                )
                return url
            else:
                update_workspace_worker_status(self.workspace_id, "failed")
                return None

        except Exception as e:
            logger.error("Failed to spawn workspace worker: %s", e, exc_info=True)
            return None

    async def _wait_for_healthy(self, job_id: str) -> Optional[str]:
        """Poll until the worker registers and passes health checks."""
        from radbot.tools.nomad.nomad_client import get_nomad_client

        client = get_nomad_client()
        if not client:
            return None

        tag = f"workspace_id={self.workspace_id}"
        elapsed = 0.0

        while elapsed < WORKER_STARTUP_TIMEOUT:
            await asyncio.sleep(WORKER_HEALTH_POLL_INTERVAL)
            elapsed += WORKER_HEALTH_POLL_INTERVAL

            try:
                svc = await client.find_service_by_tag("radbot-workspace", tag)
                if svc:
                    address = svc.get("Address", "")
                    port = svc.get("Port", 0)
                    if address and port:
                        url = f"http://{address}:{port}"
                        if await self._check_health(url):
                            logger.info(
                                "Workspace worker %s healthy after %.0fs at %s",
                                job_id,
                                elapsed,
                                url,
                            )
                            return url
            except Exception as e:
                logger.debug("Health poll attempt failed: %s", e)

            if int(elapsed) % 30 == 0:
                logger.info(
                    "Waiting for worker %s... (%.0fs/%ds)",
                    job_id,
                    elapsed,
                    WORKER_STARTUP_TIMEOUT,
                )

        logger.warning(
            "Worker %s did not become healthy within %ds",
            job_id,
            WORKER_STARTUP_TIMEOUT,
        )
        return None

    async def _check_health(self, base_url: str) -> bool:
        """Check worker health endpoint."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    def _get_bootstrap_secrets(self) -> Optional[Dict[str, str]]:
        """Read bootstrap secrets from the current environment."""
        credential_key = os.environ.get("RADBOT_CREDENTIAL_KEY", "")
        admin_token = os.environ.get("RADBOT_ADMIN_TOKEN", "")

        if not credential_key:
            logger.error("RADBOT_CREDENTIAL_KEY not set")
            return None

        postgres_pass = ""
        postgres_host = "postgres.service.consul"
        postgres_db = "radbot_todos"
        try:
            from radbot.config.config_loader import config_loader

            db_config = config_loader.config.get("database", {})
            postgres_pass = db_config.get("password", "")
            postgres_host = db_config.get("host", postgres_host)
            postgres_db = db_config.get("db_name", postgres_db)
        except Exception as e:
            logger.warning("Could not read DB config: %s", e)

        if not postgres_pass:
            logger.error("PostgreSQL password not available")
            return None

        return {
            "credential_key": credential_key,
            "admin_token": admin_token,
            "postgres_pass": postgres_pass,
            "postgres_host": postgres_host,
            "postgres_db": postgres_db,
        }

    def _get_image_tag(self) -> str:
        """Determine the Docker image tag for the worker."""
        try:
            from radbot.config.config_loader import config_loader

            agent_config = config_loader.config.get("agent", {})
            tag = agent_config.get("worker_image_tag", "")
            if tag:
                return tag
        except Exception:
            pass
        return os.environ.get("RADBOT_WORKER_IMAGE_TAG", "latest")

    def _get_max_workers(self) -> int:
        """Get the max concurrent workers limit from config."""
        try:
            from radbot.config.config_loader import config_loader

            agent_config = config_loader.config.get("agent", {})
            return int(agent_config.get("max_session_workers", 10))
        except Exception:
            return 10
