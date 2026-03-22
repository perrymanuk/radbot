"""Remote session proxy for Nomad-hosted agent workers.

SessionProxy implements the same ``process_message()`` interface as
SessionRunner but delegates execution to a remote A2A worker running
as a Nomad batch job.  It handles:

  1. Worker lifecycle — spawning, health-checking, stopping Nomad jobs
  2. Service discovery — finding the worker's A2A URL via Nomad service API
  3. Message proxying — sending user messages via A2A and translating responses
  4. Fallback — creating a local SessionRunner when the remote path fails
"""

import asyncio
import logging
import os
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# How long to wait for a newly spawned worker to become healthy
WORKER_STARTUP_TIMEOUT = 120  # seconds
WORKER_HEALTH_POLL_INTERVAL = 3  # seconds


class SessionProxy:
    """Proxy that delegates agent processing to a remote Nomad worker."""

    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id
        self._worker_url: Optional[str] = None
        self._nomad_job_id: Optional[str] = None

    async def process_message(self, message: str, run_config=None) -> dict:
        """Send a message to the remote worker and return the response.

        Falls back to a local SessionRunner if the remote path fails.

        Returns:
            Same dict shape as SessionRunner.process_message():
            ``{"response": str, "events": list, ...}``
        """
        try:
            # Ensure worker is running and we know its URL
            worker_url = await self._ensure_worker()
            if not worker_url:
                logger.warning(
                    "No worker available for session %s — falling back to local",
                    self.session_id,
                )
                return await self._fallback_local(message, run_config)

            # Send message via A2A
            response_text = await self._send_a2a_message(worker_url, message)
            if response_text is None:
                logger.warning(
                    "A2A request failed for session %s — falling back to local",
                    self.session_id,
                )
                return await self._fallback_local(message, run_config)

            # Touch the DB record to update last_active_at
            try:
                from radbot.worker.db import touch_worker

                touch_worker(self.session_id)
            except Exception:
                pass

            return {
                "response": response_text,
                "events": [],
                "source": "remote_worker",
            }
        except Exception as e:
            logger.error(
                "SessionProxy error for %s: %s", self.session_id, e, exc_info=True
            )
            return await self._fallback_local(message, run_config)

    async def _ensure_worker(self) -> Optional[str]:
        """Make sure a Nomad worker is running for this session.

        Returns the worker's A2A base URL, or None if unavailable.
        """
        # 1. Check if we already have a cached URL and it's healthy
        if self._worker_url:
            if await self._check_health(self._worker_url):
                return self._worker_url
            else:
                logger.info("Cached worker URL unhealthy, re-discovering")
                self._worker_url = None

        # 2. Try to discover an existing worker via Nomad service discovery
        url = await self._discover_worker()
        if url and await self._check_health(url):
            self._worker_url = url
            # Update DB record
            try:
                from radbot.worker.db import update_worker_status

                update_worker_status(self.session_id, "healthy", worker_url=url)
            except Exception:
                pass
            return url

        # 3. No running worker — spawn one
        logger.info("Spawning new worker for session %s", self.session_id)
        url = await self._spawn_worker()
        if url:
            self._worker_url = url
            return url

        return None

    async def _discover_worker(self) -> Optional[str]:
        """Find an existing worker via Nomad service discovery or DB."""
        # Try Nomad service discovery first
        try:
            from radbot.tools.nomad.nomad_client import get_nomad_client

            client = get_nomad_client()
            if client:
                tag = f"session_id={self.session_id}"
                svc = await client.find_service_by_tag("radbot-session", tag)
                if svc:
                    address = svc.get("Address", "")
                    port = svc.get("Port", 0)
                    if address and port:
                        url = f"http://{address}:{port}"
                        logger.debug(
                            "Discovered worker via Nomad service: %s", url
                        )
                        return url
        except Exception as e:
            logger.debug("Nomad service discovery failed: %s", e)

        # Fall back to DB record
        try:
            from radbot.worker.db import get_worker

            record = get_worker(self.session_id)
            if record and record.get("worker_url") and record.get("status") in (
                "starting",
                "healthy",
            ):
                return record["worker_url"]
        except Exception as e:
            logger.debug("DB worker lookup failed: %s", e)

        return None

    async def _spawn_worker(self) -> Optional[str]:
        """Submit a Nomad service job for this session and wait for it to be healthy."""
        try:
            from radbot.tools.nomad.nomad_client import get_nomad_client
            from radbot.worker.db import count_active_workers, upsert_worker
            from radbot.worker.nomad_template import build_worker_job_spec

            client = get_nomad_client()
            if not client:
                logger.warning("Nomad client not configured — cannot spawn worker")
                return None

            # Check concurrency limit
            max_workers = self._get_max_workers()
            active = count_active_workers()
            if active >= max_workers:
                logger.warning(
                    "Worker limit reached (%d/%d) — cannot spawn for session %s",
                    active,
                    max_workers,
                    self.session_id,
                )
                return None

            # Gather bootstrap secrets
            secrets = self._get_bootstrap_secrets()
            if not secrets:
                logger.error("Cannot spawn worker: missing bootstrap secrets")
                return None

            # Build and submit job
            image_tag = self._get_image_tag()
            job_spec = build_worker_job_spec(
                session_id=self.session_id,
                image_tag=image_tag,
                credential_key=secrets["credential_key"],
                admin_token=secrets["admin_token"],
                postgres_pass=secrets["postgres_pass"],
                postgres_host=secrets.get("postgres_host", "postgres.service.consul"),
                postgres_db=secrets.get("postgres_db", "radbot_todos"),
            )

            job_id = job_spec["Job"]["ID"]
            self._nomad_job_id = job_id

            # Record in DB before submission
            upsert_worker(
                session_id=self.session_id,
                nomad_job_id=job_id,
                status="starting",
                image_tag=image_tag,
            )

            result = await client.submit_job(job_spec)
            logger.info(
                "Submitted Nomad worker job %s for session %s: %s",
                job_id,
                self.session_id,
                result.get("EvalID", ""),
            )

            # Wait for worker to become healthy
            url = await self._wait_for_healthy(job_id)
            if url:
                from radbot.worker.db import update_worker_status

                update_worker_status(self.session_id, "healthy", worker_url=url)
                return url
            else:
                from radbot.worker.db import update_worker_status

                update_worker_status(self.session_id, "failed")
                return None

        except Exception as e:
            logger.error("Failed to spawn worker: %s", e, exc_info=True)
            return None

    async def _wait_for_healthy(self, job_id: str) -> Optional[str]:
        """Poll Nomad service discovery until the worker registers and passes health checks."""
        from radbot.tools.nomad.nomad_client import get_nomad_client

        client = get_nomad_client()
        if not client:
            return None

        tag = f"session_id={self.session_id}"
        elapsed = 0.0

        while elapsed < WORKER_STARTUP_TIMEOUT:
            await asyncio.sleep(WORKER_HEALTH_POLL_INTERVAL)
            elapsed += WORKER_HEALTH_POLL_INTERVAL

            try:
                svc = await client.find_service_by_tag("radbot-session", tag)
                if svc:
                    address = svc.get("Address", "")
                    port = svc.get("Port", 0)
                    if address and port:
                        url = f"http://{address}:{port}"
                        if await self._check_health(url):
                            logger.info(
                                "Worker %s healthy after %.0fs at %s",
                                job_id,
                                elapsed,
                                url,
                            )
                            return url
            except Exception as e:
                logger.debug("Health poll attempt failed: %s", e)

            if elapsed % 15 < WORKER_HEALTH_POLL_INTERVAL:
                logger.debug(
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

    async def _send_a2a_message(
        self, worker_url: str, message: str
    ) -> Optional[str]:
        """Send a message to the worker's A2A endpoint and return the response text."""
        try:
            from a2a.client.card_resolver import A2ACardResolver
            from a2a.client.client import ClientConfig as A2AClientConfig
            from a2a.client.client_factory import A2AClientFactory
            from a2a.types import (
                Message as A2AMessage,
                Part as A2APart,
                TextPart,
                TransportProtocol,
            )
            from google.adk.platform import uuid as platform_uuid

            # Resolve agent card from worker
            async with httpx.AsyncClient(timeout=30) as http_client:
                resolver = A2ACardResolver(
                    httpx_client=http_client,
                    base_url=worker_url,
                )
                agent_card = await resolver.get_agent_card()

                # Create A2A client
                config = A2AClientConfig(
                    httpx_client=http_client,
                    streaming=False,
                    polling=False,
                    supported_transports=[TransportProtocol.jsonrpc],
                )
                factory = A2AClientFactory(config=config)
                a2a_client = factory.create(agent_card)

                # Build and send message
                a2a_message = A2AMessage(
                    message_id=platform_uuid.new_uuid(),
                    parts=[A2APart(root=TextPart(text=message))],
                    role="user",
                )

                response_text = ""
                async for response in a2a_client.send_message(request=a2a_message):
                    # Response can be a tuple (Task, update) or a Message
                    if isinstance(response, tuple):
                        task, update = response
                        if task and task.status and task.status.message:
                            for part in task.status.message.parts:
                                if hasattr(part, "root") and hasattr(part.root, "text"):
                                    response_text += part.root.text
                                elif hasattr(part, "text"):
                                    response_text += part.text
                    elif hasattr(response, "parts"):
                        for part in response.parts:
                            if hasattr(part, "root") and hasattr(part.root, "text"):
                                response_text += part.root.text
                            elif hasattr(part, "text"):
                                response_text += part.text

                return response_text if response_text else None

        except Exception as e:
            logger.error("A2A message to %s failed: %s", worker_url, e, exc_info=True)
            return None

    async def _fallback_local(self, message: str, run_config=None) -> dict:
        """Fall back to a local SessionRunner when remote is unavailable."""
        logger.info("Using local fallback for session %s", self.session_id)
        from radbot.web.api.session.session_runner import SessionRunner

        runner = SessionRunner(user_id=self.user_id, session_id=self.session_id)
        result = await runner.process_message(message, run_config=run_config)
        result["source"] = "local_fallback"
        return result

    async def stop_worker(self) -> bool:
        """Stop the Nomad worker job for this session."""
        try:
            from radbot.tools.nomad.nomad_client import get_nomad_client
            from radbot.worker.db import update_worker_status

            client = get_nomad_client()
            if not client:
                return False

            job_id = self._nomad_job_id
            if not job_id:
                # Try DB lookup
                from radbot.worker.db import get_worker

                record = get_worker(self.session_id)
                if record:
                    job_id = record.get("nomad_job_id")

            if not job_id:
                return False

            await client.stop_job(job_id)
            update_worker_status(self.session_id, "stopped")
            self._worker_url = None
            logger.info("Stopped worker %s for session %s", job_id, self.session_id)
            return True
        except Exception as e:
            logger.error("Failed to stop worker: %s", e)
            return False

    def _get_bootstrap_secrets(self) -> Optional[Dict[str, str]]:
        """Read bootstrap secrets from the current environment.

        The main app already has these injected by Nomad.
        """
        credential_key = os.environ.get("RADBOT_CREDENTIAL_KEY", "")
        admin_token = os.environ.get("RADBOT_ADMIN_TOKEN", "")

        if not credential_key:
            logger.error("RADBOT_CREDENTIAL_KEY not set — cannot spawn worker")
            return None

        # Get postgres password from config
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
            logger.error("PostgreSQL password not available — cannot spawn worker")
            return None

        return {
            "credential_key": credential_key,
            "admin_token": admin_token,
            "postgres_pass": postgres_pass,
            "postgres_host": postgres_host,
            "postgres_db": postgres_db,
        }

    def _get_image_tag(self) -> str:
        """Determine the Docker image tag for the worker.

        Reads from config or falls back to "latest".
        """
        try:
            from radbot.config.config_loader import config_loader

            agent_config = config_loader.config.get("agent", {})
            tag = agent_config.get("worker_image_tag", "")
            if tag:
                return tag
        except Exception:
            pass

        # Try environment variable
        return os.environ.get("RADBOT_WORKER_IMAGE_TAG", "latest")

    def _get_max_workers(self) -> int:
        """Get the max concurrent workers limit from config."""
        try:
            from radbot.config.config_loader import config_loader

            agent_config = config_loader.config.get("agent", {})
            return int(agent_config.get("max_session_workers", 10))
        except Exception:
            return 10
