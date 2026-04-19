#!/usr/bin/env python3
"""Seed a CI radbot stack's config:* DB rows from the manifest.

Reads `scripts/e2e_seed_manifest.yml` config_sections, builds each section dict
from env vars or literal values, and PUTs to `/admin/api/config/{section}`.

Usage:
    uv run python scripts/seed_config_from_env.py \
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
from _admin_client import admin_client, put_config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("seed_config")

DEFAULT_MANIFEST = pathlib.Path(__file__).resolve().parent / "e2e_seed_manifest.yml"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target-url", required=True)
    p.add_argument("--admin-token", required=True)
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    return p.parse_args()


def _set_nested(target: dict, dotted_key: str, value) -> None:
    """Set target['a']['b']['c'] = value for dotted_key 'a.b.c'."""
    parts = dotted_key.split(".")
    cur = target
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def build_section(fields: dict) -> tuple[dict, list[str]]:
    """Resolve a section's fields from env/literal. Returns (payload, missing_required)."""
    payload: dict = {}
    missing: list[str] = []
    for dotted_key, spec in fields.items():
        if "value" in spec:
            _set_nested(payload, dotted_key, spec["value"])
        elif "env" in spec:
            env_var = spec["env"]
            required = spec.get("required", False)
            v = os.environ.get(env_var)
            if v:
                _set_nested(payload, dotted_key, v)
            elif required:
                missing.append(f"{dotted_key} ({env_var})")
        else:
            log.warning("field %s has neither 'value' nor 'env'; skipping", dotted_key)
    return payload, missing


def main() -> int:
    args = parse_args()
    manifest = yaml.safe_load(pathlib.Path(args.manifest).read_text())
    sections = manifest.get("config_sections", []) or []

    if not sections:
        log.warning("No config_sections in manifest; nothing to seed.")
        return 0

    all_missing: list[str] = []

    with admin_client(args.target_url, args.admin_token) as client:
        for entry in sections:
            section = entry["section"]
            fields = entry.get("fields", {}) or {}
            payload, missing = build_section(fields)
            all_missing.extend(missing)

            if not payload:
                log.info("config:%s has no resolvable fields; skipping PUT", section)
                continue

            try:
                put_config(client, section=section, payload=payload)
                log.info("seeded config:%s with keys=%s", section, sorted(payload.keys()))
            except Exception as e:
                log.error("failed to PUT config:%s: %s", section, e)
                return 1

    if all_missing:
        log.error("required config fields not provided: %s", ", ".join(all_missing))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
