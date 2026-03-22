"""Entry point for RadBot session worker.

Starts a persistent headless server that holds agent sessions and
terminal PTY processes in memory. Designed to run as a Nomad service
job — survives main app restarts and runs until explicitly stopped.

Usage:
    python -m radbot.worker --workspace-id <UUID> [--port 8000]
    python -m radbot.worker --session-id <UUID> [--port 8000]
"""

import argparse
import logging

from dotenv import load_dotenv

from radbot.logging_config import setup_logging

# Load environment variables
load_dotenv()

# Set up logging (single entry-point call)
setup_logging()
logger = logging.getLogger(__name__)


def main():
    """Parse arguments and start the worker server."""
    parser = argparse.ArgumentParser(description="Start a RadBot session worker")
    parser.add_argument(
        "--workspace-id",
        type=str,
        default=None,
        help="Workspace ID this worker serves (for terminal sessions)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Chat session ID this worker serves (for A2A chat)",
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
    if not args.workspace_id and not args.session_id:
        parser.error("Either --workspace-id or --session-id is required")

    logger.info(
        "Starting worker: workspace_id=%s, session_id=%s, port=%d",
        args.workspace_id,
        args.session_id,
        args.port,
    )

    _start_worker(
        workspace_id=args.workspace_id,
        session_id=args.session_id,
        host=args.host,
        port=args.port,
    )


def _init_schemas():
    """Initialize DB schemas needed by the agent tools."""
    inits = [
        ("todo", "radbot.tools.todo", "init_database"),
        ("scheduler", "radbot.tools.scheduler", "init_scheduler_schema"),
        ("webhooks", "radbot.tools.webhooks", "init_webhook_schema"),
        ("reminders", "radbot.tools.reminders", "init_reminder_schema"),
    ]
    for name, module, func in inits:
        try:
            mod = __import__(module, fromlist=[func])
            getattr(mod, func)()
            logger.debug("Initialized %s schema", name)
        except Exception as e:
            logger.warning("Failed to initialize %s schema: %s", name, e)


def _start_worker(
    workspace_id: str | None,
    session_id: str | None,
    host: str,
    port: int,
):
    """Build the Starlette app and run it with uvicorn."""
    import uvicorn
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse
    from starlette.routing import Route, WebSocketRoute
    from starlette.websockets import WebSocket as StarletteWebSocket

    from google.adk.a2a.utils.agent_to_a2a import to_a2a
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    from radbot.worker.idle_watchdog import ActivityMiddleware, ActivityWatchdog
    from radbot.worker.terminal_handler import (
        TerminalManager,
        handle_terminal_websocket,
    )

    # Import the root agent (triggers agent creation)
    from radbot.agent.agent_core import root_agent

    # Initialize DB schemas needed by the agent (call init functions
    # directly — setup_before_agent_call is an ADK callback that
    # requires CallbackContext which we don't have in the worker)
    _init_schemas()

    # Build the ADK Runner
    app_name = root_agent.name if hasattr(root_agent, "name") else "beto"
    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()

    memory_service = None
    if hasattr(root_agent, "_memory_service"):
        memory_service = root_agent._memory_service
    elif hasattr(root_agent, "memory_service"):
        memory_service = root_agent.memory_service

    runner = Runner(
        agent=root_agent,
        app_name=app_name,
        session_service=session_service,
        artifact_service=artifact_service,
        memory_service=memory_service,
    )

    # Enable context caching
    try:
        from google.adk.agents.context_cache_config import ContextCacheConfig

        runner.context_cache_config = ContextCacheConfig(
            cache_intervals=20,
            ttl_seconds=3600,
            min_tokens=2048,
        )
    except Exception as e:
        logger.warning("Could not enable context caching: %s", e)

    # Create the A2A Starlette app
    a2a_app = to_a2a(
        root_agent,
        host=host,
        port=port,
        protocol="http",
        runner=runner,
    )

    # Activity watchdog for health reporting
    watchdog = ActivityWatchdog()
    a2a_app.add_middleware(ActivityMiddleware, watchdog=watchdog)

    # Terminal manager for PTY sessions (workspace workers)
    terminal_mgr = TerminalManager()

    # -- Health and info endpoints --

    async def health_endpoint(request):
        return JSONResponse({
            "status": "healthy",
            "workspace_id": workspace_id,
            "session_id": session_id,
            "idle_seconds": round(watchdog.idle_seconds),
            "uptime_seconds": round(watchdog.uptime_seconds),
            "terminal_sessions": len(terminal_mgr.list_sessions()),
        })

    async def info_endpoint(request):
        return JSONResponse({
            "workspace_id": workspace_id,
            "session_id": session_id,
            "agent_name": app_name,
            "idle_seconds": round(watchdog.idle_seconds),
            "uptime_seconds": round(watchdog.uptime_seconds),
        })

    # -- Terminal REST endpoints --

    async def terminal_sessions_list(request: StarletteRequest):
        return JSONResponse({"sessions": terminal_mgr.list_sessions()})

    async def terminal_sessions_create(request: StarletteRequest):
        body = await request.json()
        ws_id = body.get("workspace_id", workspace_id)
        resume_session_id = body.get("resume_session_id")

        if not ws_id:
            return JSONResponse(
                {"error": "workspace_id required"}, status_code=400
            )

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

    async def terminal_sessions_handle(request: StarletteRequest):
        """Route GET/POST for /terminal/sessions/."""
        if request.method == "GET":
            return await terminal_sessions_list(request)
        elif request.method == "POST":
            return await terminal_sessions_create(request)
        return JSONResponse({"error": "Method not allowed"}, status_code=405)

    async def terminal_session_delete(request: StarletteRequest):
        terminal_id = request.path_params["terminal_id"]
        if terminal_mgr.kill_session(terminal_id):
            return JSONResponse(
                {"status": "success", "message": f"Session {terminal_id} killed"}
            )
        return JSONResponse(
            {"error": f"Session {terminal_id} not found"}, status_code=404
        )

    # -- Terminal WebSocket endpoint --

    async def terminal_ws_handler(websocket: StarletteWebSocket):
        terminal_id = websocket.path_params["terminal_id"]
        session = terminal_mgr.get_session(terminal_id)

        if session is None or session.closed:
            await websocket.close(code=4004, reason="Terminal session not found")
            return

        await websocket.accept()
        await handle_terminal_websocket(websocket, session, terminal_mgr)

    # -- Register routes --

    a2a_app.routes.insert(0, Route("/health", health_endpoint))
    a2a_app.routes.insert(1, Route("/info", info_endpoint))
    a2a_app.routes.insert(
        2,
        Route(
            "/terminal/sessions/",
            terminal_sessions_handle,
            methods=["GET", "POST"],
        ),
    )
    a2a_app.routes.insert(
        3,
        Route(
            "/terminal/sessions/{terminal_id}",
            terminal_session_delete,
            methods=["DELETE"],
        ),
    )
    a2a_app.routes.insert(
        4,
        WebSocketRoute("/ws/terminal/{terminal_id}", terminal_ws_handler),
    )

    # -- Startup --

    original_startup_handlers = list(a2a_app.on_startup)

    async def startup():
        for handler in original_startup_handlers:
            await handler()
        # Seed chat history if this is a session worker
        if session_id:
            await _seed_session(session_id, session_service, app_name)
        # Ensure workspace directory exists if this is a workspace worker
        if workspace_id:
            _ensure_workspace_ready(workspace_id)

    a2a_app.on_startup.clear()
    a2a_app.add_event_handler("startup", startup)

    logger.info("Worker server starting on %s:%d", host, port)
    uvicorn.run(a2a_app, host=host, port=port, log_level="info")


def _ensure_workspace_ready(workspace_id: str) -> None:
    """Ensure workspace directory exists, cloning if needed."""
    import os

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

        # Re-create directory
        if ws.get("owner") == "_scratch":
            os.makedirs(local_path, exist_ok=True)
            logger.info("Created scratch workspace directory: %s", local_path)
        else:
            from radbot.tools.claude_code.claude_code_tools import clone_repository

            result = clone_repository(
                owner=ws["owner"],
                repo=ws["repo"],
                branch=ws.get("branch", "main"),
            )
            if result.get("status") == "success":
                logger.info(
                    "Cloned workspace %s/%s for worker", ws["owner"], ws["repo"]
                )
            else:
                logger.error(
                    "Failed to clone workspace: %s", result.get("message")
                )
    except Exception as e:
        logger.warning("Failed to ensure workspace ready: %s", e, exc_info=True)


async def _seed_session(session_id: str, session_service, app_name: str):
    """Pre-load chat history from DB into the worker's session."""
    try:
        from radbot.worker.history_loader import load_history_into_session

        user_id = "web_user"
        session = await session_service.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        await load_history_into_session(
            session=session,
            session_id=session_id,
            session_service=session_service,
            agent_name=app_name,
        )
        logger.info("Seeded worker session %s with DB history", session_id)
    except Exception as e:
        logger.warning("Failed to seed session history: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
