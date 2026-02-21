#!/usr/bin/env python3
"""Seed a Docker radbot stack with credentials from the local dev credential store.

Reads credentials and config sections from the local dev PostgreSQL DB and pushes
them to a running Docker radbot instance via the admin API.

Usage:
    RADBOT_ENV=dev uv run python scripts/seed_docker_credentials.py \
        --target-url http://localhost:8000 \
        --admin-token <token> \
        --rewrite-localhost
"""

import argparse
import json
import logging
import re
import sys
import time

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Credential names to skip (internal to the Docker stack)
SKIP_PREFIXES = ("_oauth_state_",)
SKIP_NAMES = {"config:database", "config:vector_db", "config:full"}

# URL fields to rewrite when --rewrite-localhost is set
URL_FIELD_PATTERN = re.compile(r"(url|host|endpoint|base_url|server)$", re.IGNORECASE)


def rewrite_localhost_urls(obj, depth=0):
    """Recursively rewrite localhost/127.0.0.1 URLs to host.docker.internal."""
    if depth > 10:
        return obj
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if isinstance(v, str) and URL_FIELD_PATTERN.search(k):
                v = v.replace("localhost", "host.docker.internal")
                v = v.replace("127.0.0.1", "host.docker.internal")
            elif isinstance(v, (dict, list)):
                v = rewrite_localhost_urls(v, depth + 1)
            result[k] = v
        return result
    if isinstance(obj, list):
        return [rewrite_localhost_urls(item, depth + 1) for item in obj]
    return obj


def get_local_credentials():
    """Read all credentials and config sections from the local dev credential store."""
    try:
        from radbot.credentials.store import get_credential_store
    except Exception as e:
        logger.error(f"Cannot import radbot credential store: {e}")
        logger.error("Make sure RADBOT_ENV=dev is set and the local DB is reachable.")
        sys.exit(1)

    store = get_credential_store()
    if not store.available:
        logger.error("Credential store unavailable (RADBOT_CREDENTIAL_KEY not set?).")
        sys.exit(1)

    entries = store.list()
    if not entries:
        logger.warning("No credentials found in local store.")
        return [], []

    credentials = []  # (name, value, credential_type)
    config_sections = []  # (section_name, value_dict)

    for entry in entries:
        name = entry["name"]
        cred_type = entry.get("credential_type", "api_key")

        # Skip internal entries
        if name in SKIP_NAMES:
            logger.debug(f"Skipping {name} (internal)")
            continue
        if any(name.startswith(p) for p in SKIP_PREFIXES):
            logger.debug(f"Skipping {name} (prefix match)")
            continue

        value = store.get(name)
        if value is None:
            logger.warning(f"Could not decrypt '{name}', skipping")
            continue

        if cred_type == "config" and name.startswith("config:"):
            section = name[len("config:"):]
            try:
                config_sections.append((section, json.loads(value)))
            except json.JSONDecodeError:
                logger.warning(f"Config '{name}' is not valid JSON, pushing as raw credential")
                credentials.append((name, value, cred_type))
        else:
            credentials.append((name, value, cred_type))

    return credentials, config_sections


def push_to_docker(target_url, admin_token, credentials, config_sections, rewrite_localhost):
    """Push credentials and config sections to Docker radbot via admin API."""
    base = target_url.rstrip("/")
    headers = {"Authorization": f"Bearer {admin_token}"}

    errors = 0

    # Push config sections first
    for section, data in config_sections:
        if rewrite_localhost:
            data = rewrite_localhost_urls(data)

        try:
            resp = httpx.put(
                f"{base}/admin/api/config/{section}",
                json=data,
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code == 200:
                logger.info(f"Config section '{section}' pushed OK")
            else:
                logger.warning(f"Config section '{section}' failed: {resp.status_code} {resp.text}")
                errors += 1
        except httpx.HTTPError as e:
            logger.warning(f"Config section '{section}' failed: {e}")
            errors += 1

    # Push individual credentials
    for name, value, cred_type in credentials:
        try:
            resp = httpx.post(
                f"{base}/admin/api/credentials",
                json={
                    "name": name,
                    "value": value,
                    "credential_type": cred_type,
                },
                headers=headers,
                timeout=10.0,
            )
            if resp.status_code == 200:
                logger.info(f"Credential '{name}' pushed OK")
            else:
                logger.warning(f"Credential '{name}' failed: {resp.status_code} {resp.text}")
                errors += 1
        except httpx.HTTPError as e:
            logger.warning(f"Credential '{name}' failed: {e}")
            errors += 1

    return errors


def wait_for_server(target_url, admin_token, max_retries=3, delay=2.0):
    """Wait for the Docker radbot server to be ready."""
    base = target_url.rstrip("/")
    headers = {"Authorization": f"Bearer {admin_token}"}

    for attempt in range(max_retries):
        try:
            resp = httpx.get(f"{base}/health", timeout=5.0)
            if resp.status_code == 200:
                logger.info("Docker radbot server is ready")
                return True
        except httpx.HTTPError:
            pass

        if attempt < max_retries - 1:
            logger.info(f"Server not ready, retrying in {delay}s... ({attempt + 1}/{max_retries})")
            time.sleep(delay)

    logger.error(f"Docker radbot server at {target_url} not reachable after {max_retries} attempts")
    return False


def verify_status(target_url, admin_token):
    """Print integration status from the Docker stack."""
    base = target_url.rstrip("/")
    headers = {"Authorization": f"Bearer {admin_token}"}

    try:
        resp = httpx.get(f"{base}/admin/api/status", headers=headers, timeout=10.0)
        if resp.status_code != 200:
            logger.warning(f"Could not fetch status: {resp.status_code}")
            return

        status = resp.json()
        logger.info("--- Docker stack integration status ---")
        for key, info in sorted(status.items()):
            if key.startswith("_"):
                continue
            s = info.get("status", "unknown") if isinstance(info, dict) else info
            msg = info.get("message", "") if isinstance(info, dict) else ""
            suffix = f" ({msg})" if msg else ""
            logger.info(f"  {key}: {s}{suffix}")
    except httpx.HTTPError as e:
        logger.warning(f"Could not verify status: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Seed Docker radbot stack with local dev credentials"
    )
    parser.add_argument(
        "--target-url",
        default="http://localhost:8000",
        help="URL of the Docker radbot instance (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--admin-token",
        required=True,
        help="Admin API bearer token for the Docker instance",
    )
    parser.add_argument(
        "--rewrite-localhost",
        action="store_true",
        help="Rewrite localhost/127.0.0.1 URLs to host.docker.internal",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Step 1: Wait for server
    if not wait_for_server(args.target_url, args.admin_token):
        sys.exit(1)

    # Step 2: Read local credentials
    logger.info("Reading credentials from local dev credential store...")
    credentials, config_sections = get_local_credentials()
    logger.info(
        f"Found {len(credentials)} credentials and {len(config_sections)} config sections"
    )

    if not credentials and not config_sections:
        logger.warning("Nothing to push")
        sys.exit(0)

    # Step 3: Push to Docker
    logger.info(f"Pushing to {args.target_url}...")
    errors = push_to_docker(
        args.target_url,
        args.admin_token,
        credentials,
        config_sections,
        args.rewrite_localhost,
    )

    # Step 4: Verify
    verify_status(args.target_url, args.admin_token)

    if errors:
        logger.warning(f"{errors} push(es) failed — some integrations may not work")
        sys.exit(2)

    logger.info("Seed complete")


if __name__ == "__main__":
    main()
