"""Entry point for RadBot session worker.

Starts a persistent headless A2A agent server that holds a single session
in memory. Designed to run as a Nomad service job — survives main app
restarts and runs until explicitly stopped.

Usage:
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
    """Parse arguments and start the A2A worker server."""
    parser = argparse.ArgumentParser(description="Start a RadBot session worker")
    parser.add_argument(
        "--session-id",
        type=str,
        required=True,
        help="Session ID this worker serves",
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
        "Starting session worker: session_id=%s, port=%d",
        args.session_id,
        args.port,
    )

    _start_worker(
        session_id=args.session_id,
        host=args.host,
        port=args.port,
    )


def _start_worker(session_id: str, host: str, port: int):
    """Build the A2A Starlette app and run it with uvicorn."""
    import uvicorn
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from google.adk.a2a.utils.agent_to_a2a import to_a2a
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    from radbot.worker.idle_watchdog import ActivityMiddleware, ActivityWatchdog

    # Import the root agent (triggers agent creation)
    from radbot.agent.agent_core import root_agent

    # Initialize DB schemas needed by the agent (todo, scheduler, etc.)
    from radbot.agent.agent_tools_setup import setup_before_agent_call

    setup_before_agent_call()

    # Build the Runner with proper services
    app_name = root_agent.name if hasattr(root_agent, "name") else "beto"

    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()

    # Get memory service from root_agent if available
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
        logger.debug("Enabled context caching on worker Runner")
    except Exception as e:
        logger.warning("Could not enable context caching: %s", e)

    # Create the A2A Starlette app, passing our pre-configured Runner
    a2a_app = to_a2a(
        root_agent,
        host=host,
        port=port,
        protocol="http",
        runner=runner,
    )

    # Set up activity watchdog for health reporting
    watchdog = ActivityWatchdog()
    a2a_app.add_middleware(ActivityMiddleware, watchdog=watchdog)

    # Add health and metadata endpoints
    async def health_endpoint(request):
        return JSONResponse(
            {
                "status": "healthy",
                "session_id": session_id,
                "idle_seconds": round(watchdog.idle_seconds),
                "uptime_seconds": round(watchdog.uptime_seconds),
            }
        )

    async def info_endpoint(request):
        return JSONResponse(
            {
                "session_id": session_id,
                "agent_name": app_name,
                "idle_seconds": round(watchdog.idle_seconds),
                "uptime_seconds": round(watchdog.uptime_seconds),
            }
        )

    a2a_app.routes.insert(0, Route("/health", health_endpoint))
    a2a_app.routes.insert(1, Route("/info", info_endpoint))

    # Seed session history on startup
    original_startup_handlers = list(a2a_app.on_startup)

    async def startup_with_seed():
        for handler in original_startup_handlers:
            await handler()
        await _seed_session(session_id, session_service, app_name)

    a2a_app.on_startup.clear()
    a2a_app.add_event_handler("startup", startup_with_seed)

    logger.info("Worker A2A server starting on %s:%d", host, port)
    uvicorn.run(a2a_app, host=host, port=port, log_level="info")


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
