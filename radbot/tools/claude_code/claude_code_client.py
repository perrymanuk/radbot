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
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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


# Common install paths checked when the CLI isn't on PATH. Covers the Dockerfile
# symlink (`/usr/local/bin/claude`), distro packaging, and NPM global defaults
# for both root and user installs.
_CLAUDE_FALLBACK_PATHS = (
    "/usr/local/bin/claude",
    "/usr/bin/claude",
    "/opt/homebrew/bin/claude",
)


def _get_github_token() -> Optional[str]:
    """Fetch a short-lived GitHub App installation token for subprocess injection.

    Returns None (with a debug log) if the GitHub App integration is not
    configured — callers should degrade gracefully. The returned token is
    never written to logs.
    """
    try:
        from radbot.tools.github.github_app_client import get_github_client

        client = get_github_client()
        if client is None:
            logger.debug("GitHub App client not configured — skipping token injection")
            return None
        return client._get_installation_token()
    except Exception as e:
        logger.debug("GitHub App token unavailable: %s", e)
        return None


def _resolve_claude_cli() -> Optional[str]:
    """Locate the ``claude`` CLI executable.

    Resolution order:
      1. ``CLAUDE_CLI_PATH`` env var (explicit override)
      2. ``shutil.which("claude")`` on the inherited PATH
      3. A short list of common install paths (container symlink, brew, npm)
      4. ``~/.npm-global/bin/claude`` (per-user npm prefix)
    """
    override = os.environ.get("CLAUDE_CLI_PATH")
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        return override

    found = shutil.which("claude")
    if found:
        return found

    from pathlib import Path

    candidates = list(_CLAUDE_FALLBACK_PATHS)
    candidates.append(str(Path.home() / ".npm-global" / "bin" / "claude"))
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _claude_cli_available() -> bool:
    """Check whether the ``claude`` CLI can be located."""
    return _resolve_claude_cli() is not None


@dataclass
class BackgroundSession:
    """State for a long-running Claude Code CLI session.

    Spawned by ``ClaudeCodeClient.start_background_session`` and managed by
    a reader task that consumes the stream-json stdout. Poll the ``output``
    / ``status`` / ``waiting_for_input`` fields; reply by writing to
    ``proc.stdin`` via ``ClaudeCodeClient.send_input``.
    """

    job_id: str
    proc: asyncio.subprocess.Process
    working_dir: str
    status: str = "running"  # running | waiting_for_input | complete | error
    output: List[str] = field(default_factory=list)
    stderr_chunks: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    return_code: Optional[int] = None
    waiting_for_input: bool = False
    pending_question: Optional[str] = None
    reader_task: Optional[asyncio.Task] = None
    stderr_task: Optional[asyncio.Task] = None


class ClaudeCodeClient:
    """Async wrapper for the Claude Code CLI."""

    def __init__(self, oauth_token: Optional[str] = None):
        if oauth_token:
            self._token = oauth_token
        else:
            self._token, _ = _get_auth_token()

    def _build_env(self, inject_github_token: bool = False) -> Dict[str, str]:
        """Build the subprocess environment with auth + sandbox flags."""
        env = os.environ.copy()
        if self._token:
            if self._token.startswith("sk-ant-api"):
                env["ANTHROPIC_API_KEY"] = self._token
            else:
                env["CLAUDE_CODE_OAUTH_TOKEN"] = self._token
                _write_auth_token_files(self._token)
        if os.getuid() == 0:
            env["IS_SANDBOX"] = "1"
        if inject_github_token:
            gh_token = _get_github_token()
            if gh_token:
                env["GH_TOKEN"] = gh_token
                env["GITHUB_TOKEN"] = gh_token
                logger.debug("GitHub App token injected into subprocess env")
            else:
                logger.warning("inject_github_token=True but no GitHub App token available")
        return env

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
        claude_bin = _resolve_claude_cli() or "claude"
        cmd = [claude_bin, "--print", "--verbose", "--output-format", "stream-json"]
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
        claude_bin = _resolve_claude_cli() or "claude"
        cmd = [
            claude_bin,
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
        env = self._build_env()

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
                "stderr": "claude CLI not found — set CLAUDE_CLI_PATH or install the CLI",
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

    # ── Background session (kickoff / poll / reply) ─────────────

    async def start_background_session(
        self,
        working_dir: str,
        prompt: str,
        session_id: Optional[str] = None,
        inject_github_token: bool = False,
    ) -> BackgroundSession:
        """Spawn a long-running Claude Code CLI session in the background.

        Runs with ``--dangerously-skip-permissions`` so routine file/bash
        operations don't hang waiting for approval. Output is collected by
        a reader task; the caller polls via the returned ``BackgroundSession``
        and replies to prompt events by writing to ``proc.stdin``.

        Args:
            working_dir: Working directory for the Claude Code session
            prompt: Initial prompt
            session_id: Optional CLI session ID for ``--resume``
            inject_github_token: When True, fetch a GitHub App installation
                token and inject it as GH_TOKEN and GITHUB_TOKEN so the
                Claude Code subprocess can push branches and open PRs without
                interactive auth prompts.

        Returns:
            BackgroundSession tracking the running process.
        """
        _ensure_onboarding_complete(working_dir)

        claude_bin = _resolve_claude_cli() or "claude"
        cmd = [
            claude_bin,
            "--print",
            "--verbose",
            "--output-format",
            "stream-json",
            "--dangerously-skip-permissions",
        ]
        if session_id:
            cmd.extend(["--resume", session_id])
        cmd.extend(["-p", prompt])

        env = self._build_env(inject_github_token=inject_github_token)

        logger.info(
            "Starting background Claude Code session (cwd=%s, resume=%s)",
            working_dir,
            session_id or "(new)",
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
            env=env,
        )

        session = BackgroundSession(
            job_id=str(uuid.uuid4()),
            proc=proc,
            working_dir=working_dir,
            session_id=session_id,
        )
        session.reader_task = asyncio.create_task(self._consume_stdout(session))
        session.stderr_task = asyncio.create_task(self._consume_stderr(session))
        return session

    async def _consume_stdout(self, session: BackgroundSession) -> None:
        """Parse stream-json stdout line-by-line and update session state."""
        total = 0
        proc = session.proc
        assert proc.stdout is not None
        try:
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
                    if total < _MAX_OUTPUT_CHARS:
                        session.output.append(line_str)
                        total += len(line_str)
                    continue

                if "session_id" in event and event["session_id"]:
                    session.session_id = event["session_id"]

                event_type = event.get("type", "")

                # Detect prompt/question events — CLI is waiting for a reply.
                # Multiple possible signals: explicit permission/input request
                # event types, or AskUserQuestion-style tool_use blocks.
                if event_type in {
                    "permission_request",
                    "input_request",
                    "ask_user_question",
                }:
                    session.waiting_for_input = True
                    session.status = "waiting_for_input"
                    session.pending_question = (
                        event.get("question")
                        or event.get("prompt")
                        or event.get("message")
                        or line_str
                    )

                if event_type in {"assistant", "result"}:
                    for block in event.get("content", []) or []:
                        btype = block.get("type")
                        if btype == "text" and total < _MAX_OUTPUT_CHARS:
                            text = block.get("text", "")
                            session.output.append(text)
                            total += len(text)
                        elif btype == "tool_use":
                            tool_name = (block.get("name") or "").lower()
                            if "askuserquestion" in tool_name or tool_name in {
                                "ask_user_question",
                                "ask",
                            }:
                                session.waiting_for_input = True
                                session.status = "waiting_for_input"
                                session.pending_question = json.dumps(
                                    block.get("input") or {}
                                )
                    if event_type == "result":
                        result_text = event.get("result", "")
                        if result_text and total < _MAX_OUTPUT_CHARS:
                            session.output.append(result_text)
                            total += len(result_text)
        except Exception as e:
            logger.warning("Claude background reader error: %s", e)
            session.stderr_chunks.append(f"[reader error] {e}")
        finally:
            await proc.wait()
            session.return_code = proc.returncode
            if session.status != "waiting_for_input":
                session.status = "complete" if (proc.returncode or 0) == 0 else "error"
            logger.info(
                "Claude background session finished: job_id=%s rc=%s session=%s",
                session.job_id,
                session.return_code,
                session.session_id or "(none)",
            )

    async def _consume_stderr(self, session: BackgroundSession) -> None:
        """Drain stderr into the session log."""
        proc = session.proc
        assert proc.stderr is not None
        try:
            while True:
                chunk = await proc.stderr.readline()
                if not chunk:
                    break
                session.stderr_chunks.append(chunk.decode("utf-8", errors="replace"))
        except Exception as e:
            logger.debug("stderr reader error: %s", e)

    async def send_input(self, session: BackgroundSession, reply: str) -> None:
        """Write a reply to the session's stdin and flush.

        Raises:
            RuntimeError if stdin is not available (process ended or pipe closed).
        """
        proc = session.proc
        if proc.stdin is None or proc.stdin.is_closing():
            raise RuntimeError("stdin not available on this session")
        payload = reply if reply.endswith("\n") else reply + "\n"
        proc.stdin.write(payload.encode("utf-8"))
        await proc.stdin.drain()
        session.waiting_for_input = False
        session.pending_question = None
        session.status = "running"


def get_claude_code_status() -> Dict[str, Any]:
    """Check whether Claude Code CLI is available and token actually works."""
    cli_available = _claude_cli_available()
    token, kind = _get_auth_token()
    token_configured = bool(token)

    if not cli_available:
        return {
            "status": "error",
            "message": "claude CLI not found — set CLAUDE_CLI_PATH or install the CLI",
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

        claude_bin = _resolve_claude_cli() or "claude"
        result = subprocess.run(
            [claude_bin, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        auth_info = _json.loads(result.stdout) if result.stdout.strip() else {}
        if not auth_info.get("loggedIn"):
            return {
                "status": "error",
                "message": "Token configured but authentication failed — token may be expired or invalid",
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
