"""Shared bearer-auth httpx client for CI seeding scripts."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import httpx


@contextmanager
def admin_client(base_url: str, admin_token: str, timeout: float = 30.0) -> Iterator[httpx.Client]:
    """Yield an httpx.Client pre-configured with bearer auth + admin base URL."""
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {admin_token}"}
    with httpx.Client(base_url=base, headers=headers, timeout=timeout) as client:
        yield client


def post_credential(client: httpx.Client, name: str, value: str, credential_type: str = "api_key") -> None:
    """POST a credential to /admin/api/credentials. Raises on non-2xx."""
    resp = client.post(
        "/admin/api/credentials",
        json={"name": name, "value": value, "credential_type": credential_type},
    )
    resp.raise_for_status()


def put_config(client: httpx.Client, section: str, payload: dict) -> None:
    """PUT a config section to /admin/api/config/{section}. Raises on non-2xx."""
    resp = client.put(f"/admin/api/config/{section}", json=payload)
    resp.raise_for_status()
