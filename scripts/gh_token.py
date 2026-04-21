#!/usr/bin/env python3
"""Print a fresh GitHub App installation token for use with the gh CLI.

Intended usage inside the radbot container (PT79):

    GH_TOKEN=$(gh-token) gh pr list

Reads GitHub App credentials from the same sources as
``radbot.tools.github.github_app_client`` (config → credential store → env).
Exits non-zero if the App is not configured.
"""
from __future__ import annotations

import sys


def main() -> int:
    # Merge DB-stored config (admin UI saves integrations.github there) into
    # the in-memory ConfigLoader. Without this, only file-based config.yaml is
    # visible — and integrations.github lives in the credential store, not the
    # bootstrap config.
    from radbot.config.config_loader import config_loader

    config_loader.load_db_config()

    from radbot.tools.github.github_app_client import get_github_client

    client = get_github_client()
    if client is None:
        print("gh-token: GitHub App not configured", file=sys.stderr)
        return 1
    try:
        token = client._get_installation_token()
    except Exception as exc:
        print(f"gh-token: failed to mint installation token: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
