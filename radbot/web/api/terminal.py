"""Interactive Claude Code terminal via PTY + WebSocket.

Spawns the ``claude`` CLI in a PTY, bridges I/O over a WebSocket to an
xterm.js frontend. Supports two modes:

- **local**: PTY runs in the main app container (default)
- **remote**: PTY runs in a Nomad worker, main app proxies the WebSocket

The core PTY logic lives in ``radbot.worker.terminal_handler``.
"""

import asyncio
import logging
import os
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from radbot.worker.terminal_handler import (
    MSG_CLOSED,
    TerminalManager,
    handle_terminal_websocket,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/terminal", tags=["terminal"])

# Singleton TerminalManager for local mode
_local_manager: Optional[TerminalManager] = None


def _get_local_manager() -> TerminalManager:
    """Get or create the local TerminalManager singleton."""
    global _local_manager
    if _local_manager is None:
        _local_manager = TerminalManager()
    return _local_manager


def _is_remote_mode() -> bool:
    """Check if session_mode is 'remote' in config."""
    try:
        from radbot.config.config_loader import config_loader

        agent_config = config_loader.config.get("agent", {})
        return agent_config.get("session_mode") == "remote"
    except Exception:
        return False


# ------------------------------------------------------------------
# Mapping of terminal_id → worker_url for remote-mode proxy routing
# ------------------------------------------------------------------
_terminal_worker_map: Dict[str, str] = {}


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
        for ws in workspaces:
            for k, v in ws.items():
                if hasattr(v, "isoformat"):
                    ws[k] = v.isoformat()
                elif hasattr(v, "hex"):
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

    if _is_remote_mode():
        return await _create_remote_session(workspace_id, resume_session_id)

    return await _create_local_session(workspace_id, resume_session_id)


async def _create_local_session(
    workspace_id: str, resume_session_id: Optional[str] = None
) -> dict:
    """Create a terminal session in the local process.

    Runs the sync PTY creation in a thread to avoid blocking the event loop
    (the DB query + pty.fork are blocking operations).
    """
    mgr = _get_local_manager()
    try:
        session = await asyncio.get_event_loop().run_in_executor(
            None, mgr.create_session, workspace_id, resume_session_id
        )
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


async def _create_remote_session(
    workspace_id: str, resume_session_id: Optional[str] = None
) -> dict:
    """Create a terminal session on a remote Nomad worker."""
    try:
        from radbot.web.api.terminal_proxy import get_workspace_proxy

        proxy = get_workspace_proxy(workspace_id)
        worker_url = await proxy.ensure_worker()
        if not worker_url:
            logger.warning(
                "No worker available for workspace %s — falling back to local",
                workspace_id,
            )
            return _create_local_session(workspace_id, resume_session_id)

        # Forward session creation to the worker
        payload = {"workspace_id": workspace_id}
        if resume_session_id:
            payload["resume_session_id"] = resume_session_id

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{worker_url}/terminal/sessions/",
                json=payload,
            )
            if resp.status_code != 200:
                logger.error(
                    "Worker session creation failed (%d): %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return _create_local_session(workspace_id, resume_session_id)

            result = resp.json()
            terminal_id = result.get("terminal_id")
            if terminal_id:
                _terminal_worker_map[terminal_id] = worker_url
            return result

    except Exception as e:
        logger.error("Remote session creation failed: %s", e, exc_info=True)
        return _create_local_session(workspace_id, resume_session_id)


@router.get("/sessions/")
async def list_terminal_sessions():
    """List active terminal sessions."""
    if _is_remote_mode():
        # Include both local and remote sessions
        sessions = _get_local_manager().list_sessions()
        remote = await _list_remote_sessions()
        sessions.extend(remote)
        return {"sessions": sessions}

    mgr = _get_local_manager()
    return {"sessions": mgr.list_sessions()}


async def _list_remote_sessions() -> list:
    """Aggregate terminal sessions from active workspace workers."""
    try:
        from radbot.worker.db import list_active_workspace_workers

        workers = list_active_workspace_workers()
        sessions = []
        async with httpx.AsyncClient(timeout=10) as client:
            for w in workers:
                url = w.get("worker_url")
                if not url:
                    continue
                try:
                    resp = await client.get(f"{url}/terminal/sessions/")
                    if resp.status_code == 200:
                        data = resp.json()
                        for s in data.get("sessions", []):
                            s["remote"] = True
                            s["worker_url"] = url
                            sessions.append(s)
                except Exception:
                    pass
        return sessions
    except Exception as e:
        logger.debug("Failed to list remote sessions: %s", e)
        return []


@router.delete("/sessions/{terminal_id}")
async def kill_terminal_session(terminal_id: str):
    """Kill a terminal session."""
    # Check remote first
    worker_url = _terminal_worker_map.pop(terminal_id, None)
    if worker_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.delete(
                    f"{worker_url}/terminal/sessions/{terminal_id}"
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            logger.warning("Failed to kill remote session: %s", e)

    # Fall back to local
    mgr = _get_local_manager()
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
    name = body.get("name")
    description = body.get("description")

    if not owner or not repo:
        raise HTTPException(400, "owner and repo are required")

    try:
        from radbot.tools.github.github_app_client import get_github_client

        client = get_github_client()
        if not client:
            raise HTTPException(500, "GitHub App not configured")

        workspace_dir = os.path.join(
            os.environ.get("WORKSPACE_DIR", "/app/workspaces"),
        )
        os.makedirs(workspace_dir, exist_ok=True)
        result = client.clone_repo(owner, repo, workspace_dir, branch)

        if result.get("status") != "success":
            raise HTTPException(500, result.get("message", "Clone failed"))

        local_path = result["local_path"]

        from radbot.tools.claude_code.db import create_workspace

        ws = create_workspace(
            owner=owner,
            repo=repo,
            branch=branch,
            local_path=local_path,
            name=name,
            description=description,
        )

        return {
            "status": "success",
            "workspace_id": str(ws.get("workspace_id", "")),
            "work_folder": local_path,
            "action": result.get("action", "clone"),
            "message": f"Repository {owner}/{repo} ({branch}) available at {local_path}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error cloning repository: %s", e, exc_info=True)
        raise HTTPException(500, f"Error cloning repository: {e}")


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace_endpoint(workspace_id: str):
    """Delete (soft) a workspace and stop its worker if any."""
    try:
        from radbot.tools.claude_code.db import delete_workspace

        # Kill any active local terminal sessions for this workspace
        mgr = _get_local_manager()
        for s in list(mgr._sessions.values()):
            if s.workspace_id == workspace_id:
                mgr.kill_session(s.terminal_id)

        # Stop the remote worker if running
        if _is_remote_mode():
            try:
                from radbot.web.api.terminal_proxy import get_workspace_proxy

                proxy = get_workspace_proxy(workspace_id)
                await proxy.stop_worker()
            except Exception as e:
                logger.warning("Failed to stop workspace worker: %s", e)

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
    body = (
        await request.json()
        if request.headers.get("content-type") == "application/json"
        else {}
    )
    name = body.get("name")
    description = body.get("description")

    try:
        from radbot.tools.claude_code.db import create_scratch_workspace

        ws = create_scratch_workspace(name=name, description=description)
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
        # Check if this terminal is on a remote worker
        worker_url = _terminal_worker_map.get(terminal_id)
        if worker_url:
            await _proxy_terminal_ws(websocket, terminal_id, worker_url)
            return

        # Local mode — handle PTY directly
        mgr = _get_local_manager()
        session = mgr.get_session(terminal_id)

        if session is None or session.closed:
            await websocket.close(code=4004, reason="Terminal session not found")
            return

        await websocket.accept()
        await handle_terminal_websocket(websocket, session, mgr)


async def _proxy_terminal_ws(
    browser_ws: WebSocket, terminal_id: str, worker_url: str
) -> None:
    """Bidirectional binary WebSocket proxy between browser and worker.

    Forwards all binary frames unchanged. The worker handles the PTY,
    scrollback, and broadcast logic.
    """
    import websockets

    ws_url = worker_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/ws/terminal/{terminal_id}"

    await browser_ws.accept()
    logger.info("Terminal proxy connecting to worker: %s", ws_url)

    try:
        async with websockets.connect(ws_url) as worker_ws:
            async def browser_to_worker():
                try:
                    while True:
                        msg = await browser_ws.receive()
                        if "bytes" in msg and msg["bytes"]:
                            await worker_ws.send(msg["bytes"])
                        elif "text" in msg and msg["text"]:
                            await worker_ws.send(msg["text"])
                except (WebSocketDisconnect, Exception):
                    pass

            async def worker_to_browser():
                try:
                    async for data in worker_ws:
                        if isinstance(data, bytes):
                            await browser_ws.send_bytes(data)
                        else:
                            await browser_ws.send_text(data)
                except Exception:
                    pass

            # Run both directions concurrently
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(browser_to_worker()),
                    asyncio.create_task(worker_to_browser()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
            # Cancel whichever is still running
            for task in pending:
                task.cancel()

    except Exception as e:
        logger.warning("Terminal proxy error for %s: %s", terminal_id, e)
        # Try to notify the browser that the session closed
        try:
            import struct

            close_frame = bytes([MSG_CLOSED]) + struct.pack(">i", -1)
            await browser_ws.send_bytes(close_frame)
        except Exception:
            pass

    logger.info("Terminal proxy disconnected: %s", terminal_id)
