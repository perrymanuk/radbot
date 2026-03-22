"""Lazy-initialized singleton Nomad HTTP client.

Reads config from ``integrations.nomad`` (merged file+DB config) first,
then falls back to the credential store (``nomad_token``), then to
NOMAD_ADDR / NOMAD_TOKEN / NOMAD_NAMESPACE environment variables.

Returns None when unconfigured so tools can degrade gracefully.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_client: Optional["NomadClient"] = None
_initialized = False


def _get_config() -> dict:
    """Pull Nomad settings from config manager, credential store, then env."""
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("nomad", {})
    except Exception:
        cfg = {}

    addr = cfg.get("addr") or os.environ.get("NOMAD_ADDR") or ""
    token = cfg.get("token") or os.environ.get("NOMAD_TOKEN") or ""
    namespace = cfg.get("namespace") or os.environ.get("NOMAD_NAMESPACE") or "default"
    enabled = cfg.get("enabled", True)

    # Try credential store for token if not found above
    if not token:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                token = store.get("nomad_token") or ""
                if token:
                    logger.info("Nomad: Using token from credential store")
        except Exception as e:
            logger.debug(f"Nomad credential store lookup failed: {e}")

    return {
        "addr": addr,
        "token": token,
        "namespace": namespace,
        "enabled": enabled,
    }


class NomadClient:
    """Async HTTP client for the Nomad HTTP API (v1)."""

    def __init__(self, addr: str, token: str = "", namespace: str = "default"):
        self.addr = addr.rstrip("/")
        self.namespace = namespace
        self._headers: Dict[str, str] = {"Accept": "application/json"}
        if token:
            self._headers["X-Nomad-Token"] = token

    def _url(self, path: str) -> str:
        return f"{self.addr}{path}"

    def _params(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Default query params (namespace) merged with extras."""
        params: Dict[str, Any] = {}
        if self.namespace and self.namespace != "default":
            params["namespace"] = self.namespace
        if extra:
            params.update(extra)
        return params

    async def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None, timeout: float = 15
    ) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                self._url(path), headers=self._headers, params=self._params(params)
            )
            if not resp.is_success:
                logger.error(
                    "Nomad GET %s returned %d: %s",
                    path,
                    resp.status_code,
                    resp.text[:500],
                )
            resp.raise_for_status()
            return resp.json()

    async def _put(
        self,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: float = 15,
    ) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.put(
                self._url(path),
                headers=self._headers,
                json=json_body,
                params=self._params(),
            )
            if not resp.is_success:
                logger.error(
                    "Nomad PUT %s returned %d: %s",
                    path,
                    resp.status_code,
                    resp.text[:500],
                )
            resp.raise_for_status()
            # Some PUT endpoints return empty body
            if resp.text:
                return resp.json()
            return {}

    async def _post(
        self,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: float = 15,
    ) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                self._url(path),
                headers=self._headers,
                json=json_body,
                params=self._params(),
            )
            if not resp.is_success:
                logger.error(
                    "Nomad POST %s returned %d: %s",
                    path,
                    resp.status_code,
                    resp.text[:500],
                )
            resp.raise_for_status()
            return resp.json()

    async def _delete(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 15,
    ) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.delete(
                self._url(path),
                headers=self._headers,
                params=self._params(params),
            )
            if not resp.is_success:
                logger.error(
                    "Nomad DELETE %s returned %d: %s",
                    path,
                    resp.status_code,
                    resp.text[:500],
                )
            resp.raise_for_status()
            return resp.json()

    # ── Jobs ──────────────────────────────────────────────────

    async def list_jobs(self, prefix: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all jobs, optionally filtered by prefix."""
        params: Dict[str, Any] = {}
        if prefix:
            params["prefix"] = prefix
        return await self._get("/v1/jobs", params=params)

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        """Get job definition and status."""
        return await self._get(f"/v1/job/{job_id}")

    async def stop_job(self, job_id: str, purge: bool = False) -> Dict[str, Any]:
        """Stop (deregister) a job."""
        params: Dict[str, Any] = {}
        if purge:
            params["purge"] = "true"
        return await self._delete(f"/v1/job/{job_id}", params=params)

    # ── Allocations ───────────────────────────────────────────

    async def get_job_allocations(self, job_id: str) -> List[Dict[str, Any]]:
        """List allocations for a job."""
        return await self._get(f"/v1/job/{job_id}/allocations")

    async def get_allocation(self, alloc_id: str) -> Dict[str, Any]:
        """Get allocation detail."""
        return await self._get(f"/v1/allocation/{alloc_id}")

    async def restart_allocation(
        self, alloc_id: str, task: Optional[str] = None
    ) -> Dict[str, Any]:
        """Restart an allocation (or a specific task within it)."""
        body: Dict[str, Any] = {}
        if task:
            body["TaskName"] = task
        return await self._put(
            f"/v1/client/allocation/{alloc_id}/restart", json_body=body
        )

    # ── Logs ──────────────────────────────────────────────────

    async def get_alloc_logs(
        self,
        alloc_id: str,
        task: str,
        log_type: str = "stderr",
        offset: int = 0,
        origin: str = "end",
        plain: bool = True,
    ) -> str:
        """Fetch allocation logs (stderr or stdout)."""
        params: Dict[str, Any] = {
            "task": task,
            "type": log_type,
            "origin": origin,
            "plain": str(plain).lower(),
        }
        if offset:
            params["offset"] = offset
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                self._url(f"/v1/client/fs/logs/{alloc_id}"),
                headers=self._headers,
                params=self._params(params),
            )
            if not resp.is_success:
                logger.error(
                    "Nomad logs %s returned %d: %s",
                    alloc_id,
                    resp.status_code,
                    resp.text[:500],
                )
            resp.raise_for_status()
            return resp.text

    # ── Job Planning & Submission ─────────────────────────────

    async def plan_job(
        self, job_spec: Dict[str, Any], diff: bool = True
    ) -> Dict[str, Any]:
        """Plan a job update (dry-run). Returns diff and resource impact."""
        job_id = job_spec.get("Job", {}).get("ID") or job_spec.get("ID", "")
        body = {"Job": job_spec.get("Job", job_spec), "Diff": diff}
        return await self._post(f"/v1/job/{job_id}/plan", json_body=body)

    async def submit_job(self, job_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Submit (register) a job."""
        body = {"Job": job_spec.get("Job", job_spec)}
        return await self._post("/v1/jobs", json_body=body)

    async def parse_jobspec(self, hcl: str) -> Dict[str, Any]:
        """Parse an HCL job spec into JSON."""
        return await self._post(
            "/v1/jobs/parse", json_body={"JobHCL": hcl, "Canonicalize": True}
        )

    # ── Deployments ───────────────────────────────────────────

    async def get_deployment(self, deployment_id: str) -> Dict[str, Any]:
        """Get deployment status."""
        return await self._get(f"/v1/deployment/{deployment_id}")

    async def get_job_deployments(self, job_id: str) -> List[Dict[str, Any]]:
        """List deployments for a job."""
        return await self._get(f"/v1/job/{job_id}/deployments")

    # ── Nomad Service Discovery ─────────────────────────────

    async def list_services(
        self, service_name: str
    ) -> List[Dict[str, Any]]:
        """List service registrations via Nomad's native service discovery.

        Uses the Nomad ``/v1/service/{name}`` endpoint (not Consul).
        """
        return await self._get(f"/v1/service/{service_name}")

    async def find_service_by_tag(
        self, service_name: str, tag: str
    ) -> Optional[Dict[str, Any]]:
        """Find a single service instance matching a tag.

        Tries Nomad native service discovery first, then falls back to
        Consul catalog API (Nomad registers services in Consul by default).

        Args:
            service_name: Nomad service name (e.g. "radbot-workspace").
            tag: Exact tag to match (e.g. "workspace_id=<uuid>").

        Returns:
            Dict with Address/Port keys, or None.
        """
        # 1. Try Nomad native service discovery
        try:
            services = await self.list_services(service_name)
            for svc in services:
                tags = svc.get("Tags") or []
                if tag in tags:
                    return svc
        except Exception as e:
            logger.debug("Nomad service lookup failed: %s", e)

        # 2. Fall back to Consul catalog API
        try:
            consul_addr = self.addr.replace(":4646", ":8500")
            if ":4646" not in self.addr:
                # Nomad addr doesn't use standard port — try consul.service.consul
                consul_addr = "http://consul.service.consul:8500"

            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{consul_addr}/v1/catalog/service/{service_name}",
                    params={"tag": tag},
                )
                if resp.is_success:
                    services = resp.json()
                    for svc in services:
                        addr = svc.get("ServiceAddress") or svc.get("Address", "")
                        port = svc.get("ServicePort", 0)
                        if addr and port:
                            return {
                                "Address": addr,
                                "Port": port,
                                "Tags": svc.get("ServiceTags", []),
                            }
        except Exception as e:
            logger.debug("Consul service lookup for %s tag=%s failed: %s", service_name, tag, e)

        return None

    # ── Health ────────────────────────────────────────────────

    async def test(self) -> Dict[str, Any]:
        """Test connectivity by querying agent self info."""
        return await self._get("/v1/agent/self")


def get_nomad_client() -> Optional[NomadClient]:
    """Return the singleton Nomad client, or None if unconfigured."""
    global _client, _initialized

    if _initialized:
        return _client

    cfg = _get_config()
    if not cfg["enabled"]:
        logger.info("Nomad integration is disabled in config")
        _initialized = True
        return None

    addr = cfg["addr"]
    if not addr:
        logger.info(
            "Nomad integration not configured — set integrations.nomad.addr "
            "in config or NOMAD_ADDR env var"
        )
        _initialized = True
        return None

    _client = NomadClient(
        addr=addr,
        token=cfg["token"],
        namespace=cfg["namespace"],
    )
    _initialized = True
    logger.info(f"Nomad client initialized (addr={addr}, namespace={cfg['namespace']})")
    return _client


def reset_nomad_client() -> None:
    """Clear the singleton so the next call re-initializes with fresh config."""
    global _client, _initialized
    _client = None
    _initialized = False
    logger.info("Nomad client singleton reset")
