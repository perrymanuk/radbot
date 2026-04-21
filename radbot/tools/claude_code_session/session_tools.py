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

import logging
from typing import Any, Dict, Optional

from google.adk.tools import FunctionTool

from radbot.tools.claude_code.claude_code_client import (
    BackgroundSession,
    ClaudeCodeClient,
)

logger = logging.getLogger(__name__)

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
    prompt: str,
    target_dir: str,
    resume_session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Kick off a Claude Code CLI session in the background and return a job_id.

    The session runs with ``--dangerously-skip-permissions`` so routine file /
    bash operations don't hang on approval. Returns immediately — Scout must
    ``poll_claude_session`` to check progress and collect output.

    Args:
        prompt: The plan / instructions for Claude Code to execute.
        target_dir: Working directory the CLI runs inside.
        resume_session_id: Optional CLI ``session_id`` to resume an earlier run.

    Returns:
        ``{status, job_id, message}`` — job_id is used for poll/reply.
    """
    try:
        client = ClaudeCodeClient()
        session = await client.start_background_session(
            working_dir=target_dir,
            prompt=prompt,
            session_id=resume_session_id,
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


CLAUDE_SESSION_TOOLS = [
    FunctionTool(start_claude_session),
    FunctionTool(poll_claude_session),
    FunctionTool(reply_claude_session),
]
