"""
FunctionTool wrappers for Claude Code + GitHub workflows.

These tools are added to the Axel (execution) agent, enabling:
  1. Clone a GitHub repo via the GitHub App
  2. Run Claude Code in plan mode (read-only)
  3. Continue/iterate on the plan via --resume
  4. Execute the approved plan (--dangerously-skip-permissions)
  5. Commit and push changes back via the GitHub App
  6. List active workspaces

All tools return ``{"status": "success/error", ...}`` per project convention.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from google.adk.tools import FunctionTool

logger = logging.getLogger(__name__)

# Default workspace base directory
_DEFAULT_WORKSPACE_DIR = os.environ.get("RADBOT_WORKSPACE_DIR", "/app/workspaces")


def _get_workspace_dir() -> str:
    """Resolve the workspace base directory."""
    try:
        from radbot.config.config_loader import config_loader

        cfg = config_loader.get_integrations_config().get("claude_code", {})
        return cfg.get("workspace_dir", _DEFAULT_WORKSPACE_DIR)
    except Exception:
        return _DEFAULT_WORKSPACE_DIR


# ── Clone Repository ────────────────────────────────────────


def clone_repository(
    owner: str,
    repo: str,
    branch: str = "main",
) -> Dict[str, Any]:
    """Clone or update a GitHub repository using the configured GitHub App.

    Args:
        owner: Repository owner (user or organization), e.g. "perrymanuk"
        repo: Repository name, e.g. "radbot"
        branch: Branch to clone (defaults to "main")

    Returns:
        Dict with status, work_folder path, and clone details
    """
    try:
        from radbot.tools.github.github_app_client import get_github_client

        client = get_github_client()
        if not client:
            return {
                "status": "error",
                "message": "GitHub App not configured. Set up GitHub App credentials in Admin UI.",
            }

        workspace_dir = _get_workspace_dir()
        result = client.clone_repo(owner, repo, workspace_dir, branch)

        if result.get("status") == "success":
            local_path = result["local_path"]
            # Record workspace in DB
            try:
                from radbot.tools.claude_code.db import create_workspace

                create_workspace(owner, repo, branch, local_path)
            except Exception as e:
                logger.warning(f"Failed to record workspace in DB: {e}")

            return {
                "status": "success",
                "work_folder": local_path,
                "action": result.get("action", "clone"),
                "message": f"Repository {owner}/{repo} ({branch}) available at {local_path}",
            }
        return result

    except Exception as e:
        logger.error(f"clone_repository failed: {e}")
        return {"status": "error", "message": str(e)}


# ── Claude Code Plan ────────────────────────────────────────


def claude_code_plan(
    prompt: str,
    work_folder: str,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Claude Code in plan-only mode (read-only, no file modifications).

    This creates a plan for the requested changes without executing them.
    The returned session_id can be used with claude_code_continue or
    claude_code_execute to iterate on or execute the plan.

    Args:
        prompt: Description of what changes to plan
        work_folder: Path to the cloned repository
        session_id: Optional session ID to resume a previous planning session

    Returns:
        Dict with status, plan output, and session_id for continuation
    """
    try:
        from radbot.tools.claude_code.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient()
        result = asyncio.get_event_loop().run_until_complete(
            client.run_plan(work_folder, prompt, session_id)
        )

        # Store session_id in workspace DB if available
        if result.get("session_id"):
            _update_workspace_session(work_folder, result["session_id"])

        if result.get("status") == "success":
            return {
                "status": "success",
                "plan": result.get("output", ""),
                "session_id": result.get("session_id"),
                "message": "Plan created. Show it to the user and ask for approval before executing.",
            }
        return {
            "status": "error",
            "message": result.get("stderr") or result.get("output", "Unknown error"),
            "session_id": result.get("session_id"),
        }

    except Exception as e:
        logger.error(f"claude_code_plan failed: {e}")
        return {"status": "error", "message": str(e)}


# ── Claude Code Continue (iterate on plan) ──────────────────


def claude_code_continue(
    prompt: str,
    session_id: str,
    work_folder: str,
) -> Dict[str, Any]:
    """Continue an existing Claude Code planning session with feedback.

    Uses --resume to continue the conversation with the same context.

    Args:
        prompt: User feedback or refinement instructions
        session_id: Session ID from a previous claude_code_plan call
        work_folder: Path to the cloned repository

    Returns:
        Dict with status, updated plan output, and session_id
    """
    try:
        from radbot.tools.claude_code.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient()
        result = asyncio.get_event_loop().run_until_complete(
            client.run_plan(work_folder, prompt, session_id)
        )

        new_session_id = result.get("session_id") or session_id
        _update_workspace_session(work_folder, new_session_id)

        if result.get("status") == "success":
            return {
                "status": "success",
                "plan": result.get("output", ""),
                "session_id": new_session_id,
                "message": "Plan updated. Show it to the user and ask for approval.",
            }
        return {
            "status": "error",
            "message": result.get("stderr") or result.get("output", "Unknown error"),
            "session_id": new_session_id,
        }

    except Exception as e:
        logger.error(f"claude_code_continue failed: {e}")
        return {"status": "error", "message": str(e)}


# ── Claude Code Execute ─────────────────────────────────────


def claude_code_execute(
    prompt: str,
    work_folder: str,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a plan with Claude Code using full permissions.

    IMPORTANT: Only call this AFTER the user has explicitly approved the plan.
    This uses --dangerously-skip-permissions which allows Claude Code to
    modify files, run commands, etc.

    Args:
        prompt: Execution instruction (e.g. "Execute the plan" or specific guidance)
        work_folder: Path to the cloned repository
        session_id: Optional session ID from a previous planning session

    Returns:
        Dict with status, execution output, and session_id
    """
    try:
        from radbot.tools.claude_code.claude_code_client import ClaudeCodeClient

        client = ClaudeCodeClient()
        result = asyncio.get_event_loop().run_until_complete(
            client.run_execute(work_folder, prompt, session_id)
        )

        new_session_id = result.get("session_id") or session_id
        if new_session_id:
            _update_workspace_session(work_folder, new_session_id)

        if result.get("status") == "success":
            return {
                "status": "success",
                "output": result.get("output", ""),
                "session_id": new_session_id,
                "message": "Execution complete. Review the output and commit when ready.",
            }
        return {
            "status": "error",
            "message": result.get("stderr") or result.get("output", "Unknown error"),
            "session_id": new_session_id,
        }

    except Exception as e:
        logger.error(f"claude_code_execute failed: {e}")
        return {"status": "error", "message": str(e)}


# ── Commit and Push ─────────────────────────────────────────


def commit_and_push(
    work_folder: str,
    commit_message: str,
    branch: str = "main",
) -> Dict[str, Any]:
    """Stage all changes, commit, and push via the GitHub App.

    Args:
        work_folder: Path to the local repository
        commit_message: Commit message for the changes
        branch: Branch to push to (defaults to "main")

    Returns:
        Dict with status and push details
    """
    try:
        from radbot.tools.github.github_app_client import get_github_client

        client = get_github_client()
        if not client:
            return {
                "status": "error",
                "message": "GitHub App not configured. Set up credentials in Admin UI.",
            }

        result = client.push_changes(work_folder, branch, commit_message)
        return result

    except Exception as e:
        logger.error(f"commit_and_push failed: {e}")
        return {"status": "error", "message": str(e)}


# ── List Workspaces ─────────────────────────────────────────


def list_workspaces() -> Dict[str, Any]:
    """List all active cloned repository workspaces.

    Returns:
        Dict with status and list of workspaces
    """
    try:
        from radbot.tools.claude_code.db import list_active_workspaces

        workspaces = list_active_workspaces()
        # Serialize datetime/uuid fields
        formatted = []
        for ws in workspaces:
            formatted.append({
                "owner": ws.get("owner"),
                "repo": ws.get("repo"),
                "branch": ws.get("branch"),
                "local_path": ws.get("local_path"),
                "last_session_id": ws.get("last_session_id"),
                "last_used_at": str(ws.get("last_used_at", "")),
            })
        return {
            "status": "success",
            "workspaces": formatted,
            "count": len(formatted),
        }

    except Exception as e:
        logger.error(f"list_workspaces failed: {e}")
        return {"status": "error", "message": str(e), "workspaces": []}


# ── Helpers ─────────────────────────────────────────────────


def _update_workspace_session(work_folder: str, session_id: str) -> None:
    """Update the session_id on the workspace matching work_folder."""
    try:
        from radbot.tools.claude_code.db import list_active_workspaces, update_session_id

        for ws in list_active_workspaces():
            if ws.get("local_path") == work_folder:
                update_session_id(
                    ws["owner"], ws["repo"], ws["branch"], session_id
                )
                return
    except Exception as e:
        logger.debug(f"Failed to update workspace session_id: {e}")


# ── Tool Registration ───────────────────────────────────────

CLAUDE_CODE_TOOLS = [
    FunctionTool(clone_repository),
    FunctionTool(claude_code_plan),
    FunctionTool(claude_code_continue),
    FunctionTool(claude_code_execute),
    FunctionTool(commit_and_push),
    FunctionTool(list_workspaces),
]
