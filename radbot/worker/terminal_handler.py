"""Shared terminal PTY handler for both the main app and worker.

Contains the core PTY management logic: session tracking, binary WebSocket
protocol, scrollback buffer, PTY reader/broadcaster. Used by:
- ``radbot/web/api/terminal.py`` (main app, local mode)
- ``radbot/worker/__main__.py`` (Nomad worker, remote mode)
"""

import asyncio
import fcntl
import logging
import os
import pty
import select
import signal
import struct
import termios
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Binary WebSocket protocol constants
MSG_DATA = 0x01  # terminal I/O data
MSG_RESIZE = 0x02  # client→server resize (uint16 cols + uint16 rows)
MSG_CLOSED = 0x03  # server→client session closed (int32 exit code)
MSG_REPLAY_END = 0x04  # marks end of scrollback replay

# Configuration
MAX_CONCURRENT_SESSIONS = 3
PTY_READ_SIZE = 65536  # 64KB
COALESCE_SECS = 0.002  # 2ms output batching
SCROLLBACK_BUFFER_SIZE = 128 * 1024  # 128KB

# Dedicated thread pool for PTY reads
_pty_executor = ThreadPoolExecutor(
    max_workers=MAX_CONCURRENT_SESSIONS, thread_name_prefix="pty-reader"
)


class TerminalSession:
    """Tracks a single PTY-backed terminal session.

    Supports multiple simultaneous WebSocket clients. A single background
    PTY reader task broadcasts output to all connected sockets.
    """

    __slots__ = (
        "terminal_id",
        "workspace_id",
        "workspace",
        "pid",
        "fd",
        "created_at",
        "closed",
        "_scrollback",
        "_clients",
        "_reader_task",
    )

    def __init__(
        self,
        terminal_id: str,
        workspace_id: str,
        workspace: Dict[str, Any],
        pid: int,
        fd: int,
    ):
        self.terminal_id = terminal_id
        self.workspace_id = workspace_id
        self.workspace = workspace
        self.pid = pid
        self.fd = fd
        self.created_at = __import__("time").time()
        self.closed = False
        self._scrollback = bytearray()
        self._clients: list = []
        self._reader_task: Optional[asyncio.Task] = None

    def append_output(self, data: bytes) -> None:
        """Append PTY output to the scrollback buffer (ring buffer)."""
        self._scrollback.extend(data)
        if len(self._scrollback) > SCROLLBACK_BUFFER_SIZE:
            excess = len(self._scrollback) - SCROLLBACK_BUFFER_SIZE
            del self._scrollback[:excess]

    def get_scrollback(self) -> bytes:
        """Return the scrollback buffer contents for replay on reconnect."""
        return bytes(self._scrollback)

    def add_client(self, ws) -> None:
        self._clients.append(ws)

    def remove_client(self, ws) -> None:
        try:
            self._clients.remove(ws)
        except ValueError:
            pass

    async def broadcast(self, data: bytes) -> None:
        """Send raw bytes to all connected clients, removing dead ones."""
        frame = bytes([MSG_DATA]) + data
        dead = []
        for ws in self._clients:
            try:
                await ws.send_bytes(frame)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove_client(ws)


class TerminalManager:
    """Manages PTY sessions for Claude Code terminals.

    Not a singleton — each context (main app, worker) creates its own instance.
    """

    def __init__(self, max_sessions: int = MAX_CONCURRENT_SESSIONS) -> None:
        self._sessions: Dict[str, TerminalSession] = {}
        self._max_sessions = max_sessions

    def create_session(
        self,
        workspace_id: str,
        resume_session_id: Optional[str] = None,
    ) -> TerminalSession:
        """Spawn ``claude`` in a PTY inside the given workspace directory."""
        if len(self._sessions) >= self._max_sessions:
            raise RuntimeError(
                f"Maximum concurrent terminal sessions ({self._max_sessions}) reached"
            )

        # Look up workspace
        from radbot.tools.claude_code.db import list_active_workspaces

        workspaces = list_active_workspaces()
        ws = next(
            (w for w in workspaces if str(w["workspace_id"]) == workspace_id),
            None,
        )
        if ws is None:
            raise ValueError(f"Workspace {workspace_id} not found")

        local_path = ws["local_path"]
        if not os.path.isdir(local_path):
            self._recover_workspace_dir(ws, local_path)

        env = self._build_env(local_path)
        cmd = self._build_command(resume_session_id)

        # Fork PTY
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(local_path)
            os.execvpe(cmd[0], cmd, env)
            os._exit(1)

        # Parent — set initial terminal size
        try:
            winsize = struct.pack("HHHH", 30, 120, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

        terminal_id = str(uuid.uuid4())
        session = TerminalSession(
            terminal_id=terminal_id,
            workspace_id=workspace_id,
            workspace=ws,
            pid=pid,
            fd=fd,
        )
        self._sessions[terminal_id] = session
        logger.info(
            "Terminal session %s created: pid=%d, workspace=%s/%s",
            terminal_id,
            pid,
            ws.get("owner"),
            ws.get("repo"),
        )
        return session

    def get_session(self, terminal_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(terminal_id)

    def list_sessions(self) -> List[Dict[str, Any]]:
        result = []
        for s in self._sessions.values():
            result.append(
                {
                    "terminal_id": s.terminal_id,
                    "workspace_id": s.workspace_id,
                    "owner": s.workspace.get("owner"),
                    "repo": s.workspace.get("repo"),
                    "branch": s.workspace.get("branch"),
                    "pid": s.pid,
                    "closed": s.closed,
                }
            )
        return result

    def resize_terminal(self, terminal_id: str, cols: int, rows: int) -> None:
        session = self._sessions.get(terminal_id)
        if session and not session.closed:
            try:
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(session.fd, termios.TIOCSWINSZ, winsize)
            except Exception as e:
                logger.debug("resize_terminal failed: %s", e)

    def kill_session(self, terminal_id: str) -> bool:
        session = self._sessions.pop(terminal_id, None)
        if session is None:
            return False
        self._cleanup_session(session)
        return True

    def kill_all(self) -> None:
        for session in list(self._sessions.values()):
            self._cleanup_session(session)
        self._sessions.clear()
        logger.info("All terminal sessions killed")

    def _cleanup_session(self, session: TerminalSession) -> None:
        session.closed = True
        try:
            os.kill(session.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.debug("Error sending SIGTERM to pid %d: %s", session.pid, e)
        try:
            os.close(session.fd)
        except Exception:
            pass
        try:
            os.waitpid(session.pid, os.WNOHANG)
        except Exception:
            pass
        self._save_claude_session_id(session)
        logger.info(
            "Terminal session %s cleaned up (pid=%d)", session.terminal_id, session.pid
        )

    def _save_claude_session_id(self, session: TerminalSession) -> None:
        """Find and persist the Claude Code session ID from its state files."""
        try:
            import glob
            import json as _json
            from pathlib import Path

            home = Path.home()
            index_files = glob.glob(
                str(home / ".claude" / "projects" / "*" / "sessions-index.json")
            )
            if not index_files:
                return

            latest_idx = max(index_files, key=os.path.getmtime)
            with open(latest_idx) as f:
                sessions = _json.load(f)

            if not sessions:
                return

            latest = max(sessions, key=lambda s: s.get("lastUpdated", 0))
            claude_session_id = latest.get("sessionId")
            if not claude_session_id:
                return

            from radbot.tools.claude_code.db import update_session_id

            ws = session.workspace
            if ws.get("owner") and ws.get("repo"):
                update_session_id(
                    owner=ws["owner"],
                    repo=ws["repo"],
                    branch=ws.get("branch", "main"),
                    session_id=claude_session_id,
                )
                logger.info(
                    "Saved Claude session ID %s for workspace %s/%s",
                    claude_session_id[:12],
                    ws["owner"],
                    ws["repo"],
                )
        except Exception as e:
            logger.debug("Failed to capture Claude session ID: %s", e)

    def reap_dead(self) -> None:
        """Check for exited child processes and mark sessions as closed."""
        for session in list(self._sessions.values()):
            if session.closed:
                continue
            try:
                pid, status = os.waitpid(session.pid, os.WNOHANG)
                if pid != 0:
                    session.closed = True
                    logger.info(
                        "Terminal session %s child exited (status=%d)",
                        session.terminal_id,
                        status,
                    )
            except ChildProcessError:
                session.closed = True
            except Exception:
                pass

    @staticmethod
    def _recover_workspace_dir(ws: Dict[str, Any], local_path: str) -> str:
        """Re-create workspace directory if lost (container restart)."""
        if ws.get("owner") == "_scratch":
            os.makedirs(local_path, exist_ok=True)
            logger.info("Recreated scratch workspace directory: %s", local_path)
            return local_path

        try:
            from radbot.tools.github.github_app_client import get_github_client

            client = get_github_client()
            if not client:
                raise ValueError("GitHub App not configured — cannot clone workspace")

            workspace_dir = os.path.dirname(local_path)
            os.makedirs(workspace_dir, exist_ok=True)
            result = client.clone_repo(
                ws["owner"], ws["repo"], workspace_dir, ws.get("branch", "main")
            )
            if result.get("status") != "success":
                raise ValueError(
                    f"Failed to re-clone {ws['owner']}/{ws['repo']}: {result.get('message')}"
                )
            new_path = result.get("local_path", local_path)
            logger.info(
                "Re-cloned workspace %s/%s to %s", ws["owner"], ws["repo"], new_path
            )
            return new_path
        except Exception as e:
            raise ValueError(
                f"Workspace directory missing and re-clone failed: {local_path} — {e}"
            )

    @staticmethod
    def _build_env(local_path: str) -> Dict[str, str]:
        """Build environment dict with auth tokens for Claude Code."""
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        token_injected = False

        # 1. Resolve auth token (API key or OAuth)
        try:
            from radbot.tools.claude_code.claude_code_client import (
                _get_auth_token,
                _write_auth_token_files,
            )

            token, kind = _get_auth_token()
            if token:
                if kind == "api_key":
                    env["ANTHROPIC_API_KEY"] = token
                else:
                    env["CLAUDE_CODE_OAUTH_TOKEN"] = token
                    env.pop("ANTHROPIC_API_KEY", None)
                    _write_auth_token_files(token)
                token_injected = True
                logger.info("Terminal: injected Claude Code %s token", kind)
        except Exception as e:
            logger.warning("Terminal: failed to get auth token: %s", e)

        # 2. Fallback to credential store
        if not token_injected:
            try:
                from radbot.credentials.store import get_credential_store

                store = get_credential_store()
                if store.available:
                    api_key = store.get("anthropic_api_key")
                    if api_key:
                        env["ANTHROPIC_API_KEY"] = api_key
                        token_injected = True
                        logger.info(
                            "Terminal: injected ANTHROPIC_API_KEY from credential store"
                        )
            except Exception as e:
                logger.warning("Terminal: failed to get Anthropic API key: %s", e)

        if not token_injected:
            logger.warning(
                "Terminal: no auth token found — Claude Code will prompt for login. "
                "Set 'claude_code_oauth_token' or 'anthropic_api_key' in credential store."
            )

        # Ensure onboarding is complete
        if token_injected:
            try:
                from radbot.tools.claude_code.claude_code_client import (
                    _ensure_onboarding_complete,
                )

                _ensure_onboarding_complete(workspace_dir=local_path)
            except Exception as e:
                logger.warning("Terminal: failed to set onboarding flag: %s", e)

        # Allow --dangerously-skip-permissions when running as root
        if os.getuid() == 0:
            env["IS_SANDBOX"] = "1"

        return env

    @staticmethod
    def _build_command(resume_session_id: Optional[str] = None) -> List[str]:
        """Build the claude CLI command."""
        cmd = ["claude"]
        if os.getuid() == 0:
            cmd.append("--dangerously-skip-permissions")
        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])
        return cmd


# ------------------------------------------------------------------
# PTY reader and WebSocket handler (protocol-level, framework-agnostic)
# ------------------------------------------------------------------


def pty_read_coalesced(fd: int) -> bytes:
    """Blocking read from PTY fd with output coalescing."""
    data = os.read(fd, PTY_READ_SIZE)
    if not data:
        return data
    while True:
        r, _, _ = select.select([fd], [], [], COALESCE_SECS)
        if not r:
            break
        more = os.read(fd, PTY_READ_SIZE)
        if not more:
            break
        data += more
    return data


async def ensure_pty_reader(session: TerminalSession) -> None:
    """Start the shared PTY reader task if not already running.

    One reader per session reads from the PTY fd and broadcasts to
    all connected WebSocket clients. Runs until the PTY closes.
    """
    if session._reader_task is not None and not session._reader_task.done():
        return

    loop = asyncio.get_event_loop()

    async def _reader():
        while not session.closed:
            try:
                data = await loop.run_in_executor(
                    _pty_executor, pty_read_coalesced, session.fd
                )
                if not data:
                    break
                session.append_output(data)
                await session.broadcast(data)
            except OSError:
                break
            except Exception as e:
                logger.debug("PTY reader error: %s", e)
                break

        # PTY closed — notify all clients
        exit_code = -1
        try:
            _, status = os.waitpid(session.pid, os.WNOHANG)
            if os.WIFEXITED(status):
                exit_code = os.WEXITSTATUS(status)
        except Exception:
            pass
        session.closed = True
        close_frame = bytes([MSG_CLOSED]) + struct.pack(">i", exit_code)
        for ws in list(session._clients):
            try:
                await ws.send_bytes(close_frame)
            except Exception:
                pass

    session._reader_task = asyncio.create_task(_reader())


async def handle_terminal_websocket(
    websocket,
    session: TerminalSession,
    manager: TerminalManager,
) -> None:
    """Handle a single WebSocket client connected to a terminal session.

    Works with both FastAPI and Starlette WebSocket objects (same API).
    Caller must have already called ``websocket.accept()``.
    """
    session.add_client(websocket)
    client_count = len(session._clients)
    logger.info(
        "Terminal WS connected: %s (%d client%s)",
        session.terminal_id,
        client_count,
        "s" if client_count > 1 else "",
    )

    # Replay scrollback
    scrollback = session.get_scrollback()
    if scrollback:
        try:
            await websocket.send_bytes(bytes([MSG_DATA]) + scrollback)
            logger.info(
                "Terminal WS replayed %d bytes of scrollback for %s",
                len(scrollback),
                session.terminal_id,
            )
        except Exception as e:
            logger.debug("Failed to replay scrollback: %s", e)

    # Send replay-end marker so the frontend knows where history ends
    try:
        await websocket.send_bytes(bytes([MSG_REPLAY_END]))
    except Exception:
        pass

    # Start the shared PTY reader if this is the first client
    await ensure_pty_reader(session)

    # Read input from this client → write to PTY
    try:
        while not session.closed:
            try:
                msg = await websocket.receive()

                if "bytes" in msg and msg["bytes"]:
                    raw = msg["bytes"]
                    if not raw:
                        continue
                    msg_type = raw[0]
                    if msg_type == MSG_DATA:
                        os.write(session.fd, raw[1:])
                    elif msg_type == MSG_RESIZE:
                        if len(raw) >= 5:
                            cols = int.from_bytes(raw[1:3], "big")
                            rows = int.from_bytes(raw[3:5], "big")
                            manager.resize_terminal(session.terminal_id, cols, rows)

                elif "text" in msg and msg["text"]:
                    import json

                    data = json.loads(msg["text"])
                    if data.get("type") == "input":
                        os.write(session.fd, data.get("data", "").encode("utf-8"))
                    elif data.get("type") == "resize":
                        cols = data.get("cols", 80)
                        rows = data.get("rows", 24)
                        manager.resize_terminal(session.terminal_id, cols, rows)

            except Exception:
                break
    finally:
        session.remove_client(websocket)
        logger.info(
            "Terminal WS disconnected: %s (%d client%s remaining)",
            session.terminal_id,
            len(session._clients),
            "s" if len(session._clients) != 1 else "",
        )
