"""Scout's native access to Claude Code via the official ``claude-agent-sdk``.

Exposes three FunctionTools (start / poll / reply) that implement an async
kickoff + poll pattern with human-in-the-loop support. Scout fires
``start_claude_session`` with a finalized plan, polls for progress, and
answers any ``AskUserQuestion`` pauses via ``reply_claude_session``. See
``explorations: EX26`` and ``project_tasks: PT77`` in Telos.
"""

from .session_tools import CLAUDE_SESSION_TOOLS

__all__ = ["CLAUDE_SESSION_TOOLS"]
