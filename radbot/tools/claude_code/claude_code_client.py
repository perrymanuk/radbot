"""
Async wrapper for the Claude Code CLI with session support.

Provides plan mode (read-only, no --dangerously-skip-permissions) and
execute mode (full permissions) via ``--print --output-format stream-json``.

Session continuity is achieved via ``--resume <session_id>``.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Maximum output to keep in memory (characters)
_MAX_OUTPUT_CHARS = 200_000
# Default timeout for Claude Code processes (10 minutes)
_DEFAULT_TIMEOUT = 600


def _get_auth_token() -> tuple[Optional[str], str]:
    """Resolve the Claude Code auth token and its type.

    Returns:
        (token, kind) where kind is ``"api_key"`` or ``"oauth"``.
        API keys (``sk-ant-*``) go into ``ANTHROPIC_API_KEY``;
        everything else is treated as an OAuth token.
    """
    # 1. Explicit env vars
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        return api_key, "api_key"

    oauth = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if oauth:
        return oauth, "oauth"

    # 2. Credential store (admin UI saves here as "claude_code_oauth_token")
    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            token = store.get("claude_code_oauth_token")
            if token:
                # sk-ant-api* = API key, everything else = OAuth
                kind = "api_key" if token.startswith("sk-ant-api") else "oauth"
                logger.debug(f"Claude Code: Using {kind} token from credential store")
                return token, kind
    except Exception as e:
        logger.debug(f"Claude Code credential store lookup failed: {e}")

    return None, "oauth"


def _write_auth_token_files(token: str) -> None:
    """Write the OAuth token to ``~/.claude/remote/.oauth_token``.

    The CLI reads this file for headless/remote auth. For interactive PTY
    sessions, auth is provided via ``CLAUDE_CODE_OAUTH_TOKEN`` env var
    (set by ``terminal.py`` in the PTY environment).

    The container filesystem is ephemeral, so we write before each invocation.
    Uses ``Path.home()`` to resolve the correct home directory for the current user.
    """
    from pathlib import Path

    home = Path.home()
    remote_dir = home / ".claude" / "remote"
    token_path = remote_dir / ".oauth_token"
    try:
        remote_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        # Remove stale .api_key if it exists to avoid auth path confusion
        api_key_path = remote_dir / ".api_key"
        if api_key_path.exists():
            api_key_path.unlink()
        token_path.write_text(token)
        token_path.chmod(0o600)
    except Exception as e:
        logger.debug("Failed to write token to %s: %s", token_path, e)


def _ensure_onboarding_complete(workspace_dir: Optional[str] = None) -> None:
    """Ensure Claude Code can start without interactive prompts.

    Sets up three things in the Claude Code config:

    1. ``~/.claude.json`` → ``hasCompletedOnboarding: true``
       Without this, interactive mode forces the onboarding flow even
       when ``CLAUDE_CODE_OAUTH_TOKEN`` is set.

    2. ``~/.claude.json`` → ``projects.<path>.hasTrustDialogAccepted: true``
       Pre-accepts the per-directory trust dialog so the user doesn't
       have to click "Yes, I trust this folder" on first access.

    3. ``~/.claude/settings.json`` → ``skipDangerousModePermissionPrompt: true``
       Skips the bypass-permissions warning dialog when
       ``--dangerously-skip-permissions`` is used.

    All writes are idempotent.
    """
    import json
    from pathlib import Path

    home = Path.home()

    # 1 & 2: ~/.claude.json — onboarding flag + per-directory trust
    claude_json = home / ".claude.json"
    try:
        data = {}
        if claude_json.exists():
            data = json.loads(claude_json.read_text())

        dirty = False

        if not data.get("hasCompletedOnboarding"):
            data["hasCompletedOnboarding"] = True
            dirty = True

        if workspace_dir:
            projects = data.setdefault("projects", {})
            project = projects.setdefault(workspace_dir, {})
            if not project.get("hasTrustDialogAccepted"):
                project["hasTrustDialogAccepted"] = True
                dirty = True

        if dirty:
            claude_json.write_text(json.dumps(data, indent=2))
            claude_json.chmod(0o600)
    except Exception as e:
        logger.debug("Failed to write %s: %s", claude_json, e)

    # 3: ~/.claude/settings.json — skip bypass-permissions warning
    settings_json = home / ".claude" / "settings.json"
    try:
        settings = {}
        if settings_json.exists():
            settings = json.loads(settings_json.read_text())
        if not settings.get("skipDangerousModePermissionPrompt"):
            settings["skipDangerousModePermissionPrompt"] = True
            settings_json.parent.mkdir(parents=True, exist_ok=True)
            settings_json.write_text(json.dumps(settings, indent=2))
    except Exception as e:
        logger.debug("Failed to write %s: %s", settings_json, e)


def _claude_cli_available() -> bool:
    """Check whether the ``claude`` CLI is on PATH."""
    return shutil.which("claude") is not None


class ClaudeCodeClient:
    """Async wrapper for the Claude Code CLI."""

    def __init__(self, oauth_token: Optional[str] = None):
        if oauth_token:
            self._token = oauth_token
        else:
            self._token, _ = _get_auth_token()

    async def run_plan(
        self,
        working_dir: str,
        prompt: str,
        session_id: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """Run Claude Code in plan mode (no --dangerously-skip-permissions).

        Without --dangerously-skip-permissions, Claude Code in --print mode
        can only read files. Write operations require interactive approval
        which is not possible in non-interactive mode.

        Args:
            working_dir: Working directory for the Claude Code session
            prompt: The planning prompt
            session_id: Optional session ID for --resume
            timeout: Process timeout in seconds

        Returns:
            Dict with output, session_id, return_code, stderr
        """
        cmd = ["claude", "--print", "--verbose", "--output-format", "stream-json"]
        if session_id:
            cmd.extend(["--resume", session_id])
        cmd.extend(["-p", prompt])
        return await self._run_process(cmd, working_dir, timeout)

    async def run_execute(
        self,
        working_dir: str,
        prompt: str,
        session_id: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """Run Claude Code with full permissions.

        Uses --dangerously-skip-permissions. Should ONLY be called after
        the user has approved the plan.

        Args:
            working_dir: Working directory for the Claude Code session
            prompt: The execution prompt
            session_id: Optional session ID for --resume
            timeout: Process timeout in seconds

        Returns:
            Dict with output, session_id, return_code, stderr
        """
        cmd = [
            "claude",
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--dangerously-skip-permissions",
        ]
        if session_id:
            cmd.extend(["--resume", session_id])
        cmd.extend(["-p", prompt])
        return await self._run_process(cmd, working_dir, timeout)

    async def _run_process(
        self,
        cmd: list,
        working_dir: str,
        timeout: int,
    ) -> Dict[str, Any]:
        """Execute the Claude Code subprocess and parse stream-json output.

        Reads stdout line-by-line, collecting text content from stream-json
        events. Extracts session_id from the output for --resume support.
        """
        env = os.environ.copy()
        if self._token:
            if self._token.startswith("sk-ant-api"):
                # Standard Anthropic API key (sk-ant-api*)
                env["ANTHROPIC_API_KEY"] = self._token
            else:
                # OAuth token (sk-ant-oat*) or setup-token: use OAuth path.
                # ANTHROPIC_API_KEY must NOT be set — it disables OAuth mode.
                env["CLAUDE_CODE_OAUTH_TOKEN"] = self._token
                _write_auth_token_files(self._token)
        # Allow --dangerously-skip-permissions when running as root inside a
        # container.  Claude Code checks for IS_SANDBOX=1 to permit this.
        if os.getuid() == 0:
            env["IS_SANDBOX"] = "1"

        logger.info(
            "Running Claude Code: %s (cwd=%s)",
            " ".join(c if not c.startswith("--resume") else c for c in cmd[:6]),
            working_dir,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                env=env,
            )
        except FileNotFoundError:
            return {
                "status": "error",
                "output": "",
                "session_id": None,
                "return_code": -1,
                "stderr": "claude CLI not found on PATH",
            }

        output_parts: list[str] = []
        total_chars = 0
        extracted_session_id: Optional[str] = None

        try:
            async with asyncio.timeout(timeout):
                # Read stdout line-by-line (stream-json emits one JSON object per line)
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode("utf-8", errors="replace").strip()
                    if not line_str:
                        continue

                    try:
                        event = json.loads(line_str)
                    except json.JSONDecodeError:
                        # Not JSON — could be plain text fallback
                        if total_chars < _MAX_OUTPUT_CHARS:
                            output_parts.append(line_str)
                            total_chars += len(line_str)
                        continue

                    # Extract session_id from any event that carries it
                    if "session_id" in event:
                        extracted_session_id = event["session_id"]

                    # Extract text content from assistant messages
                    event_type = event.get("type", "")
                    if event_type == "assistant" or event_type == "result":
                        # assistant events have content blocks
                        for block in event.get("content", []):
                            if (
                                block.get("type") == "text"
                                and total_chars < _MAX_OUTPUT_CHARS
                            ):
                                text = block.get("text", "")
                                output_parts.append(text)
                                total_chars += len(text)
                        # result events may have a result field
                        if event_type == "result":
                            result_text = event.get("result", "")
                            if result_text and total_chars < _MAX_OUTPUT_CHARS:
                                output_parts.append(result_text)
                                total_chars += len(result_text)
                            # result event often has session_id
                            if not extracted_session_id and event.get("session_id"):
                                extracted_session_id = event["session_id"]

                # Wait for process completion
                stderr_bytes = await proc.stderr.read()
                await proc.wait()

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "status": "error",
                "output": "".join(output_parts),
                "session_id": extracted_session_id,
                "return_code": -1,
                "stderr": f"Process timed out after {timeout}s",
            }

        stderr_text = (
            stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
        )
        output_text = "\n".join(output_parts) if output_parts else ""
        return_code = proc.returncode or 0

        status = "success" if return_code == 0 else "error"
        if return_code != 0 and not output_text:
            output_text = stderr_text

        logger.info(
            "Claude Code finished: return_code=%d, output_len=%d, session=%s",
            return_code,
            len(output_text),
            extracted_session_id or "(none)",
        )

        return {
            "status": status,
            "output": output_text,
            "session_id": extracted_session_id,
            "return_code": return_code,
            "stderr": stderr_text,
        }


def get_claude_code_status() -> Dict[str, Any]:
    """Check whether Claude Code CLI is available and token actually works."""
    cli_available = _claude_cli_available()
    token, kind = _get_auth_token()
    token_configured = bool(token)

    if not cli_available:
        return {
            "status": "error",
            "message": "claude CLI not found on PATH",
            "cli_available": False,
            "token_configured": token_configured,
        }

    if not token_configured:
        return {
            "status": "error",
            "message": "No OAuth token configured — set claude_code_oauth_token in credential store or CLAUDE_CODE_OAUTH_TOKEN env var",  # noqa: E501
            "cli_available": True,
            "token_configured": False,
        }

    # Validate the token by running `claude auth status` with it
    try:
        import json as _json

        env = os.environ.copy()
        if kind == "api_key":
            env["ANTHROPIC_API_KEY"] = token
        else:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = token

        result = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        auth_info = _json.loads(result.stdout) if result.stdout.strip() else {}
        if not auth_info.get("loggedIn"):
            return {
                "status": "error",
                "message": f"Token configured but authentication failed — token may be expired or invalid",
                "cli_available": True,
                "token_configured": True,
            }
    except Exception as e:
        logger.debug("Could not validate token via CLI: %s", e)
        # Fall through — if we can't validate, report as configured

    return {
        "status": "ok",
        "message": "Claude Code CLI available and token authenticated",
        "cli_available": True,
        "token_configured": True,
    }
