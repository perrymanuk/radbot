"""Minimal PTY terminal server for RadBot workspace workers.

Runs Claude Code CLI in a PTY and serves the terminal over WebSocket.
No ADK, no agent stack, no A2A — just a PTY server with health checks.

Usage:
    python -m radbot.worker --workspace-id <UUID> [--port 8000]
"""

import argparse
import logging
import os
import time

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
try:
    from radbot.logging_config import setup_logging

    setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

logger = logging.getLogger(__name__)


def main():
    """Parse arguments and start the PTY server."""
    parser = argparse.ArgumentParser(description="RadBot terminal worker")
    parser.add_argument(
        "--workspace-id",
        type=str,
        default=None,
        help="Workspace ID this worker serves",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )

    args = parser.parse_args()
    logger.info(
        "Starting terminal worker: workspace_id=%s, port=%d",
        args.workspace_id,
        args.port,
    )

    _start_server(
        workspace_id=args.workspace_id,
        host=args.host,
        port=args.port,
    )


def _start_server(workspace_id: str | None, host: str, port: int):
    """Build a Starlette app with terminal routes and run it."""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route, WebSocketRoute
    from starlette.websockets import WebSocket as StarletteWebSocket

    from radbot.worker.terminal_handler import (
        TerminalManager,
        handle_terminal_websocket,
    )

    start_time = time.monotonic()
    last_activity = time.monotonic()
    terminal_mgr = TerminalManager()

    # -- Endpoints --

    async def health(request):
        nonlocal last_activity
        last_activity = time.monotonic()
        return JSONResponse({
            "status": "healthy",
            "workspace_id": workspace_id,
            "uptime_seconds": round(time.monotonic() - start_time),
            "idle_seconds": round(time.monotonic() - last_activity),
            "terminal_sessions": len(terminal_mgr.list_sessions()),
        })

    async def info(request):
        return JSONResponse({
            "workspace_id": workspace_id,
            "uptime_seconds": round(time.monotonic() - start_time),
        })

    async def terminal_sessions_endpoint(request):
        nonlocal last_activity
        last_activity = time.monotonic()

        if request.method == "GET":
            return JSONResponse({"sessions": terminal_mgr.list_sessions()})

        # POST — create session
        body = await request.json()
        ws_id = body.get("workspace_id", workspace_id)
        resume_session_id = body.get("resume_session_id")

        if not ws_id:
            return JSONResponse({"error": "workspace_id required"}, status_code=400)

        try:
            session = terminal_mgr.create_session(ws_id, resume_session_id)
            return JSONResponse({
                "terminal_id": session.terminal_id,
                "workspace_id": session.workspace_id,
                "owner": session.workspace.get("owner"),
                "repo": session.workspace.get("repo"),
                "branch": session.workspace.get("branch"),
                "pid": session.pid,
            })
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=429)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=404)
        except Exception as e:
            logger.error("Error creating terminal session: %s", e, exc_info=True)
            return JSONResponse({"error": str(e)}, status_code=500)

    async def terminal_session_delete(request):
        terminal_id = request.path_params["terminal_id"]
        if terminal_mgr.kill_session(terminal_id):
            return JSONResponse(
                {"status": "success", "message": f"Session {terminal_id} killed"}
            )
        return JSONResponse(
            {"error": f"Session {terminal_id} not found"}, status_code=404
        )

    async def terminal_ws(websocket: StarletteWebSocket):
        nonlocal last_activity
        last_activity = time.monotonic()

        terminal_id = websocket.path_params["terminal_id"]
        session = terminal_mgr.get_session(terminal_id)

        if session is None or session.closed:
            await websocket.close(code=4004, reason="Terminal session not found")
            return

        await websocket.accept()
        await handle_terminal_websocket(websocket, session, terminal_mgr)

    # -- App --

    routes = [
        Route("/health", health),
        Route("/info", info),
        Route(
            "/terminal/sessions/",
            terminal_sessions_endpoint,
            methods=["GET", "POST"],
        ),
        Route(
            "/terminal/sessions/{terminal_id}",
            terminal_session_delete,
            methods=["DELETE"],
        ),
        WebSocketRoute("/ws/terminal/{terminal_id}", terminal_ws),
    ]

    async def lifespan(app):
        # Load integration configs (GitHub, etc.) from the credential store DB
        # before attempting workspace operations that need them.
        try:
            from radbot.config.config_loader import config_loader

            config_loader.load_db_config()
            logger.info("Loaded DB config overrides")
        except Exception as e:
            logger.warning("Failed to load DB config: %s", e)

        if workspace_id:
            _ensure_workspace_ready(workspace_id)
        logger.info("Terminal worker ready on %s:%d", host, port)
        yield

    app = Starlette(routes=routes, lifespan=lifespan)

    uvicorn.run(app, host=host, port=port, log_level="info")


def _ensure_workspace_ready(workspace_id: str) -> None:
    """Ensure workspace directory exists, cloning if needed."""
    try:
        from radbot.tools.claude_code.db import list_active_workspaces

        workspaces = list_active_workspaces()
        ws = next(
            (w for w in workspaces if str(w["workspace_id"]) == workspace_id),
            None,
        )
        if ws is None:
            logger.warning("Workspace %s not found in DB", workspace_id)
            return

        local_path = ws["local_path"]
        if os.path.isdir(local_path):
            logger.info("Workspace directory exists: %s", local_path)
            return

        if ws.get("owner") == "_scratch":
            os.makedirs(local_path, exist_ok=True)
            logger.info("Created scratch workspace directory: %s", local_path)
        else:
            try:
                from radbot.tools.github.github_app_client import get_github_client

                client = get_github_client()
                if client:
                    workspace_dir = os.environ.get("WORKSPACE_DIR", "/app/workspaces")
                    os.makedirs(workspace_dir, exist_ok=True)
                    result = client.clone_repo(
                        ws["owner"], ws["repo"], workspace_dir, ws.get("branch", "main")
                    )
                    if result.get("status") == "success":
                        logger.info("Cloned workspace %s/%s", ws["owner"], ws["repo"])
                    else:
                        logger.error("Clone failed: %s", result.get("message"))
                else:
                    logger.warning("GitHub client not configured — cannot clone workspace")
            except Exception as e:
                logger.error("Failed to clone workspace: %s", e)
    except Exception as e:
        logger.warning("Failed to ensure workspace ready: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
