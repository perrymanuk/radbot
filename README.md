# RadBot: Personal AI Agent
(Beto)

An AI agent built on Google ADK with a unique '90s SoCal personality. Beto blends practical functionality with a laid-back, knowledgeable persona. It manages smart home devices via Home Assistant, schedules recurring tasks, handles voice interactions, retains context from past conversations, and provides a mobile-friendly web interface — all while occasionally dropping '90s tech references.

<p align="center">
  <img src="img/radbot.png" alt="RadBot">
</p>

## Features

### Multi-Agent Architecture

RadBot uses specialized sub-agents with focused toolsets, reducing token usage and improving response quality:

*   **Beto** (root agent): General conversation, Home Assistant control, task management, calendar, memory
*   **Search Agent**: Web search with focused query handling
*   **Scout Agent**: Technical research across web, docs, and code repos with sequential thinking
*   **Axel Agent**: Code implementation with a dynamic worker system that distributes tasks across specialized agents for parallel execution
*   **Code Execution Agent**: Secure Python code execution via Google ADK's built-in sandbox

### Web Interface

React SPA with a terminal-inspired, i3-style tiling layout. Built with React 18, TypeScript, Vite, Tailwind CSS, and Zustand.

*   **Mobile-responsive**: Full-screen panel overlays on mobile, proper touch targets (44px minimum), dvh viewport units for correct mobile address bar handling
*   **Real-time**: WebSocket connection with heartbeat, reconnection, and message history sync
*   **Panels**: Chat, Sessions, Tasks, and Events panels in a side-by-side split (desktop) or overlay (mobile)
*   **Input features**: Slash commands (`/tasks`, `/clear`, `/help`), emoji autocomplete, command suggestions, input history (arrow keys)
*   **Memory mode**: Prefix with `#` to save text directly to long-term memory

### Scheduler

APScheduler-based cron engine for recurring tasks, persisted in PostgreSQL.

*   **`create_scheduled_task`**: Create cron-scheduled tasks with natural language (e.g., "every weekday at 9am")
*   **`list_scheduled_tasks`**: View all scheduled tasks with next run times
*   **`delete_scheduled_task`**: Remove a scheduled task
*   Task results are processed through the agent and broadcast to all connected WebSocket clients

### Reminders

One-shot reminders that fire at a specific date/time, persisted in PostgreSQL with offline delivery support.

*   **`create_reminder`**: Set a reminder with an absolute time (`remind_at`) or relative delay (`delay_minutes`)
*   **`list_reminders`**: View reminders filtered by status (pending/completed/cancelled/all)
*   **`delete_reminder`**: Cancel and remove a reminder
*   Reminders fire as system message notifications broadcast to all connected WebSocket clients
*   Offline delivery: reminders that fire while disconnected are delivered on WebSocket reconnect
*   REST API at `/api/reminders`

### Push Notifications (ntfy)

Push notifications via [ntfy.sh](https://ntfy.sh) for scheduled task results and reminders.

*   Sends notifications even when no browser tab is open
*   Works with Android (ntfy app), Linux desktop (ntfy CLI / notify-send), and any ntfy subscriber
*   Scheduled tasks now always execute (no longer skipped when offline); results are queued for WebSocket delivery on reconnect
*   Configurable server URL, topic, access token, priority, and click-through URL
*   Admin UI panel for configuration and test notifications

### Webhooks

External POST triggers with template rendering.

*   **`create_webhook`**: Create endpoints that trigger agent actions when called externally
*   **`list_webhooks`**: View registered webhooks
*   **`delete_webhook`**: Remove a webhook
*   Supports `{{payload.key}}` template variables for dynamic message content

### Text-to-Speech (TTS)

Google Cloud TTS integration with in-browser playback.

*   Per-message play button on assistant responses
*   Auto-play toggle (TTS:ON/OFF in header)
*   REST API at `/api/tts/synthesize`

### Speech-to-Text (STT)

Google Cloud STT integration with push-to-talk microphone input.

*   MIC button in chat input (push-to-talk)
*   Transcribed text injected into the input field for review before sending
*   REST API at `/api/stt/transcribe`

### Home Assistant Control

*   **`search_ha_entities`**: Find entities by name or area
*   **`list_ha_entities`**: List all connected devices and sensors
*   **`get_ha_entity_state`**: Check current state or sensor readings
*   **`turn_on_ha_entity`** / **`turn_off_ha_entity`** / **`toggle_ha_entity`**: Control devices

### Task Management

PostgreSQL-backed todo system with projects and status tracking.

*   **`add_task`**: Create tasks in project lists
*   **`complete_task`** / **`remove_task`** / **`update_task`**: Manage task lifecycle
*   **`list_projects`** / **`list_project_tasks`** / **`list_all_tasks`**: Browse tasks sorted by status (In Progress > Backlog > Done)
*   **`update_project`**: Rename projects

### Calendar Management (Google Calendar)

Supports OAuth and service account authentication.

*   **`list_calendar_events_wrapper`**: View upcoming events
*   **`create_calendar_event_wrapper`**: Create events
*   **`update_calendar_event_wrapper`** / **`delete_calendar_event_wrapper`**: Modify or remove events
*   **`check_calendar_availability_wrapper`**: Check free/busy times

### Memory System

Three-tier semantic memory backed by Qdrant vector database:

*   **Raw conversation history**: Full chat logs searchable by content
*   **Memories**: Automatically extracted key information from conversations
*   **Facts**: User-stored important information via `#` prefix or `store_important_information`
*   **`search_past_conversations`**: Semantic search across past interactions

### Web & Search Tools

*   **`web_search`**: General web search
*   **`call_search_agent`**: Focused web search via search agent

### File System & Shell

*   **File tools**: `list_files`, `read_file`, `write_file`, `edit_file_func`, `copy_file`, `move_file`, `delete_file`, `get_file_info`
*   **`execute_shell_command`**: **(Advanced)** Arbitrary shell command execution with security controls

### General Utilities

*   **`get_current_time`**: Current time for any city (defaults to UTC)
*   **`get_weather`**: Weather reports by city

### Configuration

Credentials and settings stored in an encrypted PostgreSQL credential store with an admin UI at `/admin`.

*   **Admin panel**: Web-based configuration editor for all settings (API keys, model preferences, tool enablement, integrations)
*   Per-agent model configuration
*   Prompt caching for reduced token usage

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/perrymanuk/radbot.git
   cd radbot
   ```

2. Set up your environment:
   ```
   make setup
   ```

3. Configure the application via the admin UI at `/admin`, or:
   ```
   cp config.yaml.example config.yaml
   # Edit config.yaml with your API keys and settings
   ```

## Usage

Run the web interface:
```
# Optional: Set the root directory for filesystem access
export MCP_FS_ROOT_DIR=/path/to/accessible/directory

# Run the web interface (FastAPI on port 8000)
make run-web
```

Run the CLI:
```
make run-cli
```

### Frontend Development

```
# Start Vite dev server (port 5173, proxies to FastAPI on 8000)
make dev-frontend

# Build for production (outputs to radbot/web/static/dist/)
make build-frontend
```

The Vite dev server binds to all interfaces (`host: true`) for mobile testing on the same network.

## Development

- Run tests: `make test`
- Run unit tests only: `make test-unit`
- Run integration tests only: `make test-integration`
- Run a specific test: `pytest tests/path/to/test_file.py::TestClass::test_method`
- Format code: `make format`
- Lint code: `make lint`

## Project Structure

- `/radbot/agent`: Core agent logic, initializer, and persona definitions
- `/radbot/tools`: Tool implementations (HA, calendar, tasks, scheduler, reminders, webhooks, ntfy, TTS, STT, shell, search)
- `/radbot/memory`: Qdrant-backed semantic memory system
- `/radbot/web`: FastAPI server, WebSocket handler, React frontend
- `/radbot/web/frontend`: React SPA source (Vite + TypeScript + Tailwind)
- `/radbot/config`: Configuration schema and credential store
- `/radbot/cli`: Command-line interface
- `/docs/implementation`: Detailed implementation documentation
- `/tests`: Unit and integration tests

## Tech Stack

- **Agent framework**: Google ADK 1.21.0
- **LLM**: Google Gemini or Ollama local models (configurable per agent via `resolve_model()`)
- **Backend**: FastAPI, WebSockets, APScheduler
- **Frontend**: React 18, Vite 6, TypeScript, Tailwind CSS, Zustand
- **Database**: PostgreSQL (tasks, scheduler, webhooks, credentials)
- **Vector store**: Qdrant (semantic memory)
- **Voice**: Google Cloud TTS / STT
- **Package manager**: uv

## Documentation

See the `docs/implementation` directory for detailed documentation on each feature, including core architecture, component guides, and specialized agent documentation.

## License

MIT
