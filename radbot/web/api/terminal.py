"""Interactive Claude Code terminal via PTY + WebSocket.

Spawns the ``claude`` CLI in a PTY, bridges I/O over a WebSocket to an
xterm.js frontend. Manages concurrent terminal sessions with lifecycle
tracking and cleanup.
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

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/terminal", tags=["terminal"])

_MAX_CONCURRENT_SESSIONS = 3

# Binary WebSocket protocol constants
_MSG_DATA = 0x01  # terminal I/O data
_MSG_RESIZE = 0x02  # client→server resize (uint16 cols + uint16 rows)
_MSG_CLOSED = 0x03  # server→client session closed (int32 exit code)

# Dedicated thread pool for PTY reads (avoids contention with default executor)
_pty_executor = ThreadPoolExecutor(
    max_workers=_MAX_CONCURRENT_SESSIONS, thread_name_prefix="pty-reader"
)

# PTY read buffer size — 64KB to minimise syscalls for large screen redraws
_PTY_READ_SIZE = 65536

# Output coalescing window — drain additional pending bytes for up to this long
# before sending a WebSocket frame.  Imperceptible to humans but batches rapid
# output (e.g. full-screen ANSI redraws) into fewer frames.
_COALESCE_SECS = 0.002  # 2 ms


# ------------------------------------------------------------------
# Terminal session data
# ------------------------------------------------------------------
# Max bytes to keep in the scrollback replay buffer per session
_SCROLLBACK_BUFFER_SIZE = 128 * 1024  # 128 KB


class _TerminalSession:
    """Tracks a single PTY-backed terminal session."""

    __slots__ = (
        "terminal_id",
        "workspace_id",
        "workspace",
        "pid",
        "fd",
        "created_at",
        "closed",
        "_scrollback",
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

    def append_output(self, data: bytes) -> None:
        """Append PTY output to the scrollback buffer (ring buffer)."""
        self._scrollback.extend(data)
        if len(self._scrollback) > _SCROLLBACK_BUFFER_SIZE:
            excess = len(self._scrollback) - _SCROLLBACK_BUFFER_SIZE
            del self._scrollback[:excess]

    def get_scrollback(self) -> bytes:
        """Return the scrollback buffer contents for replay on reconnect."""
        return bytes(self._scrollback)


# ------------------------------------------------------------------
# TerminalManager singleton
# ------------------------------------------------------------------
class TerminalManager:
    """Manages PTY sessions for Claude Code terminals."""

    _instance: Optional["TerminalManager"] = None

    def __init__(self) -> None:
        self._sessions: Dict[str, _TerminalSession] = {}

    @classmethod
    def get_instance(cls) -> "TerminalManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- create session --

    def create_session(
        self,
        workspace_id: str,
        resume_session_id: Optional[str] = None,
    ) -> _TerminalSession:
        """Spawn ``claude`` in a PTY inside the given workspace directory."""
        if len(self._sessions) >= _MAX_CONCURRENT_SESSIONS:
            raise RuntimeError(
                f"Maximum concurrent terminal sessions ({_MAX_CONCURRENT_SESSIONS}) reached"
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
            raise ValueError(f"Workspace directory does not exist: {local_path}")

        # Build environment — inject auth tokens for Claude Code
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")
        token_injected = False

        # 1. Resolve auth token (API key or OAuth) from config/env
        try:
            from radbot.tools.claude_code.claude_code_client import (
                _get_auth_token,
                _write_auth_token_files,
            )

            token, kind = _get_auth_token()
            if token:
                # Always use ANTHROPIC_API_KEY for PTY sessions — the interactive
                # CLI ignores CLAUDE_CODE_OAUTH_TOKEN during onboarding, but
                # detects ANTHROPIC_API_KEY and auto-configures auth.
                env["ANTHROPIC_API_KEY"] = token
                _write_auth_token_files(token)
                token_injected = True
                logger.info("Terminal: injected Claude Code %s token as ANTHROPIC_API_KEY", kind)
        except Exception as e:
            logger.warning("Terminal: failed to get auth token: %s", e)

        # 2. Also try ANTHROPIC_API_KEY as fallback
        if not token_injected:
            try:
                from radbot.credentials.store import get_credential_store

                store = get_credential_store()
                if store.available:
                    api_key = store.get("anthropic_api_key")
                    if api_key:
                        env["ANTHROPIC_API_KEY"] = api_key
                        token_injected = True
                        logger.info("Terminal: injected ANTHROPIC_API_KEY from credential store")
            except Exception as e:
                logger.warning("Terminal: failed to get Anthropic API key: %s", e)

        if not token_injected:
            logger.warning(
                "Terminal: no auth token found — Claude Code will prompt for login. "
                "Set 'claude_code_oauth_token' or 'anthropic_api_key' in credential store."
            )

        # Build command
        cmd = ["claude"]
        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])

        # Fork PTY
        pid, fd = pty.fork()

        if pid == 0:
            # Child process
            os.chdir(local_path)
            os.execvpe(cmd[0], cmd, env)
            # execvpe never returns; if it somehow does, exit
            os._exit(1)

        # Parent process — set initial terminal size
        try:
            winsize = struct.pack("HHHH", 30, 120, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

        terminal_id = str(uuid.uuid4())
        session = _TerminalSession(
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

    # -- lookup --

    def get_session(self, terminal_id: str) -> Optional[_TerminalSession]:
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

    # -- resize --

    def resize_terminal(self, terminal_id: str, cols: int, rows: int) -> None:
        session = self._sessions.get(terminal_id)
        if session and not session.closed:
            try:
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(session.fd, termios.TIOCSWINSZ, winsize)
            except Exception as e:
                logger.debug("resize_terminal failed: %s", e)

    # -- kill --

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

    def _cleanup_session(self, session: _TerminalSession) -> None:
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
        # Reap the child to avoid zombie
        try:
            os.waitpid(session.pid, os.WNOHANG)
        except Exception:
            pass
        logger.info("Terminal session %s cleaned up (pid=%d)", session.terminal_id, session.pid)

    # -- reap dead children --

    def _reap_dead(self) -> None:
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


# ------------------------------------------------------------------
# REST endpoints
# ------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def terminal_page(request: Request):
    """Serve the terminal page (React SPA)."""
    dist_index = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static", "dist", "index.html"
    )
    if os.path.isfile(dist_index):
        with open(dist_index, "r") as f:
            html = f.read()
        html = html.replace('"/assets/', '"/static/dist/assets/')
        html = html.replace("'/assets/", "'/static/dist/assets/")
        return HTMLResponse(content=html)
    return HTMLResponse(
        content="<h1>RadBot Terminal</h1><p>React frontend not built.</p>",
        status_code=503,
    )


@router.get("/workspaces/")
async def list_workspaces():
    """List active Claude Code workspaces."""
    try:
        from radbot.tools.claude_code.db import list_active_workspaces

        workspaces = list_active_workspaces()
        # Serialize UUIDs and datetimes to strings
        for ws in workspaces:
            for k, v in ws.items():
                if hasattr(v, "isoformat"):
                    ws[k] = v.isoformat()
                elif hasattr(v, "hex"):  # UUID
                    ws[k] = str(v)
        return {"workspaces": workspaces}
    except Exception as e:
        logger.error("Error listing workspaces: %s", e, exc_info=True)
        raise HTTPException(500, f"Error listing workspaces: {e}")


@router.post("/sessions/")
async def create_terminal_session(request: Request):
    """Create a new interactive terminal session."""
    body = await request.json()
    workspace_id = body.get("workspace_id")
    resume_session_id = body.get("resume_session_id")

    if not workspace_id:
        raise HTTPException(400, "workspace_id is required")

    mgr = TerminalManager.get_instance()
    try:
        session = mgr.create_session(workspace_id, resume_session_id)
    except RuntimeError as e:
        raise HTTPException(429, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error("Error creating terminal session: %s", e, exc_info=True)
        raise HTTPException(500, f"Error creating terminal session: {e}")

    return {
        "terminal_id": session.terminal_id,
        "workspace_id": session.workspace_id,
        "owner": session.workspace.get("owner"),
        "repo": session.workspace.get("repo"),
        "branch": session.workspace.get("branch"),
        "pid": session.pid,
    }


@router.get("/sessions/")
async def list_terminal_sessions():
    """List active terminal sessions."""
    mgr = TerminalManager.get_instance()
    return {"sessions": mgr.list_sessions()}


@router.delete("/sessions/{terminal_id}")
async def kill_terminal_session(terminal_id: str):
    """Kill a terminal session."""
    mgr = TerminalManager.get_instance()
    if mgr.kill_session(terminal_id):
        return {"status": "success", "message": f"Session {terminal_id} killed"}
    raise HTTPException(404, f"Terminal session {terminal_id} not found")


@router.post("/clone/")
async def clone_repository_endpoint(request: Request):
    """Clone a GitHub repository into a workspace."""
    body = await request.json()
    owner = body.get("owner")
    repo = body.get("repo")
    branch = body.get("branch", "main")

    if not owner or not repo:
        raise HTTPException(400, "owner and repo are required")

    try:
        from radbot.tools.claude_code.claude_code_tools import clone_repository

        result = clone_repository(owner=owner, repo=repo, branch=branch)
        return result
    except Exception as e:
        logger.error("Error cloning repository: %s", e, exc_info=True)
        raise HTTPException(500, f"Error cloning repository: {e}")


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace_endpoint(workspace_id: str):
    """Delete (soft) a workspace."""
    try:
        from radbot.tools.claude_code.db import delete_workspace

        # Kill any active terminal sessions for this workspace
        mgr = TerminalManager.get_instance()
        for s in list(mgr._sessions.values()):
            if s.workspace_id == workspace_id:
                mgr.kill_session(s.terminal_id)

        success = delete_workspace(workspace_id)
        if not success:
            raise HTTPException(404, f"Workspace {workspace_id} not found")
        return {"status": "success", "message": f"Workspace {workspace_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting workspace: %s", e, exc_info=True)
        raise HTTPException(500, f"Error deleting workspace: {e}")


@router.put("/workspaces/{workspace_id}")
async def update_workspace_endpoint(workspace_id: str, request: Request):
    """Update workspace name and/or description."""
    body = await request.json()
    name = body.get("name")
    description = body.get("description")

    if name is None and description is None:
        raise HTTPException(400, "name or description is required")

    try:
        from radbot.tools.claude_code.db import update_workspace

        success = update_workspace(workspace_id, name=name, description=description)
        if not success:
            raise HTTPException(404, f"Workspace {workspace_id} not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating workspace: %s", e, exc_info=True)
        raise HTTPException(500, f"Error updating workspace: {e}")


@router.post("/workspaces/scratch/")
async def create_scratch_workspace_endpoint(request: Request):
    """Create a scratch workspace (no repo) for a fresh Claude session."""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    name = body.get("name")
    description = body.get("description")

    try:
        from radbot.tools.claude_code.db import create_scratch_workspace

        ws = create_scratch_workspace(name=name, description=description)
        # Serialize UUIDs/datetimes
        for k, v in ws.items():
            if hasattr(v, "isoformat"):
                ws[k] = v.isoformat()
            elif hasattr(v, "hex"):
                ws[k] = str(v)
        return {"status": "success", "workspace": ws}
    except Exception as e:
        logger.error("Error creating scratch workspace: %s", e, exc_info=True)
        raise HTTPException(500, f"Error creating scratch workspace: {e}")


@router.get("/status/")
async def terminal_status():
    """Check Claude Code CLI and token availability."""
    try:
        from radbot.tools.claude_code.claude_code_client import get_claude_code_status

        return get_claude_code_status()
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ------------------------------------------------------------------
# WebSocket handler
# ------------------------------------------------------------------
def register_terminal_websocket(app) -> None:
    """Register the terminal WebSocket endpoint on the FastAPI app."""

    @app.websocket("/ws/terminal/{terminal_id}")
    async def terminal_ws(websocket: WebSocket, terminal_id: str):
        mgr = TerminalManager.get_instance()
        session = mgr.get_session(terminal_id)

        if session is None or session.closed:
            await websocket.close(code=4004, reason="Terminal session not found")
            return

        await websocket.accept()
        logger.info("Terminal WS connected: %s", terminal_id)

        # Replay scrollback buffer so reconnecting clients see prior output
        scrollback = session.get_scrollback()
        if scrollback:
            try:
                await websocket.send_bytes(bytes([_MSG_DATA]) + scrollback)
                logger.info(
                    "Terminal WS replayed %d bytes of scrollback for %s",
                    len(scrollback),
                    terminal_id,
                )
            except Exception as e:
                logger.debug("Failed to replay scrollback: %s", e)

        loop = asyncio.get_event_loop()

        def _pty_read_coalesced(fd: int) -> bytes:
            """Blocking read from PTY fd with output coalescing.

            Reads available data, then drains any additional bytes that
            arrive within a short window so that rapid output (e.g. a
            full-screen ANSI redraw) is batched into a single frame.
            """
            data = os.read(fd, _PTY_READ_SIZE)
            if not data:
                return data
            while True:
                r, _, _ = select.select([fd], [], [], _COALESCE_SECS)
                if not r:
                    break
                more = os.read(fd, _PTY_READ_SIZE)
                if not more:
                    break
                data += more
            return data

        async def pty_reader():
            """Read from PTY fd and forward to WebSocket as binary frames."""
            while not session.closed:
                try:
                    data = await loop.run_in_executor(
                        _pty_executor, _pty_read_coalesced, session.fd
                    )
                    if not data:
                        break
                    # Record in scrollback for reconnect replay
                    session.append_output(data)
                    # Binary frame: 0x01 prefix + raw PTY bytes
                    await websocket.send_bytes(bytes([_MSG_DATA]) + data)
                except OSError:
                    # PTY closed
                    break
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.debug("PTY reader error: %s", e)
                    break

            # Notify client that the terminal has closed
            exit_code = -1
            try:
                _, status = os.waitpid(session.pid, os.WNOHANG)
                if os.WIFEXITED(status):
                    exit_code = os.WEXITSTATUS(status)
            except Exception:
                pass
            session.closed = True
            try:
                # Binary frame: 0x03 prefix + int32 BE exit code
                await websocket.send_bytes(
                    bytes([_MSG_CLOSED]) + struct.pack(">i", exit_code)
                )
            except Exception:
                pass

        async def ws_reader():
            """Read from WebSocket and forward to PTY."""
            while not session.closed:
                try:
                    msg = await websocket.receive()

                    # Binary frame (new protocol)
                    if "bytes" in msg and msg["bytes"]:
                        raw = msg["bytes"]
                        if not raw:
                            continue
                        msg_type = raw[0]
                        if msg_type == _MSG_DATA:
                            os.write(session.fd, raw[1:])
                        elif msg_type == _MSG_RESIZE:
                            if len(raw) >= 5:
                                cols = int.from_bytes(raw[1:3], "big")
                                rows = int.from_bytes(raw[3:5], "big")
                                mgr.resize_terminal(terminal_id, cols, rows)

                    # Text frame (legacy JSON fallback)
                    elif "text" in msg and msg["text"]:
                        import json

                        data = json.loads(msg["text"])
                        if data.get("type") == "input":
                            os.write(session.fd, data.get("data", "").encode("utf-8"))
                        elif data.get("type") == "resize":
                            cols = data.get("cols", 80)
                            rows = data.get("rows", 24)
                            mgr.resize_terminal(terminal_id, cols, rows)

                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.debug("WS reader error: %s", e)
                    break

        # Run both tasks concurrently — when either finishes, cancel the other
        reader_task = asyncio.create_task(pty_reader())
        writer_task = asyncio.create_task(ws_reader())

        try:
            done, pending = await asyncio.wait(
                {reader_task, writer_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
        except Exception:
            reader_task.cancel()
            writer_task.cancel()
        finally:
            logger.info("Terminal WS disconnected: %s", terminal_id)
