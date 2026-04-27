"""Scout's async kickoff/poll/reply tools over Claude Code CLI.

Wraps :class:`radbot.tools.claude_code.claude_code_client.ClaudeCodeClient`'s
background-session API. Scout fires ``start_claude_session`` with a finalized
plan, polls progress via ``poll_claude_session``, and answers any
prompt/question events via ``reply_claude_session``.

We deliberately do **not** use the ``claude-agent-sdk`` Python package: it
requires a raw ``ANTHROPIC_API_KEY``, but RadBot authenticates Claude Code
via the custom ``CLAUDE_CODE_OAUTH_TOKEN`` flow already wired into
``ClaudeCodeClient`` (credential store → ``~/.claude/remote/.oauth_token``
+ onboarding/trust/sandbox setup). See EX26 / PT77 in Telos.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, Optional

from google.adk.tools import FunctionTool
from pydantic import BaseModel, Field, ValidationError, field_validator

from radbot.tools.claude_code.claude_code_client import (
    BackgroundSession,
    ClaudeCodeClient,
)

# Hard cap on bounded-sync execution — MCP turn budgets are typically 60–120s.
# Past this point we yield a job_id and hand off to poll/reply.
_RUN_SYNC_CAP_SECONDS = 90
# Poll interval while waiting for completion / waiting_for_input inside the cap.
_RUN_SYNC_POLL_INTERVAL = 0.25

# Regex enforced on every Claude Code session kickoff. EX35: scout must dispatch
# work via a Telos ref (Project Task or Exploration), never via raw prompt.
_TASK_REF_RE = re.compile(r"^(PT|EX)\d+$")

logger = logging.getLogger(__name__)


class ClaudeSessionRequest(BaseModel):
    """Strict parameter envelope for Claude Code session kickoff (EX35).

    Forces every dispatch through a Telos reference so scout cannot smuggle a
    raw bash command, multi-line plan, or one-off prompt into Claude Code —
    closing the escape hatch that bypassed the bipartite review loop.
    """

    task_ref: str = Field(
        ...,
        description="Telos ref code — must match ^(PT|EX)\\d+$ (e.g. 'PT96', 'EX35').",
    )
    target_dir: str = Field(
        ..., description="Working directory for the CLI subprocess."
    )

    @field_validator("task_ref")
    @classmethod
    def _validate_task_ref(cls, v: str) -> str:
        if not _TASK_REF_RE.match(v):
            raise ValueError(
                f"task_ref must match ^(PT|EX)\\d+$ (got {v!r}). "
                "Pass a Telos task or exploration ref (e.g. 'PT96'), not a raw prompt. "
                "If no task exists, draft one with telos_add_task first."
            )
        return v


# Module-level session registry. Job IDs live for the lifetime of the process;
# a restart drops in-flight sessions (acceptable — Scout can restart them).
_SESSIONS: Dict[str, BackgroundSession] = {}
# Cursor per job_id so poll only returns output the caller hasn't seen yet.
_CURSORS: Dict[str, int] = {}


def _snapshot(session: BackgroundSession, new_text: str) -> Dict[str, Any]:
    return {
        "status": "success",
        "job_id": session.job_id,
        "job_status": session.status,
        "output": new_text,
        "waiting_for_input": session.waiting_for_input,
        "pending_question": session.pending_question,
        "session_id": session.session_id,
        "return_code": session.return_code,
        "stderr": (
            "".join(session.stderr_chunks)[-2000:] if session.stderr_chunks else ""
        ),
    }


async def start_claude_session(
    task_ref: str,
    target_dir: str,
    auto_ship: bool = True,
    resume_session_id: Optional[str] = None,
    inject_github_token: bool = False,
) -> Dict[str, Any]:
    """Kick off a Claude Code CLI session in the background and return a job_id.

    The session runs with ``--dangerously-skip-permissions`` so routine file /
    bash operations don't hang on approval. Returns immediately — Scout must
    ``poll_claude_session`` or ``wait_claude_session`` to collect output.

    The prompt is **always synthesized** from ``task_ref`` (e.g. ``"PT96"`` →
    ``"execute PT96 and use /ship when complete"``). Raw prompts are not
    accepted — every dispatch must go through a Telos reference. See EX35.

    Args:
        task_ref: Telos task / exploration ref code (must match
            ``^(PT|EX)\\d+$``). Rendered into ``execute <ref>`` for the CLI.
        target_dir: Working directory the CLI runs inside.
        auto_ship: When True, append ``and use /ship when complete`` so the
            session routes into the ship-it skill flow on success.
        resume_session_id: Optional CLI ``session_id`` to resume an earlier run.
        inject_github_token: When True, fetch a GitHub App installation token
            and inject it as GH_TOKEN / GITHUB_TOKEN so the subprocess can
            push branches and open PRs without interactive auth prompts.

    Returns:
        ``{status, job_id, message}`` on success, or
        ``{status: 'error', message: <validation error>}`` if ``task_ref`` is
        malformed (caught from Pydantic so the agent loop does not crash).
    """
    try:
        request = ClaudeSessionRequest(task_ref=task_ref, target_dir=target_dir)
    except ValidationError as e:
        return {"status": "error", "message": str(e)}

    prompt = _synthesize_prompt(request.task_ref, auto_ship)

    try:
        client = ClaudeCodeClient()
        session = await client.start_background_session(
            working_dir=request.target_dir,
            prompt=prompt,
            session_id=resume_session_id,
            inject_github_token=inject_github_token,
        )
        _SESSIONS[session.job_id] = session
        _CURSORS[session.job_id] = 0
        return {
            "status": "success",
            "job_id": session.job_id,
            "message": (
                "Claude Code session started in the background. "
                "Poll with poll_claude_session(job_id). If waiting_for_input "
                "becomes true, respond with reply_claude_session(job_id, reply)."
            ),
        }
    except Exception as e:
        logger.error("start_claude_session failed: %s", e)
        return {"status": "error", "message": str(e)}


async def poll_claude_session(job_id: str) -> Dict[str, Any]:
    """Poll a background Claude Code session for new output and status.

    Returns only output produced since the previous poll for this job_id.

    Args:
        job_id: The id returned by ``start_claude_session``.

    Returns:
        ``{status, job_id, job_status, output, waiting_for_input,
        pending_question, session_id, return_code, stderr}``.
        ``job_status`` is one of: running, waiting_for_input, complete, error.
    """
    session = _SESSIONS.get(job_id)
    if session is None:
        return {"status": "error", "message": f"Unknown job_id: {job_id}"}
    cursor = _CURSORS.get(job_id, 0)
    chunks = session.output[cursor:]
    _CURSORS[job_id] = len(session.output)
    return _snapshot(session, "".join(chunks))


async def reply_claude_session(job_id: str, reply: str) -> Dict[str, Any]:
    """Send a reply to a background Claude Code session waiting for input.

    Writes the reply to the CLI's stdin and flushes. Clears the
    ``waiting_for_input`` flag so the next poll reflects resumed execution.

    Args:
        job_id: The id returned by ``start_claude_session``.
        reply: Text to send (a trailing newline is added if missing).

    Returns:
        ``{status, message, ...poll snapshot}``.
    """
    session = _SESSIONS.get(job_id)
    if session is None:
        return {"status": "error", "message": f"Unknown job_id: {job_id}"}
    try:
        client = ClaudeCodeClient()
        await client.send_input(session, reply)
    except Exception as e:
        logger.error("reply_claude_session failed for %s: %s", job_id, e)
        return {"status": "error", "message": str(e)}
    cursor = _CURSORS.get(job_id, 0)
    chunks = session.output[cursor:]
    _CURSORS[job_id] = len(session.output)
    snap = _snapshot(session, "".join(chunks))
    snap["message"] = "Reply sent"
    return snap


def _synthesize_prompt(task_ref: str, auto_ship: bool) -> str:
    """Render a validated ``task_ref`` into the Claude Code CLI prompt.

    ``"PT38"`` becomes ``"execute PT38"``, with ``and use /ship when complete``
    appended when ``auto_ship`` is set so the session routes into the
    telos-review Stage 4 + ship skill flow. ``task_ref`` is assumed to have
    passed :class:`ClaudeSessionRequest` validation already.
    """
    base = f"execute {task_ref}"
    if auto_ship:
        return f"{base} and use /ship when complete"
    return base


async def run_claude_session(
    task_ref: str,
    target_dir: str,
    auto_ship: bool = True,
    timeout: int = _RUN_SYNC_CAP_SECONDS,
) -> Dict[str, Any]:
    """Run a Claude Code session bounded-synchronously.

    Spawns the CLI via ``start_background_session`` (so it inherits the
    JIT MCP/skills bootstrap and masked token injection), waits up to
    ``timeout`` seconds, and returns one of:

    - **Completed** — final output in the same turn, session cleaned up.
    - **Waiting for input** — ``waiting_for_input=True``, ``job_id`` set;
      reply via ``reply_claude_session(job_id, reply)``.
    - **Cap exceeded** — ``job_status='running'``, ``job_id`` set;
      continue via ``poll_claude_session(job_id)`` /
      ``reply_claude_session(job_id, ...)``.

    Like :func:`start_claude_session`, the prompt is always synthesized from
    ``task_ref``. Raw prompts are not accepted — see EX35.

    Args:
        task_ref: Telos task / exploration ref code (must match
            ``^(PT|EX)\\d+$``). Rendered into ``execute <ref>`` for the CLI.
        target_dir: Working directory for the Claude Code session.
        auto_ship: Append ``and use /ship when complete`` to route the
            session into the ship-it skill flow on success.
        timeout: Seconds to block before yielding a ``job_id``. Capped
            at ``_RUN_SYNC_CAP_SECONDS`` to respect MCP turn budgets.

    Returns:
        On invalid ``task_ref``: ``{status: 'error', message: <reason>}``
        (Pydantic ``ValidationError`` is caught so the agent loop survives).
        Otherwise a dict with ``status``, ``job_id``, ``job_status``,
        ``output``, ``waiting_for_input``, ``pending_question``,
        ``session_id``, ``return_code``, ``stderr``, and ``completed`` (bool).
    """
    try:
        request = ClaudeSessionRequest(task_ref=task_ref, target_dir=target_dir)
    except ValidationError as e:
        return {"status": "error", "message": str(e)}

    prompt = _synthesize_prompt(request.task_ref, auto_ship)

    # Clamp timeout to the hard cap so callers can't block indefinitely.
    timeout = max(1, min(timeout, _RUN_SYNC_CAP_SECONDS))

    try:
        client = ClaudeCodeClient()
        session = await client.start_background_session(
            working_dir=request.target_dir,
            prompt=prompt,
        )
    except Exception as e:
        logger.error("run_claude_session failed to start: %s", e)
        return {"status": "error", "message": str(e)}

    _SESSIONS[session.job_id] = session
    _CURSORS[session.job_id] = 0

    # Wait for a terminal/paused state up to the cap.
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if session.status in {"complete", "error", "waiting_for_input"}:
            break
        await asyncio.sleep(_RUN_SYNC_POLL_INTERVAL)

    # Drain what we have so far.
    cursor = _CURSORS.get(session.job_id, 0)
    new_text = "".join(session.output[cursor:])
    _CURSORS[session.job_id] = len(session.output)
    snap = _snapshot(session, new_text)

    if session.status in {"complete", "error"}:
        # Terminal — drop from the registry.
        _SESSIONS.pop(session.job_id, None)
        _CURSORS.pop(session.job_id, None)
        snap["completed"] = True
        snap["message"] = (
            "Claude Code session finished within the cap."
            if session.status == "complete"
            else "Claude Code session errored within the cap."
        )
    else:
        snap["completed"] = False
        snap["message"] = (
            "Cap or prompt reached — continue with poll_claude_session(job_id) "
            "or reply_claude_session(job_id, reply). job_id is kept alive."
        )
    return snap


_WAIT_POLL_INTERVAL = 5  # seconds between internal polls
_WAIT_MAX_TIMEOUT = 600  # hard cap: 10 minutes


async def wait_claude_session(
    job_id: str,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """Block until a background Claude Code session leaves the running state.

    Polls internally every 5 seconds so Scout doesn't have to implement its
    own polling loop. Returns as soon as ``job_status`` becomes ``complete``,
    ``error``, or ``waiting_for_input`` — or when the timeout is reached.

    The timeout is capped at 600 seconds (10 minutes) regardless of the
    value passed in, so Scout's MCP turn cannot hang indefinitely.

    Args:
        job_id: The id returned by ``start_claude_session``.
        timeout_seconds: Maximum time to wait in seconds (capped at 600).

    Returns:
        Same dict as ``poll_claude_session``, plus ``timed_out: bool``.
    """
    session = _SESSIONS.get(job_id)
    if session is None:
        return {"status": "error", "message": f"Unknown job_id: {job_id}"}

    effective_timeout = min(timeout_seconds, _WAIT_MAX_TIMEOUT)
    deadline = time.monotonic() + effective_timeout

    while session.status == "running":
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(_WAIT_POLL_INTERVAL, remaining))

    timed_out = session.status == "running"

    cursor = _CURSORS.get(job_id, 0)
    chunks = session.output[cursor:]
    _CURSORS[job_id] = len(session.output)
    snap = _snapshot(session, "".join(chunks))
    snap["timed_out"] = timed_out
    if timed_out:
        snap["message"] = (
            f"Session still running after {effective_timeout}s — "
            "call wait_claude_session again or poll_claude_session to continue"
        )
    return snap


CLAUDE_SESSION_TOOLS = [
    FunctionTool(run_claude_session),
    FunctionTool(start_claude_session),
    FunctionTool(poll_claude_session),
    FunctionTool(reply_claude_session),
    FunctionTool(wait_claude_session),
]
