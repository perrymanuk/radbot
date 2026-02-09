"""
Main FastAPI application for RadBot web interface.

This module defines the FastAPI application for the RadBot web interface.
"""
import asyncio
import logging
import os
import uuid
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.cors import CORSMiddleware
import uvicorn

from radbot.config import config_manager
from radbot.web.api.session import (
    SessionManager,
    get_session_manager,
    get_or_create_runner_for_session,
    memory_router,
)

# Import API routers for registration
from radbot.web.api.events import register_events_router
from radbot.web.api.agent_info import register_agent_info_router
from radbot.web.api.sessions import register_sessions_router
from radbot.web.api.messages import register_messages_router
from radbot.web.api.scheduler import router as scheduler_router
from radbot.web.api.webhooks import router as webhooks_router
from radbot.web.api.tts import router as tts_router
from radbot.web.api.stt import router as stt_router
from radbot.web.api.admin import router as admin_router

# Set up logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def create_app():
    """Create and configure the FastAPI application.
    
    Returns:
        FastAPI: The configured FastAPI application
    """
    # Create FastAPI app
    app = FastAPI(
        title="RadBot Web Interface",
        description="Web interface for interacting with RadBot agent",
        version="0.1.0",
    )
    
    # Register API routers immediately after app creation
    register_events_router(app)
    register_agent_info_router(app)
    register_sessions_router(app)
    register_messages_router(app)
    app.include_router(memory_router)
    app.include_router(scheduler_router)
    app.include_router(webhooks_router)
    app.include_router(tts_router)
    app.include_router(stt_router)
    app.include_router(admin_router)
    logger.info("API routers registered during app initialization")
    
    return app

# Create the FastAPI app instance
app = create_app()

# Define a startup event to initialize database schema and MCP servers
@app.on_event("startup")
async def initialize_app_startup():
    """Initialize database schema and MCP server tools on application startup."""
    try:
        # First initialize the chat history database schema
        logger.info("Initializing chat history database schema...")
        try:
            from radbot.web.db import chat_operations
            success = chat_operations.create_schema_if_not_exists()
            if success:
                logger.info("Chat history database schema initialized successfully")
            else:
                logger.warning("Failed to initialize chat history database schema")
        except Exception as db_error:
            logger.error(f"Error initializing chat history database: {str(db_error)}", exc_info=True)
            # Continue app startup even if database initialization fails
            
        # Initialize todo database schema (runs migrations like adding title column)
        logger.info("Initializing todo database schema...")
        try:
            from radbot.tools.todo.db.schema import create_schema_if_not_exists as init_todo_schema
            init_todo_schema()
            logger.info("Todo database schema initialized successfully")
        except Exception as todo_err:
            logger.error(f"Error initializing todo database: {str(todo_err)}", exc_info=True)

        # Initialize scheduler and webhook database schemas
        logger.info("Initializing scheduler database schema...")
        try:
            from radbot.tools.scheduler.db import init_scheduler_schema
            init_scheduler_schema()
            logger.info("Scheduler database schema initialized successfully")
        except Exception as sched_err:
            logger.error(f"Error initializing scheduler database: {str(sched_err)}", exc_info=True)

        logger.info("Initializing webhook database schema...")
        try:
            from radbot.tools.webhooks.db import init_webhook_schema
            init_webhook_schema()
            logger.info("Webhook database schema initialized successfully")
        except Exception as wh_err:
            logger.error(f"Error initializing webhook database: {str(wh_err)}", exc_info=True)

        # Initialize credential store schema
        logger.info("Initializing credential store schema...")
        try:
            from radbot.credentials.store import CredentialStore
            CredentialStore.init_schema()
            logger.info("Credential store schema initialized successfully")
        except Exception as cred_err:
            logger.error(f"Error initializing credential store: {str(cred_err)}", exc_info=True)

        # Load config overrides from the credential store DB
        logger.info("Loading config overrides from credential store...")
        try:
            from radbot.config.config_loader import config_loader
            config_loader.load_db_config()
            logger.info("Config overrides loaded from credential store")
        except Exception as cfg_err:
            logger.error(f"Error loading DB config: {str(cfg_err)}", exc_info=True)

        # Re-run environment setup now that full config (including DB overrides) is loaded
        try:
            from radbot.config.adk_config import setup_vertex_environment
            setup_vertex_environment()
            logger.info("Re-initialized vertex/API-key environment after DB config load")
        except Exception as env_err:
            logger.warning(f"Error re-initializing environment: {env_err}")

        # Prune disabled MCP server tools from the root agent.
        # The root agent is created at import time using config.yaml, before DB
        # config overrides are loaded. This step removes tools from MCP servers
        # that were disabled via the /admin UI (stored in DB).
        try:
            from agent import root_agent
            from radbot.config.config_loader import config_loader as _cl
            from radbot.tools.mcp.dynamic_tools_loader import _MCP_TOOL_BLOCKLIST

            enabled_server_ids = {
                s.get("id") for s in _cl.get_enabled_mcp_servers()
            }
            all_server_ids = {
                s.get("id") for s in _cl.get_mcp_servers()
            }
            disabled_server_ids = all_server_ids - enabled_server_ids

            if disabled_server_ids:
                original_count = len(root_agent.tools)
                # Build set of tool names to remove: blocklisted + tools from disabled servers
                tools_to_remove = set(_MCP_TOOL_BLOCKLIST)

                # Get tool names from disabled servers by checking the MCP client factory
                try:
                    from radbot.tools.mcp.mcp_client_factory import MCPClientFactory
                    for sid in disabled_server_ids:
                        client = MCPClientFactory.get_client(sid) if MCPClientFactory else None
                        if client:
                            server_tools = client.tools if hasattr(client, 'tools') else []
                            for t in (server_tools or []):
                                name = getattr(t, 'name', None) or getattr(t, '__name__', None)
                                if name:
                                    tools_to_remove.add(name)
                except Exception:
                    pass  # If we can't get client tools, rely on the blocklist

                root_agent.tools = [
                    t for t in root_agent.tools
                    if (getattr(t, '__name__', None) or getattr(t, 'name', ''))
                    not in tools_to_remove
                ]
                removed = original_count - len(root_agent.tools)
                if removed:
                    logger.info(
                        f"Pruned {removed} MCP tools from root agent "
                        f"(disabled servers: {disabled_server_ids}). "
                        f"Tools: {original_count} -> {len(root_agent.tools)}"
                    )
        except Exception as prune_err:
            logger.warning(f"Error pruning disabled MCP tools: {prune_err}")

        # Start the scheduler engine
        logger.info("Starting scheduler engine...")
        try:
            from radbot.tools.scheduler.engine import SchedulerEngine

            engine = SchedulerEngine.create_instance()
            engine.inject(connection_manager=manager, session_manager=get_session_manager())
            await engine.start()
            logger.info("Scheduler engine started successfully")
        except Exception as engine_err:
            logger.error(f"Error starting scheduler engine: {str(engine_err)}", exc_info=True)

        # Initialize TTS service (lazy, just load config)
        try:
            from radbot.tools.tts.tts_service import TTSService
            from radbot.config import config_loader
            tts_config = config_loader.get_config().get("tts", {})
            if tts_config.get("enabled", True):
                TTSService.create_instance(
                    voice_name=tts_config.get("voice_name"),
                    language_code=tts_config.get("language_code"),
                    speaking_rate=tts_config.get("speaking_rate"),
                    pitch=tts_config.get("pitch"),
                )
                logger.info("TTS service instance created")
        except Exception as tts_err:
            logger.error(f"Error initializing TTS service: {str(tts_err)}", exc_info=True)

        # Initialize STT service (lazy, just load config)
        try:
            from radbot.tools.stt.stt_service import STTService
            from radbot.config import config_loader as stt_config_loader
            stt_config = stt_config_loader.get_config().get("stt", {})
            if stt_config.get("enabled", True):
                STTService.create_instance(
                    language_code=stt_config.get("language_code"),
                    model=stt_config.get("model"),
                    enable_automatic_punctuation=stt_config.get("enable_automatic_punctuation", True),
                )
                logger.info("STT service instance created")
        except Exception as stt_err:
            logger.error(f"Error initializing STT service: {str(stt_err)}", exc_info=True)

        # Then initialize MCP servers
        logger.info("Initializing MCP servers at application startup...")
        from radbot.tools.mcp.mcp_client_factory import MCPClientFactory
        from radbot.config.config_loader import config_loader
        
        # Just check if servers are enabled and can connect
        servers = config_loader.get_enabled_mcp_servers()
        logger.info(f"Found {len(servers)} enabled MCP servers in configuration")
        
        for server in servers:
            server_id = server.get("id", "unknown")
            server_name = server.get("name", server_id)
            logger.info(f"MCP server enabled: {server_name} (ID: {server_id})")
            
        # Don't attempt to create tools here - we'll do that in the session
        # when a new client connects, which is safer and more reliable
        
    except Exception as e:
        logger.error(f"Failed during application startup: {str(e)}", exc_info=True)

@app.on_event("shutdown")
async def shutdown_scheduler():
    """Shut down the scheduler engine gracefully."""
    try:
        from radbot.tools.scheduler.engine import SchedulerEngine
        engine = SchedulerEngine.get_instance()
        if engine:
            await engine.shutdown()
            logger.info("Scheduler engine shut down")
    except Exception as e:
        logger.error(f"Error shutting down scheduler engine: {e}", exc_info=True)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Mount static files directory
# Create a custom class that only handles HTTP requests, not WebSocket
class HTTPOnlyStaticFiles(StaticFiles):
    """StaticFiles class that only handles HTTP requests, not WebSocket."""
    async def __call__(self, scope, receive, send):
        """Handle request or return 404 for non-HTTP requests."""
        if scope["type"] != "http":
            # Log and ignore non-HTTP requests (like WebSocket)
            logger.info(f"Ignoring non-HTTP request to static files: {scope['type']}")
            return
        await super().__call__(scope, receive, send)

def mount_static_files():
    """Mount static files after all routes have been defined."""
    try:
        app.mount(
            "/static",
            HTTPOnlyStaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
            name="static"
        )
        logger.info("Static files mounted successfully")
    except Exception as e:
        logger.error(f"Error mounting static files: {str(e)}", exc_info=True)

# Schedule static files mounting after all other routes are registered
@app.on_event("startup")
async def mount_static_files_on_startup():
    """Mount static files during application startup after routes are registered."""
    mount_static_files()

# Set up Jinja2 templates
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        count = len(self.active_connections[session_id])
        logger.info(f"WebSocket connected for session {session_id} ({count} connection(s) now)")

    def disconnect(self, session_id: str, websocket: WebSocket = None):
        if session_id not in self.active_connections:
            return
        if websocket is None:
            del self.active_connections[session_id]
        else:
            self.active_connections[session_id] = [
                ws for ws in self.active_connections[session_id] if ws is not websocket
            ]
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def _send_to_all(self, session_id: str, payload: dict) -> None:
        """Send payload to all WebSocket connections for a session, removing dead ones."""
        if session_id not in self.active_connections:
            return
        dead: List[WebSocket] = []
        for ws in self.active_connections[session_id]:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        if dead:
            self.active_connections[session_id] = [
                ws for ws in self.active_connections[session_id] if ws not in dead
            ]
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast_to_all_sessions(self, payload: dict) -> int:
        """Send payload to every connection across all sessions. Returns send count."""
        sent = 0
        for session_id in list(self.active_connections):
            for ws in list(self.active_connections.get(session_id, [])):
                try:
                    await ws.send_json(payload)
                    sent += 1
                except Exception as e:
                    logger.warning(f"Failed to send to session {session_id}: {e}")
        return sent

    def get_any_session_id(self) -> Optional[str]:
        """Return the first active session_id, or None."""
        return next(iter(self.active_connections), None)

    def has_connections(self) -> bool:
        """Return True if there is at least one active connection."""
        return bool(self.active_connections)

    async def send_message(self, session_id: str, message: str):
        await self._send_to_all(session_id, {
            "type": "message",
            "content": message
        })

    async def send_status(self, session_id: str, status: str):
        await self._send_to_all(session_id, {
            "type": "status",
            "content": status
        })

    async def send_events(self, session_id: str, events: list):
        if session_id not in self.active_connections:
            return
        # Check for excessively large messages
        import json
        events_json = json.dumps({"type": "events", "content": events})
        max_size = 1024 * 1024  # 1MB limit

        if len(events_json) > max_size:
            # Log the oversized message
            logger.warning(f"Event payload too large: {len(events_json)} bytes. Splitting into chunks.")

            # Process events individually to find large ones
            for event in events:
                single_event_json = json.dumps({"type": "events", "content": [event]})
                event_size = len(single_event_json)
                event_type = event.get('type', 'unknown')
                event_summary = event.get('summary', 'no summary')

                if event_size > max_size:
                    # This event is too large - truncate any text content
                    logger.warning(f"Oversized event: {event_type} - {event_summary}: {event_size} bytes")
                    if 'text' in event and isinstance(event['text'], str) and len(event['text']) > 100000:
                        # Truncate text and add indicator
                        original_length = len(event['text'])
                        event['text'] = event['text'][:100000] + f"\n\n[Message truncated due to size constraints. Original length: {original_length} characters]"
                        logger.info(f"Truncated event text from {original_length} to {len(event['text'])} characters")

                        await self._send_to_all(session_id, {
                            "type": "events",
                            "content": [event]
                        })
                else:
                    # Send normal-sized events individually
                    await self._send_to_all(session_id, {
                        "type": "events",
                        "content": [event]
                    })
        else:
            # Send as normal if not oversized
            await self._send_to_all(session_id, {
                "type": "events",
                "content": events
            })

# Create connection manager
manager = ConnectionManager()

def _react_index_path() -> Optional[str]:
    """Return the path to the React build index.html if it exists."""
    dist_index = os.path.join(os.path.dirname(__file__), "static", "dist", "index.html")
    return dist_index if os.path.isfile(dist_index) else None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main chat interface.

    If a React build exists in static/dist/, serve the React SPA.
    Otherwise fall back to the legacy Jinja2 template.
    """
    react_index = _react_index_path()
    if react_index:
        # Serve the Vite-generated index.html directly (it contains hashed asset references)
        with open(react_index, "r") as f:
            html = f.read()
        # Rewrite asset paths: Vite outputs /assets/... but we serve from /static/dist/assets/...
        html = html.replace('"/assets/', '"/static/dist/assets/')
        html = html.replace("'/assets/", "'/static/dist/assets/")
        return HTMLResponse(content=html)
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/api/chat")
async def chat(
    message: str = Form(...),
    session_id: Optional[str] = Form(None),
    session_manager: SessionManager = Depends(get_session_manager)
):
    """Process a user message and return the agent's response.
    
    Args:
        message: The user's message
        session_id: Optional session ID (if not provided, a new one will be created)
        
    Returns:
        JSON response with session_id and agent's response
    """
    # Generate a session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.info(f"Created new session ID: {session_id}")
    else:
        logger.info(f"Using existing session ID: {session_id}")
    
    # Get or create a runner for this session
    runner = await get_or_create_runner_for_session(session_id, session_manager)
    
    try:
        # Process the message
        logger.info(f"Processing message for session {session_id}: {message[:50]}{'...' if len(message) > 50 else ''}")
        result = await runner.process_message(message)

        # Extract response and events
        response = result.get("response", "")
        events = result.get("events", [])
        
        # Process events for size constraints to match WebSocket behavior
        max_size = 1024 * 1024  # 1MB limit
        processed_events = []
        
        for event in events:
            if 'text' in event and isinstance(event['text'], str) and len(event['text']) > 100000:
                # Truncate large text events
                event_copy = event.copy()  # Create a copy to avoid modifying the original
                original_length = len(event_copy['text'])
                event_copy['text'] = event_copy['text'][:100000] + f"\n\n[Message truncated due to size constraints. Original length: {original_length} characters]"
                logger.info(f"Truncated REST API event text from {original_length} to {len(event_copy['text'])} characters")
                processed_events.append(event_copy)
            else:
                processed_events.append(event)
        
        # Return the response with session information and processed events
        return {
            "session_id": session_id,
            "response": response,
            "events": processed_events
        }
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str, session_manager: SessionManager = Depends(get_session_manager)):
    """WebSocket endpoint for real-time chat.

    Args:
        websocket: The WebSocket connection
        session_id: The session ID
    """
    await manager.connect(websocket, session_id)

    try:
        # Get or create a runner for this session
        runner = await get_or_create_runner_for_session(session_id, session_manager)

        # Ensure session is registered in the database
        try:
            from radbot.web.db import chat_operations
            chat_operations.create_or_update_session(session_id=session_id, name=f"Session {session_id[:8]}")
        except Exception as db_err:
            logger.warning(f"Failed to register session in DB: {db_err}")

        # Send ready status
        await manager.send_status(session_id, "ready")
        
        # Helper function to get events from a session
        def get_events_from_session(session):
            if not hasattr(session, 'events') or not session.events:
                return []
            
            messages = []
            for event in session.events:
                if hasattr(event, 'content') and event.content:
                    # Try to extract text content for different ADK versions
                    text_content = ""
                    if hasattr(event.content, 'parts') and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, 'text') and part.text:
                                text_content += part.text
                    elif hasattr(event.content, 'text') and event.content.text:
                        text_content = event.content.text
                    
                    # Determine the role/author
                    role = getattr(event, 'author', 'assistant')
                    
                    # Create a message object if we have content
                    if text_content:
                        message = {
                            "id": getattr(event, 'id', str(uuid.uuid4())),
                            "role": role,
                            "content": text_content,
                            "timestamp": int(getattr(event, 'timestamp', time.time()) * 1000),  # Convert to JS timestamp
                            "agent": getattr(event, 'agent_name', None) or getattr(event, 'agent', None)
                        }
                        messages.append(message)
            
            return messages
        
        # Process heartbeat messages
        async def handle_heartbeat():
            await websocket.send_json({
                "type": "heartbeat"
            })
            logger.debug(f"Sent heartbeat response for session {session_id}")
        
        # Process sync_request messages
        async def handle_sync_request(last_message_id, timestamp=None):
            logger.info(f"Handling sync request for session {session_id} since message {last_message_id}")

            # Get app name for this session
            app_name = runner.runner.app_name if hasattr(runner, 'runner') and hasattr(runner.runner, 'app_name') else "beto"

            # Retrieve the session from ADK (get_session is async in ADK 1.21.0)
            session = await runner.session_service.get_session(
                app_name=app_name,
                user_id=runner.user_id,
                session_id=session_id
            )
            
            if not session:
                logger.warning(f"No session found for sync request with ID {session_id}")
                await websocket.send_json({
                    "type": "sync_response",
                    "messages": []
                })
                return
            
            # Get all messages from the session
            all_messages = get_events_from_session(session)
            
            # Find the index of the last known message
            last_index = -1
            for i, msg in enumerate(all_messages):
                if msg.get("id") == last_message_id:
                    last_index = i
                    break
            
            # Extract messages after the last known one
            messages = []
            if last_index >= 0 and last_index < len(all_messages) - 1:
                messages = all_messages[last_index + 1:]
            
            # Send the sync response
            await websocket.send_json({
                "type": "sync_response",
                "messages": messages
            })
            
            logger.info(f"Sent sync response with {len(messages)} messages for session {session_id}")
        
        # Process history_request messages
        async def handle_history_request(limit=50):
            logger.info(f"Handling history request for session {session_id}, limit={limit}")

            # Get app name for this session
            app_name = runner.runner.app_name if hasattr(runner, 'runner') and hasattr(runner.runner, 'app_name') else "beto"

            # Retrieve the session from ADK (get_session is async in ADK 1.21.0)
            session = await runner.session_service.get_session(
                app_name=app_name,
                user_id=runner.user_id,
                session_id=session_id
            )
            
            if not session:
                logger.warning(f"No session found for history request with ID {session_id}")
                await websocket.send_json({
                    "type": "history",
                    "messages": []
                })
                return
            
            # Get all messages from the session
            all_messages = get_events_from_session(session)
            
            # Limit the number of messages if needed
            messages = all_messages[-limit:] if limit and len(all_messages) > limit else all_messages
            
            # Send the history response
            await websocket.send_json({
                "type": "history",
                "messages": messages
            })
            
            logger.info(f"Sent history response with {len(messages)} messages for session {session_id}")
        
        while True:
            # Wait for a message from the client
            data = await websocket.receive_json()
            
            # Handle different message types
            if data.get("type") == "heartbeat":
                await handle_heartbeat()
                continue
            
            elif data.get("type") == "sync_request":
                last_message_id = data.get("lastMessageId")
                timestamp = data.get("timestamp")
                if last_message_id:
                    await handle_sync_request(last_message_id, timestamp)
                else:
                    await manager.send_status(session_id, "error: Missing lastMessageId in sync_request")
                continue
            
            elif data.get("type") == "history_request":
                limit = data.get("limit", 50)
                await handle_history_request(limit)
                continue
            
            # Handle regular chat messages
            if "message" not in data:
                await manager.send_status(session_id, "error: Invalid message format")
                continue

            user_message = data["message"]

            # Check for special command to reset session to Beto
            if user_message.lower() in ["reset to beto", "use beto", "start beto"]:
                logger.info(f"Explicit request to reset session to Beto agent")
                if hasattr(runner, 'reset_session'):
                    await runner.reset_session()
                    await manager.send_status(session_id, "reset")
                    await manager.send_events(session_id, [{
                        "type": "system",
                        "category": "system",
                        "text": "Session reset to Beto agent",
                        "timestamp": datetime.now().isoformat()
                    }])
                    await manager.send_status(session_id, "ready")
                    continue

            # Check for special agent targeting message format (AGENT:NAME:actual message)
            target_agent = None
            if user_message.startswith("AGENT:"):
                parts = user_message.split(":", 2)
                if len(parts) >= 3:
                    target_agent = parts[1].strip().lower()
                    user_message = parts[2].strip()
                    logger.info(f"Detected explicit agent targeting: {target_agent}")

            # Send "thinking" status
            await manager.send_status(session_id, "thinking")

            try:
                # Process the message
                logger.info(f"Processing WebSocket message for session {session_id}")

                # Handle explicit agent targeting if present
                if target_agent:
                    # Import agent transfer tool
                    from radbot.tools.agent_transfer import process_request, find_agent_by_name
                    from agent import root_agent  # Import from root module

                    # Debug the agent tree
                    logger.info("DEBUG: Agent tree structure:")
                    if hasattr(root_agent, 'name'):
                        logger.info(f"Root agent name: {root_agent.name}")
                    else:
                        logger.info("Root agent has no name attribute")

                    if hasattr(root_agent, 'sub_agents'):
                        sub_agents = [sa.name for sa in root_agent.sub_agents if hasattr(sa, 'name')]
                        logger.info(f"Sub-agents: {sub_agents}")
                    else:
                        logger.info("Root agent has no sub_agents attribute")

                    # Make case-insensitive check for scout
                    if target_agent.lower() == 'scout':
                        # Try direct access to scout agent
                        for sub_agent in root_agent.sub_agents:
                            if hasattr(sub_agent, 'name') and sub_agent.name.lower() == 'scout':
                                logger.info(f"Found Scout agent directly: {sub_agent.name}")
                                # Process the request directly with the Scout agent's generate_content method
                                # This bypasses the transfer mechanism completely to avoid context bleed
                                try:
                                    # First try direct generation to bypass any transfer issues
                                    if hasattr(sub_agent, 'generate_content') and callable(sub_agent.generate_content):
                                        logger.info("Calling Scout's generate_content method directly")
                                        logger.info(f"Direct message to Scout: {user_message[:50]}...")
                                        response = sub_agent.generate_content(user_message)

                                        # Extract text from response
                                        if hasattr(response, 'text'):
                                            response_text = response.text
                                        elif hasattr(response, 'parts') and response.parts:
                                            response_text = ''
                                            for part in response.parts:
                                                if hasattr(part, 'text') and part.text:
                                                    response_text += part.text
                                        else:
                                            # Fallback to string representation
                                            response_text = str(response)

                                        logger.info(f"Direct Scout response received, length: {len(response_text)}")
                                    else:
                                        # Fallback to process_request
                                        logger.info("Fallback to process_request for Scout")
                                        response_text = process_request(sub_agent, user_message)
                                except Exception as e:
                                    logger.error(f"Error with direct generation: {str(e)}", exc_info=True)
                                    # Try process_request as a fallback
                                    response_text = process_request(sub_agent, user_message)

                                # Log the response for debugging
                                logger.info(f"Scout's response (first 100 chars): {response_text[:100]}...")

                                # Create a result with the response
                                result = {
                                    "response": response_text,
                                    "events": [{
                                        "type": "model_response",
                                        "category": "model_response",
                                        "text": response_text,
                                        "is_final": True,
                                        "agent_name": "SCOUT",
                                        "timestamp": datetime.now().isoformat()
                                    }]
                                }
                                break
                        else:
                            # If we get here, we didn't find Scout directly
                            logger.warning("Could not find Scout agent directly in sub_agents")
                            # Try using the standard finder
                            target = find_agent_by_name(root_agent, target_agent)
                            if target:
                                logger.info(f"Found target agent with find_agent_by_name: {target.name}")
                                response_text = process_request(target, user_message)
                                result = {
                                    "response": response_text,
                                    "events": [{
                                        "type": "model_response",
                                        "category": "model_response",
                                        "text": response_text,
                                        "is_final": True,
                                        "agent_name": target.name,
                                        "timestamp": datetime.now().isoformat()
                                    }]
                                }
                            else:
                                logger.warning(f"Target agent {target_agent} not found, using default runner")
                                result = await runner.process_message(user_message)
                    else:
                        # Standard approach for other agents
                        target = find_agent_by_name(root_agent, target_agent)
                        if target:
                            logger.info(f"Found target agent: {target.name}")
                            # Process the request with the specific agent
                            response_text = process_request(target, user_message)
                            # Create a result with the response
                            result = {
                                "response": response_text,
                                "events": [{
                                    "type": "model_response",
                                    "category": "model_response",
                                    "text": response_text,
                                    "is_final": True,
                                    "agent_name": target.name,
                                    "timestamp": datetime.now().isoformat()
                                }]
                            }
                        else:
                            logger.warning(f"Target agent {target_agent} not found, using default runner")
                            result = await runner.process_message(user_message)
                else:
                    # Use normal runner for processing
                    result = await runner.process_message(user_message)
                
                # Extract response and events
                response = result.get("response", "")
                events = result.get("events", [])

                # Persist user message and assistant response to DB
                try:
                    from radbot.web.db import chat_operations
                    chat_operations.add_message(session_id, "user", user_message, user_id="web_user")
                    if response:
                        chat_operations.add_message(session_id, "assistant", response, user_id="web_user")
                except Exception as db_err:
                    logger.warning(f"Failed to persist messages to DB: {db_err}")

                # Log event sizes for debugging
                if events:
                    for idx, event in enumerate(events):
                        if 'text' in event and isinstance(event['text'], str):
                            text_size = len(event['text'])
                            if text_size > 10000:  # Only log notably large events
                                event_type = event.get('type', 'unknown')
                                event_summary = event.get('summary', 'no summary')
                                logger.info(f"Large event[{idx}] {event_type} - {event_summary}: text size = {text_size} bytes")
                
                # Send events only (events contain the model responses)
                if events:
                    logger.info(f"Sending {len(events)} events to client")
                    await manager.send_events(session_id, events)
                
                # Update status to ready (no need to send the response separately)
                await manager.send_status(session_id, "ready")
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {str(e)}", exc_info=True)
                await manager.send_status(session_id, f"error: {str(e)}")
    
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
        logger.info(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}", exc_info=True)
        manager.disconnect(session_id, websocket)

@app.get("/api/sessions/{session_id}/reset")
async def reset_session(
    session_id: str,
    session_manager: SessionManager = Depends(get_session_manager)
):
    """Reset a session's conversation history.
    
    Args:
        session_id: The session ID to reset
        
    Returns:
        JSON response with status
    """
    try:
        await session_manager.reset_session(session_id)
        return {"status": "ok", "message": "Session reset successfully"}
    except Exception as e:
        logger.error(f"Error resetting session: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error resetting session: {str(e)}")

@app.post("/api/tasks")
async def create_task_endpoint(request: Request):
    """Create a new task.

    Accepts JSON body with title, description, project_id, and optional
    status and category fields.

    Returns:
        The new task ID on success.
    """
    try:
        from radbot.tools.todo.api.task_tools import add_task

        body = await request.json()
        description = body.get("description", "")
        project_id = body.get("project_id", "")
        title = body.get("title") or None
        category = body.get("category") or None

        if not description and not title:
            raise HTTPException(status_code=400, detail="Title or description is required")
        if not project_id:
            raise HTTPException(status_code=400, detail="project_id is required")

        result = add_task(
            description=description or (title or ""),
            project_id=project_id,
            title=title,
            category=category,
            origin="web_ui",
        )

        if result.get("status") == "success":
            # If a non-default status was requested, update it after creation
            status = body.get("status")
            if status and status != "backlog":
                task_id = result.get("task_id")
                if task_id:
                    from radbot.tools.todo.api.update_tools import update_task
                    update_task(task_id=task_id, status=status)
            return result

        msg = result.get("message", "Unknown error")
        raise HTTPException(status_code=400, detail=msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating task: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating task: {str(e)}")

@app.get("/api/tasks")
async def get_tasks():
    """Get all tasks from the database directly.
    
    Returns:
        JSON list of tasks
    """
    try:
        # Import task listing function
        from radbot.tools.todo.api.list_tools import list_all_tasks
        
        # Call the function directly
        result = list_all_tasks()

        # list_all_tasks returns {"status": "success", "tasks": [...]}
        if isinstance(result, dict) and result.get("status") == "success":
            return result.get("tasks", [])

        logger.warning(f"list_all_tasks returned unexpected result: {result}")
        return []
    except Exception as e:
        logger.error(f"Error getting tasks: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting tasks: {str(e)}")

@app.delete("/api/tasks/{task_id}")
async def delete_task_endpoint(task_id: str):
    """Delete a task by ID.

    Returns:
        Confirmation on success, error on failure.
    """
    try:
        from radbot.tools.todo.api.task_tools import remove_task

        result = remove_task(task_id=task_id)

        if result.get("status") == "success":
            return result

        msg = result.get("message", "Unknown error")
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task {task_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting task: {str(e)}")

@app.put("/api/tasks/{task_id}")
async def update_task_endpoint(task_id: str, request: Request):
    """Update a task by ID.

    Accepts JSON body with optional fields: description, status, project_id.

    Returns:
        Updated task on success, error on failure.
    """
    try:
        from radbot.tools.todo.api.update_tools import update_task

        body = await request.json()

        # Extract supported fields
        kwargs = {}
        for field in ("description", "status", "project_id", "title"):
            if field in body:
                kwargs[field] = body[field]

        if not kwargs:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        result = update_task(task_id=task_id, **kwargs)

        if result.get("status") == "success":
            return result

        # Determine appropriate status code
        msg = result.get("message", "Unknown error")
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task {task_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating task: {str(e)}")

@app.get("/api/projects")
async def get_projects():
    """Get all projects from the database directly.
    
    Returns:
        JSON list of projects
    """
    try:
        # Import project listing function
        from radbot.tools.todo.api.project_tools import list_projects
        
        # Call the function directly
        result = list_projects()

        # list_projects returns {"status": "success", "projects": [...]}
        if isinstance(result, dict) and result.get("status") == "success":
            return result.get("projects", [])

        logger.warning(f"list_projects returned unexpected result: {result}")
        return []
    except Exception as e:
        logger.error(f"Error getting projects: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting projects: {str(e)}")

@app.get("/api/tools")
async def get_available_tools(session_id: Optional[str] = None, session_manager: SessionManager = Depends(get_session_manager)):
    """Get the list of available tools from the root agent.
    
    Args:
        session_id: Optional session ID to get tools from a specific session
        
    Returns:
        JSON list of tools with their details
    """
    try:
        # Import the root_agent directly
        from agent import root_agent
        
        # Use the specific session's runner if a session_id is provided
        if session_id:
            runner = await get_or_create_runner_for_session(session_id, session_manager)
            if hasattr(runner, "runner") and hasattr(runner.runner, "agent"):
                agent = runner.runner.agent
            else:
                agent = root_agent
        else:
            agent = root_agent
            
        # Check if agent has tools
        if not hasattr(agent, "tools") or not agent.tools:
            logger.warning("Agent has no tools attribute or tools list is empty")
            return []
            
        # Convert tools to a serializable format
        serializable_tools = []
        for tool in agent.tools:
            tool_dict = {
                "name": str(tool.name) if hasattr(tool, "name") else "unknown",
                "description": str(tool.description) if hasattr(tool, "description") else "",
            }
            
            # Add schema information if available
            if hasattr(tool, "input_schema"):
                if hasattr(tool.input_schema, "schema"):
                    tool_dict["input_schema"] = tool.input_schema.schema()
                elif hasattr(tool.input_schema, "to_dict"):
                    tool_dict["input_schema"] = tool.input_schema.to_dict()
                else:
                    tool_dict["input_schema"] = str(tool.input_schema)
                    
            # Add any other tool attributes that might be useful
            if hasattr(tool, "metadata"):
                tool_dict["metadata"] = tool.metadata
                
            serializable_tools.append(tool_dict)
        
        logger.info(f"Retrieved {len(serializable_tools)} tools")
        return serializable_tools
    except Exception as e:
        logger.error(f"Error getting tools: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting tools: {str(e)}")

# Mock events endpoint has been replaced with the real events API
# provided by radbot.web.api.events

def start_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Start the FastAPI server.
    
    Args:
        host: Host to bind to
        port: Port to bind to
        reload: Whether to reload on code changes
    """
    # Events router is already registered during module initialization
    
    logger.info(f"Starting RadBot web server on {host}:{port}")
    uvicorn.run("radbot.web.app:app", host=host, port=port, reload=reload)