"""
Lazy-initialized singleton GitHub App client.

Reads config from ``integrations.github`` (merged file+DB config) first,
then falls back to the credential store (``github_app_private_key``),
then to environment variables.

Uses GitHub App JWT authentication with short-lived installation tokens
for repo clone/push operations.
"""

import asyncio
import logging
import os
import subprocess
import time
from typing import Any, Dict, Optional

import httpx
import jwt

logger = logging.getLogger(__name__)

_client: Optional["GitHubAppClient"] = None
_initialized = False

GITHUB_API_BASE = "https://api.github.com"


def _get_config() -> dict:
    """Pull GitHub App settings from config manager, credential store, then env."""
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("github", {})
    except Exception:
        cfg = {}

    app_id = cfg.get("app_id") or os.environ.get("GITHUB_APP_ID")
    installation_id = cfg.get("installation_id") or os.environ.get(
        "GITHUB_INSTALLATION_ID"
    )
    private_key = cfg.get("private_key") or os.environ.get("GITHUB_APP_PRIVATE_KEY")
    enabled = cfg.get("enabled", True)

    # Try credential store for private key if not found above
    if not private_key:
        try:
            from radbot.credentials.store import get_credential_store

            store = get_credential_store()
            if store.available:
                private_key = store.get("github_app_private_key")
                if private_key:
                    logger.debug("GitHub: Using private key from credential store")
        except Exception as e:
            logger.debug(f"GitHub credential store lookup failed: {e}")

    return {
        "app_id": app_id,
        "installation_id": installation_id,
        "private_key": private_key,
        "enabled": enabled,
    }


class GitHubAppClient:
    """GitHub App client with JWT auth and installation token management."""

    def __init__(self, app_id: str, installation_id: str, private_key: str):
        self.app_id = app_id
        self.installation_id = installation_id
        self._private_key = private_key
        self._installation_token: Optional[str] = None
        self._token_expires_at: float = 0

    def _generate_jwt(self) -> str:
        """Generate a short-lived JWT for GitHub App authentication."""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # Issued 60s ago to account for clock drift
            "exp": now + (10 * 60),  # Expires in 10 minutes
            "iss": self.app_id,
        }
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    def _get_installation_token(self) -> str:
        """Get or refresh the installation access token (sync, for git operations)."""
        now = time.time()
        if self._installation_token and now < self._token_expires_at - 60:
            return self._installation_token

        app_jwt = self._generate_jwt()
        resp = httpx.post(
            f"{GITHUB_API_BASE}/app/installations/{self.installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        self._installation_token = data["token"]
        # GitHub installation tokens expire in 1 hour
        self._token_expires_at = now + 3600
        logger.debug("GitHub installation token refreshed")
        return self._installation_token

    def clone_repo(
        self,
        owner: str,
        repo: str,
        workspace_dir: str,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Clone a repo using the installation token, or pull if it already exists.

        Args:
            owner: Repository owner (user or org)
            repo: Repository name
            workspace_dir: Base directory for workspaces
            branch: Branch to clone (default: repo default branch)

        Returns:
            Dict with status, local_path, and any error info
        """
        token = self._get_installation_token()
        clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
        local_path = os.path.join(workspace_dir, owner, repo)

        try:
            if os.path.isdir(os.path.join(local_path, ".git")):
                # Repo already cloned — update remote URL (token may have changed) and pull
                self._run_git(
                    ["git", "remote", "set-url", "origin", clone_url],
                    cwd=local_path,
                )
                pull_cmd = ["git", "pull", "--ff-only"]
                self._run_git(pull_cmd, cwd=local_path)
                logger.info(f"Updated existing clone at {local_path}")
                return {"status": "success", "local_path": local_path, "action": "pull"}
            else:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                clone_cmd = ["git", "clone", "--depth", "50"]
                if branch:
                    clone_cmd.extend(["--branch", branch])
                clone_cmd.extend([clone_url, local_path])
                self._run_git(clone_cmd)
                logger.info(f"Cloned {owner}/{repo} to {local_path}")
                return {
                    "status": "success",
                    "local_path": local_path,
                    "action": "clone",
                }
        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e.stderr}")
            return {
                "status": "error",
                "message": f"Git operation failed: {e.stderr[:500]}",
            }
        except Exception as e:
            logger.error(f"Clone failed: {e}")
            return {"status": "error", "message": str(e)}

    def push_changes(
        self,
        local_path: str,
        branch: str,
        commit_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stage all changes, commit, and push to the remote.

        Args:
            local_path: Path to the local git repository
            branch: Branch to push to
            commit_message: Commit message (if None, no commit is made)

        Returns:
            Dict with status info
        """
        try:
            # Refresh token and update remote URL
            token = self._get_installation_token()
            # Read the current remote URL to get owner/repo
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=local_path,
                check=True,
            )
            old_url = result.stdout.strip()
            # Replace the token in the URL
            # URL format: https://x-access-token:TOKEN@github.com/owner/repo.git
            import re

            new_url = re.sub(
                r"https://[^@]*@github\.com/",
                f"https://x-access-token:{token}@github.com/",
                old_url,
            )
            if new_url == old_url and "x-access-token" not in old_url:
                # Original URL wasn't token-based, reconstruct from path
                # e.g. https://github.com/owner/repo.git
                new_url = old_url.replace(
                    "https://github.com/",
                    f"https://x-access-token:{token}@github.com/",
                )
            self._run_git(
                ["git", "remote", "set-url", "origin", new_url],
                cwd=local_path,
            )

            # Ensure we're on the right branch
            self._run_git(
                ["git", "checkout", "-B", branch],
                cwd=local_path,
            )

            # Stage, commit if requested
            if commit_message:
                self._run_git(["git", "add", "-A"], cwd=local_path)
                self._run_git(
                    ["git", "commit", "-m", commit_message],
                    cwd=local_path,
                )

            # Push
            self._run_git(
                ["git", "push", "-u", "origin", branch],
                cwd=local_path,
            )
            logger.info(f"Pushed changes to {branch}")
            return {"status": "success", "branch": branch}
        except subprocess.CalledProcessError as e:
            logger.error(f"Push failed: {e.stderr}")
            return {
                "status": "error",
                "message": f"Push failed: {e.stderr[:500]}",
            }
        except Exception as e:
            logger.error(f"Push failed: {e}")
            return {"status": "error", "message": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Health check — GET /app to verify JWT works."""
        try:
            app_jwt = self._generate_jwt()
            resp = httpx.get(
                f"{GITHUB_API_BASE}/app",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "ok",
                "app_name": data.get("name", "unknown"),
                "app_id": data.get("id"),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def _run_git(cmd: list, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
        """Run a git command with shell=False."""
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            check=True,
            timeout=300,
        )


def get_github_client() -> Optional[GitHubAppClient]:
    """Return the singleton GitHub App client, or None if unconfigured."""
    global _client, _initialized

    if _initialized:
        return _client

    cfg = _get_config()
    if not cfg["enabled"]:
        logger.info("GitHub App integration is disabled in config")
        _initialized = True
        return None

    app_id = cfg["app_id"]
    installation_id = cfg["installation_id"]
    private_key = cfg["private_key"]

    if not app_id or not installation_id or not private_key:
        logger.info(
            "GitHub App integration not configured — set integrations.github "
            "in config or GITHUB_APP_ID/GITHUB_INSTALLATION_ID/GITHUB_APP_PRIVATE_KEY env vars"
        )
        _initialized = True
        return None

    try:
        client = GitHubAppClient(str(app_id), str(installation_id), private_key)
        status = client.get_status()
        if status.get("status") == "ok":
            logger.info(
                "Connected to GitHub App '%s' (ID: %s)",
                status.get("app_name"),
                status.get("app_id"),
            )
        else:
            logger.warning("GitHub App health check returned: %s", status)
        _client = client
        _initialized = True
        return _client
    except Exception as e:
        logger.error("Failed to initialise GitHub App client: %s", e)
        return None


def reset_github_client() -> None:
    """Clear the singleton so the next call re-initializes with fresh config."""
    global _client, _initialized
    _client = None
    _initialized = False
    logger.info("GitHub App client singleton reset")
