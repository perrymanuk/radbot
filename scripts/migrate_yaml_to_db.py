#!/usr/bin/env python3
"""Migrate YAML config sections into the PostgreSQL credential store.

Usage::

    # Dry-run (default) — shows what would be stored
    uv run python scripts/migrate_yaml_to_db.py config.yaml.bak

    # Actually write to DB
    uv run python scripts/migrate_yaml_to_db.py config.yaml.bak --apply

Requires:
- A valid ``database`` section in the current ``config.yaml`` (bootstrap)
- ``RADBOT_CREDENTIAL_KEY`` env var or ``credential_key`` in ``config.yaml``
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

# Ensure project root is on sys.path so radbot imports work
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("migrate_yaml_to_db")

# Sections that should NOT be migrated (they stay in config.yaml)
BOOTSTRAP_SECTIONS = {"database", "credential_key", "admin_token"}

# Sensitive values that should also be stored as named credentials
NAMED_CREDENTIALS = [
    # (yaml_path_tuple, credential_name, credential_type)
    (("api_keys", "google"), "google_api_key", "api_key"),
    (("api_keys", "tavily"), "tavily_api_key", "api_key"),
    (("integrations", "home_assistant", "token"), "ha_token", "credential"),
    (("integrations", "jira", "api_token"), "jira_api_token", "credential"),
]


def _extract(data: dict, path: tuple):
    """Walk a nested dict by key path, return value or None."""
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def main():
    parser = argparse.ArgumentParser(
        description="Migrate YAML config into the PostgreSQL credential store."
    )
    parser.add_argument(
        "yaml_file",
        help="Path to the YAML config file to migrate (e.g. config.yaml.bak)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Actually write to the database (default is dry-run)",
    )
    args = parser.parse_args()

    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        logger.error(f"File not found: {yaml_path}")
        sys.exit(1)

    with open(yaml_path) as f:
        data = yaml.safe_load(f) or {}

    if not data:
        logger.error("YAML file is empty or invalid")
        sys.exit(1)

    # ----------------------------------------------------------------
    # Collect what we will store
    # ----------------------------------------------------------------
    config_sections: list[tuple[str, str, str]] = []  # (db_name, json_value, description)
    credentials: list[tuple[str, str, str, str]] = []  # (name, value, type, description)

    for section_name, section_data in data.items():
        if section_name in BOOTSTRAP_SECTIONS:
            logger.info(f"Skipping bootstrap section: {section_name}")
            continue
        json_value = json.dumps(section_data, indent=2, default=str)
        db_name = f"config:{section_name}"
        config_sections.append((db_name, json_value, f"Config section: {section_name}"))

    for yaml_path_tuple, cred_name, cred_type in NAMED_CREDENTIALS:
        value = _extract(data, yaml_path_tuple)
        if value:
            credentials.append((
                cred_name,
                str(value),
                cred_type,
                f"From {'.'.join(yaml_path_tuple)} in YAML",
            ))

    # ----------------------------------------------------------------
    # Report
    # ----------------------------------------------------------------
    print("\n=== Config sections to store ===")
    for db_name, json_value, desc in config_sections:
        preview = json_value[:120].replace("\n", " ")
        print(f"  {db_name:30s}  {preview}...")

    print(f"\n=== Named credentials to store ({len(credentials)}) ===")
    for name, value, ctype, desc in credentials:
        masked = value[:4] + "***" + value[-4:] if len(value) > 10 else "***"
        print(f"  {name:30s}  type={ctype:12s}  value={masked}")

    if not args.apply:
        print("\n** DRY RUN — pass --apply to write to the database **\n")
        return

    # ----------------------------------------------------------------
    # Write to DB
    # ----------------------------------------------------------------
    print("\nApplying to database...")

    # Init credential store schema
    from radbot.credentials.store import CredentialStore, get_credential_store

    CredentialStore.init_schema()
    store = get_credential_store()

    if not store.available:
        logger.error(
            "Credential store unavailable. Set RADBOT_CREDENTIAL_KEY or "
            "credential_key in config.yaml."
        )
        sys.exit(1)

    for db_name, json_value, desc in config_sections:
        store.set(db_name, json_value, credential_type="config", description=desc)
        print(f"  Stored {db_name}")

    for name, value, ctype, desc in credentials:
        store.set(name, value, credential_type=ctype, description=desc)
        print(f"  Stored credential {name}")

    print(f"\nDone. {len(config_sections)} config sections and {len(credentials)} credentials stored.")


if __name__ == "__main__":
    main()
