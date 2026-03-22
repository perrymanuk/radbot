# Web

## Architecture

FastAPI backend (`radbot/web/`) + React SPA frontend (`radbot/web/frontend/`).

| Layer | Stack | Entry |
|-------|-------|-------|
| Backend | FastAPI, uvicorn | `python -m radbot.web` |
| Frontend | React 18, Vite 6, TypeScript, Tailwind | `make dev-frontend` (dev) / `make build-frontend` (prod) |
| State | Zustand | `stores/app-store.ts` |
| WS | native WebSocket + reconnect | `hooks/use-websocket.ts` |

## Session Modes

| Mode | Config | Behavior |
|------|--------|----------|
| `local` (default) | `config:agent` → `session_mode = "local"` | In-process `SessionRunner` with `InMemorySessionService` |
| `remote` | `config:agent` → `session_mode = "remote"` | `SessionProxy` spawns Nomad batch jobs, proxies via A2A |

### Local Mode

```
Browser ◄──WS──► FastAPI app.py ──► SessionRunner ──► ADK Runner ──► root_agent
```

- `SessionRunner` wraps ADK `Runner` + `InMemorySessionService`
- Session state lost on restart; last 15 messages replayed from DB
- `SessionManager` holds runners in `Dict[str, SessionRunner]`

### Remote Mode

```
Browser ◄──WS──► FastAPI app.py ──► SessionProxy ──A2A──► Nomad Worker Job
```

- `SessionProxy` same interface as `SessionRunner` (duck-typed `process_message()`)
- Worker holds full ADK state in memory as long as it runs
- Falls back to local `SessionRunner` if Nomad unreachable or worker limit hit
- See `specs/deployment.md` for worker lifecycle details

### Key Session Files

| File | Purpose |
|------|---------|
| `web/api/session/session_runner.py` | Local ADK runner, event processing, history loading |
| `web/api/session/session_proxy.py` | Remote proxy: Nomad lifecycle + A2A communication |
| `web/api/session/session_manager.py` | Runner registry, local/remote mode switching |
| `web/api/session/dependencies.py` | FastAPI dep: creates Runner or Proxy based on mode |
| `worker/history_loader.py` | Shared: loads chat DB history into ADK session |

## WebSocket Protocol

Endpoint: `GET /ws/{session_id}`

### Client → Server

```json
{"message": "user text"}           // chat message
{"type": "heartbeat"}               // keep-alive
{"type": "history_request", "limit": 50}  // request history
```

### Server → Client

```json
{"type": "status", "content": "ready"}      // ready for input
{"type": "status", "content": "thinking"}   // processing
{"type": "events", "content": [...]}        // agent events
{"type": "message", "content": "text"}      // final response
```

## API Routes

| Router | Prefix | Purpose |
|--------|--------|---------|
| `api/sessions.py` | `/api/sessions` | Session CRUD |
| `api/messages.py` | `/api/messages` | Chat message history |
| `api/admin.py` | `/admin/api` | Config, credentials, status |
| `api/tasks_api.py` | `/api/tasks` | Todo task CRUD |
| `api/scheduler_api.py` | `/api/scheduler` | Scheduled tasks |
| `api/reminders_api.py` | `/api/reminders` | Reminders |
| `api/webhooks_api.py` | `/api/webhooks` | Webhook definitions |
| `api/alerts_api.py` | `/api/alerts` | Alert events + policies |
| `api/terminal.py` | `/terminal` | Terminal PTY sessions |
| `api/tts.py` | `/api/tts` | Text-to-speech |
| `api/stt.py` | `/api/stt` | Speech-to-text |

## Frontend

Build: `make build-frontend` → `radbot/web/static/dist/`

Feature flag: if `static/dist/index.html` exists, FastAPI serves React SPA; otherwise legacy vanilla JS.

Key dirs: `components/`, `hooks/`, `stores/`, `pages/`, `lib/`
