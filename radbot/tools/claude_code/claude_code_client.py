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
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Maximum output to keep in memory (characters)
_MAX_OUTPUT_CHARS = 200_000
# Default timeout for Claude Code processes (10 minutes)
_DEFAULT_TIMEOUT = 600


def _get_oauth_token() -> Optional[str]:
    """Resolve the Claude Code OAuth token from credential store or env."""
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if token:
        return token

    try:
        from radbot.credentials.store import get_credential_store

        store = get_credential_store()
        if store.available:
            token = store.get("claude_code_oauth_token")
            if token:
                logger.debug("Claude Code: Using OAuth token from credential store")
                return token
    except Exception as e:
        logger.debug(f"Claude Code credential store lookup failed: {e}")

    return None


def _claude_cli_available() -> bool:
    """Check whether the ``claude`` CLI is on PATH."""
    return shutil.which("claude") is not None


class ClaudeCodeClient:
    """Async wrapper for the Claude Code CLI."""

    def __init__(self, oauth_token: Optional[str] = None):
        self._oauth_token = oauth_token or _get_oauth_token()

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
        cmd = ["claude", "--print", "--output-format", "stream-json"]
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
        if self._oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self._oauth_token

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
                            if block.get("type") == "text" and total_chars < _MAX_OUTPUT_CHARS:
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

        stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
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
    """Check whether Claude Code CLI is available and token is configured."""
    cli_available = _claude_cli_available()
    token_configured = bool(_get_oauth_token())

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
            "message": "No OAuth token configured — set claude_code_oauth_token in credential store or CLAUDE_CODE_OAUTH_TOKEN env var",
            "cli_available": True,
            "token_configured": False,
        }

    return {
        "status": "ok",
        "message": "Claude Code CLI available and token configured",
        "cli_available": True,
        "token_configured": True,
    }
