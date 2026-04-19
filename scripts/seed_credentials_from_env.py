#!/usr/bin/env python3
"""Seed a CI radbot stack's credential store from environment variables.

Reads `scripts/e2e_seed_manifest.yml` for the list of (credential, env_var) pairs,
pulls each value from the process env, and POSTs to `/admin/api/credentials`.

CI variant of `seed_docker_credentials.py` — no host DB dependency, no decryption,
no rewrite_localhost. Intended to run from a GitHub Actions runner.

Usage:
    uv run python scripts/seed_credentials_from_env.py \
        --target-url http://localhost:8001 \
        --admin-token "$RADBOT_ADMIN_TOKEN"
"""

from __future__ import annotations

import argparse
import logging
import os
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _admin_client import admin_client, post_credential  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("seed_credentials")

DEFAULT_MANIFEST = pathlib.Path(__file__).resolve().parent / "e2e_seed_manifest.yml"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target-url", required=True, help="Base URL of the running radbot stack (e.g. http://localhost:8001)")
    p.add_argument("--admin-token", required=True, help="Admin bearer token for the target stack")
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to e2e_seed_manifest.yml")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    manifest = yaml.safe_load(pathlib.Path(args.manifest).read_text())
    creds = manifest.get("credentials", []) or []

    if not creds:
        log.warning("No credentials declared in manifest %s; nothing to seed.", args.manifest)
        return 0

    seeded = 0
    skipped = 0
    missing_required: list[str] = []

    with admin_client(args.target_url, args.admin_token) as client:
        for entry in creds:
            name = entry["name"]
            env_var = entry["env"]
            cred_type = entry.get("credential_type", "api_key")
            required = entry.get("required", True)

            value = os.environ.get(env_var)
            if not value:
                if required:
                    missing_required.append(f"{name} ({env_var})")
                    log.error("missing required env var %s for credential %s", env_var, name)
                else:
                    log.info("skip optional credential %s (%s not set)", name, env_var)
                    skipped += 1
                continue

            try:
                post_credential(client, name=name, value=value, credential_type=cred_type)
                seeded += 1
                log.info("seeded credential %s (%d chars)", name, len(value))
            except Exception as e:
                log.error("failed to seed %s: %s", name, e)
                return 1

    log.info("done: seeded=%d skipped=%d missing_required=%d", seeded, skipped, len(missing_required))

    if missing_required:
        log.error("required credentials not provided: %s", ", ".join(missing_required))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
