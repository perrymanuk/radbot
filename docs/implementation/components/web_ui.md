# Web Interface Implementation

<!-- Version: 0.4.0 | Last Updated: 2025-05-07 -->


This document describes the web interface implementations for RadBot, including both the custom FastAPI interface and the ADK web server integration.

## Overview

RadBot offers two web interface options:

1. **ADK Web Server**: Using Google ADK's built-in web server via the `adk web` command
2. **Custom FastAPI Interface**: A modern, responsive custom web UI built with FastAPI and WebSockets

Both implementations provide a chat interface for interacting with the RadBot agent, with different features and flexibility.

## ADK Web Server

### Overview

The ADK web server provides a pre-built web interface for agent interaction with minimal configuration.

Key features:
- Built-in chat interface
- Automatic session management
- Integration with ADK tools
- Simple setup with `adk web` command

### Implementation

The ADK web server implementation uses the root-level `agent.py` file as its entry point:

1. The `create_agent()` function sets up the agent with all necessary tools
2. The `root_agent` variable is exported for ADK web to import
3. ADK handles the web server, session management, and HTTP endpoints

### Configuration

Configuration for the ADK web server is defined in `adk.config.json`:

```json
{
  "agent": {
    "model": "gemini-pro",
    "path": "agent.py"
  },
  "web": {
    "port": 8080,
    "host": "0.0.0.0"
  }
}
```

### Running the ADK Web Server

To run the ADK web server:

```bash
adk web
```

This starts the server on the configured port (default 8080) and makes the interface available at http://localhost:8080.

## Custom FastAPI Interface

### Overview

The custom web interface provides a modern, responsive chat interface with more flexibility and features than the ADK web server.

Key components:
- **FastAPI**: A modern, fast web framework for building APIs with Python
- **WebSockets**: For real-time bidirectional communication
- **Jinja2 Templates**: For server-side rendering of HTML
- **Vanilla JavaScript**: For client-side interactivity

### Architecture

The implementation follows a clean architecture with separation of concerns:

1. **API Layer**: FastAPI routes and endpoints
2. **Session Management**: Handling user sessions and agent instances
3. **UI Layer**: HTML templates, CSS styling, and JavaScript for user interaction

### Key Components

#### 1. FastAPI Application (`app.py`)

The main FastAPI application handles HTTP requests, WebSocket connections, and routes users to the appropriate endpoints. It integrates with the RadBot agent to process user messages and return responses.

Key features:
- REST API endpoint for processing messages (`/api/chat`)
- WebSocket endpoint for real-time chat (`/ws/{session_id}`)
- Session management to persist user conversations
- Serving static files (JavaScript, CSS) and HTML templates

#### 2. Session Management (`session.py`)

The session management module handles:
- Creating and tracking user sessions
- Initializing and managing agent instances for each session
- Providing a clean interface for the API layer to interact with agents

#### 3. HTML Template (`index.html`)

A clean, responsive chat interface that:
- Displays conversation history with proper formatting for markdown
- Provides a text input area with support for multi-line input
- Shows status indicators for agent processing
- Includes a button to reset the conversation

#### 4. JavaScript Client (`app_main.js`, `chat.js`, `socket.js`)

Client-side JavaScript that handles:
- WebSocket connection management
- Sending and receiving messages
- Rendering messages with markdown support
- Managing the UI state based on agent status
- Handling session persistence via localStorage

#### 5. CSS Styling (`style.css`)

Modern styling with:
- Responsive design that works on mobile and desktop
- Clean message bubbles for user and agent messages
- Support for markdown rendering including code blocks
- Status indicators for agent state

### Interaction Flow

1. **User Loads the Page**:
   - Client generates a session ID or retrieves existing one from localStorage
   - Client establishes WebSocket connection with the server
   - Server initializes or retrieves an agent for the session

2. **User Sends a Message**:
   - Client sends message via WebSocket
   - Message is displayed in the UI immediately
   - Status changes to "thinking"

3. **Server Processes the Message**:
   - Server receives the message via WebSocket
   - RadBot agent processes the message
   - Any tool usage happens on the server side

4. **Server Sends Response**:
   - Agent's response is sent back via WebSocket
   - Client receives and displays the response
   - Status changes back to "ready"

5. **Session Management**:
   - Conversation history is maintained in the agent's session
   - User can reset the conversation via UI button
   - Session persists across page reloads via localStorage

### Running the Custom Web Interface

To run the custom web interface:

```bash
make run-web
```

This will:
1. Install necessary dependencies
2. Start the FastAPI server with auto-reload enabled
3. Make the interface available at http://localhost:8000

## WebSocket vs. HTTP

The custom web interface implementation supports both WebSocket and HTTP communication:
- WebSocket is used for real-time chat experience
- HTTP fallback is available if WebSocket connection fails

### WebSocket Implementation

```javascript
// Client-side WebSocket connection
const socket = new WebSocket(`ws://${window.location.host}/ws/${sessionId}`);

socket.onmessage = (event) => {
  const message = JSON.parse(event.data);
  displayMessage(message.text, 'agent');
  setStatus('ready');
};

// Send message via WebSocket
function sendMessage(text) {
  socket.send(JSON.stringify({ text: text }));
  displayMessage(text, 'user');
  setStatus('thinking');
}
```

```python
# Server-side WebSocket handler
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    user_id = f"user_{session_id[:8]}"
    
    # Get or create agent session
    agent = session_manager.get_agent(user_id, session_id)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            message = data.get("text", "")
            
            # Process message with agent
            response = agent.process_message(user_id=user_id, message=message)
            
            # Send response back to client
            await websocket.send_json({"text": response})
    except WebSocketDisconnect:
        session_manager.note_disconnection(session_id)
```

## Memory Management

Agent instances are managed by the `SessionManager` which:
- Creates new agent instances for new sessions
- Reuses existing agent instances for returning users
- Handles agent memory and conversation state

```python
class SessionManager:
    def __init__(self):
        self.sessions = {}
        self.agent_cache = {}
        
    def get_agent(self, user_id: str, session_id: str) -> Agent:
        """Get or create an agent for the given session."""
        if session_id in self.agent_cache:
            return self.agent_cache[session_id]
            
        # Create new agent for this session
        from radbot.agent import create_agent
        agent = create_agent(name="web_agent")
        
        # Store in cache for reuse
        self.agent_cache[session_id] = agent
        return agent
```

## CLI vs Web Interface Differences

The implementation of RadBot's CLI and web interfaces differ in several key ways:

### Initialization Process

1. **CLI Interface**:
   - Custom initialization in `radbot/cli/main.py`
   - Manually creates and configures all components (Agent, Runner, SessionService, etc.)
   - Requires explicit handling of all parameters, including `app_name`
   - Runs in an async event loop managed by `asyncio.run(main())`

2. **Web Interface**:
   - Uses the ADK web server via `adk web` command
   - Agent initialization handled by ADK's web server
   - Parameters like `app_name` are automatically managed
   - Uses the root-level `agent.py` as the entry point

### Runner Initialization

The most critical difference is in how the `Runner` is initialized:

```python
# CLI Interface (explicit)
runner = Runner(
    agent=root_agent,
    app_name="radbot",  # Must be explicitly provided
    session_service=session_service,
    memory_service=memory_service
)

# Web Interface (handled by ADK)
# The ADK web server automatically creates the Runner with all required parameters
```

## Event Loop Handling

When using async tools such as the MCP integration, proper event loop management is critical:

```python
# Problem: Creates a new event loop inside an existing one
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
tools, exit_stack = loop.run_until_complete(_create_home_assistant_toolset_async())

# Solution: Check for existing event loop
try:
    existing_loop = asyncio.get_event_loop()
    if existing_loop.is_running():
        # Handle the case of a running loop
        return []
except RuntimeError:
    # No event loop exists, create a new one
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
```

## Security Considerations

The web implementations include several security considerations:

- CORS is configured to allow secure cross-origin requests
- Session IDs are generated using UUIDs for uniqueness
- Input validation is performed on all API endpoints
- Authentication handles for API keys are secured
- Error messages are sanitized to avoid leaking sensitive information

## Comparison of Web Interfaces

| Feature | ADK Web Server | Custom FastAPI Interface |
|---------|---------------|-------------------------|
| Setup Complexity | Simpler | More configuration required |
| Real-time Communication | Polling | WebSockets (faster) |
| UI Customization | Limited | Fully customizable |
| Session Management | Built-in | Custom implementation |
| Memory Management | Handled by ADK | Custom implementation |
| Tool Visualization | Limited | Enhanced |
| Mobile Responsiveness | Basic | Enhanced |
| Performance | Good | Very good |
| Development Effort | Lower | Higher |

## Future Enhancements

Potential improvements for the web interfaces:

1. **Authentication**: Add user authentication for persistent user profiles
2. **File Uploads**: Support for file uploads to interact with documents
3. **Tool Visualization**: Visual indicators for when tools are being used
4. **Streaming Responses**: Implement streaming for faster perceived response times
5. **More UI Controls**: Additional controls for agent configuration
6. **Dark Mode**: Add theme support with light/dark mode toggle
7. **Progressive Web App**: Make the interface installable as a PWA