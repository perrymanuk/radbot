# Session Workers

## Overview

Session workers run agent sessions as independent persistent Nomad service jobs. Each worker holds full ADK session state in memory and exposes an A2A (Agent-to-Agent) HTTP endpoint. The main radbot app acts as a gateway — the WebSocket handler delegates to a `SessionProxy` that manages worker lifecycle and proxies messages.

**Why**: `InMemorySessionService` loses all state on restart. Workers keep sessions alive as independent processes — surviving main app restarts, providing resource isolation, and enabling horizontal scaling. Primary use case is persistent Claude Code terminal environments.

**Design principle**: Workers are persistent session holders. They run the agent runtime (including Claude Code CLI) and hold state indefinitely. Workers restart on crash and run until explicitly stopped — there is no idle self-termination. The main app evolves independently — new features don't require restarting existing workers.

## Architecture

```
                    ┌──────────────────────────────────┐
                    │       Main radbot App             │
                    │   (Gateway / UI / Scheduler)      │
                    │                                   │
  Browser ◄──WS──► │  /ws/{session_id}                 │
                    │       │                           │
                    │  SessionManager                   │
                    │   mode=remote? ──► SessionProxy   │
                    │   mode=local?  ──► SessionRunner  │
                    │                        │          │
                    └────────────────────────┼──────────┘
                                             │ A2A HTTP
                              ┌──────────────▼──────────────┐
                              │    Nomad Batch Job           │
                              │  radbot-session-{id[:8]}     │
                              │                              │
                              │  python -m radbot.worker     │
                              │    --session-id <UUID>       │
                              │                              │
                              │  ┌─────────────────────┐     │
                              │  │ Starlette (to_a2a)  │     │
                              │  │  /.well-known/agent  │     │
                              │  │  /health             │     │
                              │  │  /info               │     │
                              │  └─────────┬───────────┘     │
                              │            │                 │
                              │  ┌─────────▼───────────┐     │
                              │  │ ADK Runner           │     │
                              │  │  InMemorySession     │     │
                              │  │  root_agent (beto)   │     │
                              │  │  all sub-agents      │     │
                              │  │  memory service      │     │
                              │  └─────────────────────┘     │
                              │                              │
                              │  ActivityWatchdog (tracking)  │
                              └──────────────────────────────┘
```

## Worker Process

### Entry Point: `radbot/worker/__main__.py`

```
python -m radbot.worker --session-id <UUID> [--host 0.0.0.0] [--port 8000]
```

Startup sequence:
1. Bootstrap logging, env vars, DB config (same as `radbot.web`)
2. Import `root_agent` from `radbot.agent.agent_core` (creates full agent tree)
3. Run `setup_before_agent_call()` (DB schema init)
4. Create `Runner` with `InMemorySessionService`, `InMemoryArtifactService`, memory service
5. Enable context caching (intervals=20, ttl=3600s, min_tokens=1024)
6. Call `to_a2a(root_agent, runner=runner)` → Starlette app with A2A routes
7. Add `ActivityMiddleware` (touches watchdog on every request)
8. Add `/health` and `/info` routes
9. On startup: start watchdog + seed session from chat DB history
10. Run with `uvicorn`

### A2A Protocol

Workers use Google ADK's built-in A2A support:

| Component | Role |
|-----------|------|
| `to_a2a()` | Converts `BaseAgent` into Starlette app with A2A JSON-RPC routes |
| `A2aAgentExecutor` | Wraps `Runner`, processes A2A messages → ADK events → A2A responses |
| `AgentCardBuilder` | Auto-generates `/.well-known/agent.json` from agent metadata |
| `a2a-sdk` | Protocol types, server framework, client library |

The A2A endpoint handles:
- Agent card discovery (`/.well-known/agent.json`)
- Message send (JSON-RPC `message/send`)
- Task management (submit, status, artifacts)

### Endpoints

| Path | Method | Purpose |
|------|--------|---------|
| `/health` | GET | Health check — returns `{status, session_id, idle_seconds, uptime_seconds}` |
| `/info` | GET | Metadata — returns `{session_id, agent_name, idle_seconds, uptime_seconds}` |
| `/.well-known/agent.json` | GET | A2A agent card (auto-generated) |
| `/` | POST | A2A JSON-RPC endpoint (message/send, tasks) |

### Idle Watchdog: `radbot/worker/idle_watchdog.py`

Two components:
- **`ActivityWatchdog`**: Tracks `last_activity` and `uptime_seconds` via `time.monotonic()`. Pure observability — no shutdown logic. Health and info endpoints report these values.
- **`ActivityMiddleware`**: Starlette middleware that calls `watchdog.touch()` on every HTTP request.

Workers are persistent — they do not self-terminate. Stop them explicitly via `NomadClient.stop_job()` or workspace deletion.

### History Seeding: `radbot/worker/history_loader.py`

On startup, the worker pre-loads chat history from PostgreSQL:
1. Query `chat_messages` table for the session (limit: `max_history * 2`, default 30)
2. Take last `max_history` messages (default 15)
3. Create ADK `Event` objects with user/assistant roles
4. Group user+assistant pairs under shared `invocation_id`
5. Append to session via `session_service.append_event()`

This function is shared between the worker and `SessionRunner` (web app).

## Gateway (Main App Side)

### SessionProxy: `radbot/web/api/session/session_proxy.py`

Duck-typed replacement for `SessionRunner` — same `process_message(message) → dict` interface.

#### Message Flow

```python
async def process_message(message, run_config=None) -> dict:
    worker_url = await self._ensure_worker()    # spawn if needed
    if not worker_url:
        return await self._fallback_local(...)  # degrade gracefully

    response_text = await self._send_a2a_message(worker_url, message)
    if response_text is None:
        return await self._fallback_local(...)  # A2A failed

    return {"response": response_text, "events": [], "source": "remote_worker"}
```

#### Worker Discovery

Priority order:
1. **Cached URL** — check health, use if still healthy
2. **Nomad service discovery** — `GET /v1/service/radbot-session`, filter by `session_id` tag
3. **DB fallback** — `session_workers` table lookup
4. **Spawn new** — submit Nomad service job, poll until healthy

#### Spawning

1. Check concurrency limit (`max_session_workers`, default 10)
2. Read bootstrap secrets from main app's env (`RADBOT_CREDENTIAL_KEY`, `RADBOT_ADMIN_TOKEN`) + DB config (`postgres_pass`)
3. Generate job spec via `nomad_template.build_worker_job_spec()`
4. Submit via `NomadClient.submit_job()`
5. Record in `session_workers` table (status=`starting`)
6. Poll Nomad service discovery until worker registers + passes health check (timeout: 120s)
7. Update DB record (status=`healthy`, `worker_url`)

#### A2A Client

Uses `a2a-sdk` directly (not `RemoteA2aAgent`):
1. Resolve agent card from `{worker_url}/.well-known/agent.json`
2. Create `A2AClientFactory` with `httpx.AsyncClient`
3. Build `A2AMessage` with user text
4. Send via `a2a_client.send_message()`, iterate response stream
5. Extract text from response parts

#### Fallback

Falls back to local `SessionRunner` when:
- Nomad client not configured
- Worker limit reached
- Worker fails to start within 120s
- A2A message fails
- Any unhandled exception

Fallback result includes `"source": "local_fallback"` for observability.

### SessionManager: `radbot/web/api/session/session_manager.py`

Extended with `mode` property (lazy-loaded from `config:agent` → `session_mode`):
- `"local"` (default): creates `SessionRunner`
- `"remote"`: creates `SessionProxy`

### Dependencies: `radbot/web/api/session/dependencies.py`

FastAPI dependency `get_or_create_runner_for_session()` checks `session_manager.mode` and creates the appropriate handler.

## Nomad Job Template: `radbot/worker/nomad_template.py`

Generates JSON job spec (Python dict) compatible with Nomad HTTP API.

```python
build_worker_job_spec(
    session_id="...",       # full UUID
    image_tag="v0.14",      # Docker tag
    credential_key="...",   # RADBOT_CREDENTIAL_KEY
    admin_token="...",      # RADBOT_ADMIN_TOKEN
    postgres_pass="...",    # DB password
    # Optional:
    cpu=500, memory=1024,
    dns_server=None, extra_env=None,
) -> {"Job": {...}}
```

Key properties:
- `type = "service"` — Nomad restarts on crash, runs until explicitly stopped
- `restart: attempts=1, mode=fail` — minimal retry, no restart loop
- Dynamic port on `host_network = "lan"`
- Service `radbot-session` with tag `session_id=<UUID>` for discovery
- Health check `GET /health` every 30s
- Config via Nomad template stanza (same pattern as main job)

## Worker DB: `radbot/worker/db.py`

Table: `session_workers`

| Column | Type | Purpose |
|--------|------|---------|
| `session_id` | UUID PK | Links to `chat_sessions` |
| `nomad_job_id` | TEXT | Nomad job ID (e.g. `radbot-session-550e8400`) |
| `worker_url` | TEXT | Discovered URL (e.g. `http://10.0.1.5:28432`) |
| `status` | TEXT | `starting` → `healthy` → `stopped` / `failed` |
| `created_at` | TIMESTAMPTZ | When job was submitted |
| `last_active_at` | TIMESTAMPTZ | Updated on each proxied message |
| `image_tag` | TEXT | Docker image tag at spawn time |
| `metadata` | JSONB | Extensible metadata |

Operations: `upsert_worker`, `get_worker`, `update_worker_status`, `touch_worker`, `list_active_workers`, `count_active_workers`, `delete_worker`.

## Nomad Service Discovery

Added to `NomadClient` (`radbot/tools/nomad/nomad_client.py`):

| Method | API | Purpose |
|--------|-----|---------|
| `list_services(name)` | `GET /v1/service/{name}` | All registrations for a service |
| `find_service_by_tag(name, tag)` | filters above | Find worker by `session_id=<UUID>` tag |

## Config

| Key | Location | Default | Purpose |
|-----|----------|---------|---------|
| `session_mode` | `config:agent` | `local` | `local` = in-process; `remote` = Nomad workers |
| `max_session_workers` | `config:agent` | `10` | Max concurrent worker jobs |
| `worker_image_tag` | `config:agent` or `RADBOT_WORKER_IMAGE_TAG` | `latest` | Docker tag for new workers |

## Sequence Diagrams

### New Session (Remote Mode)

```
Browser ──WS──► /ws/{session_id}
                  │
                  ▼
            SessionManager.get_runner() → None (new session)
            dependencies → SessionProxy(session_id)
                  │
                  ▼ process_message("hello")
            SessionProxy._ensure_worker()
              ├─ _discover_worker() → None
              └─ _spawn_worker()
                   ├─ count_active_workers() < limit
                   ├─ build_worker_job_spec()
                   ├─ NomadClient.submit_job()
                   ├─ upsert_worker(status="starting")
                   └─ _wait_for_healthy()
                        └─ poll find_service_by_tag() + /health
                             │
                             ▼ worker healthy
            SessionProxy._send_a2a_message(worker_url, "hello")
              ├─ resolve agent card
              ├─ A2AClient.send_message()
              └─ extract text response
                  │
                  ▼
            return {"response": "...", "source": "remote_worker"}
```

### Reconnect After Main App Restart

```
Browser ──WS──► /ws/{session_id}
                  │
                  ▼
            SessionProxy._ensure_worker()
              └─ _discover_worker()
                   └─ find_service_by_tag("session_id=xxx")
                        │
                        ▼ worker still running!
                   _check_health(url) → 200 OK
                  │
                  ▼
            SessionProxy._send_a2a_message()
              └─ Worker has FULL session state (in-memory, never lost)
                  No history reconstruction needed
```

### Worker Explicit Stop

```
Admin or workspace delete
      │
SessionProxy.stop_worker()
      └─ NomadClient.stop_job("radbot-session-{id}")
           └─ DELETE /v1/job/{id}
                │
                ▼
    Nomad deregisters job, kills allocation
    session_workers.status → "stopped"
```

### Worker Crash Recovery

```
Worker process crashes (OOM, unhandled exception)
      │
Nomad RestartPolicy (attempts=3, mode=delay)
      └─ Restart allocation after 15s delay
           └─ Worker boots, re-seeds from DB
                └─ Claude Code can --resume from saved session ID
```

## Testing

### Unit Tests: `tests/unit/test_worker_components.py`

| Class | Tests | Covers |
|-------|-------|--------|
| `TestNomadJobTemplate` | 13 | Job structure, args, env, service tags, resources, constraints, serialization |
| `TestActivityWatchdog` | 3 | Activity tracking, touch reset, uptime |
| `TestHistoryLoader` | 6 | DB loading, empty handling, max limit, invocation ID pairing |
| `TestSessionManagerMode` | 5 | Mode switching, runner registry |
| `TestSessionProxyUnit` | 7 | Health checks, fallback, concurrency limits, message routing |

### E2E Tests: `tests/e2e/test_session_worker.py`

| Class | Mark | Tests | Covers |
|-------|------|-------|--------|
| `TestSessionWorkerAPI` | `e2e` | 2 | Health endpoint, schema init |
| `TestNomadJobSubmission` | `requires_nomad` | 3 | Nomad connectivity, template validation |
| `TestSessionProxyFlow` | `requires_nomad` + `requires_gemini` | 3 | Full WS→proxy→worker→A2A→response, worker reuse |
| `TestSessionProxyFallback` | `e2e` | 2 | Local mode default, local sessions work |
| `TestWorkerDBTracking` | `e2e` | 6 | CRUD on session_workers table |
| `TestNomadServiceDiscovery` | `requires_nomad` | 2 | Service lookup edge cases |

## Files

| File | Purpose |
|------|---------|
| `radbot/worker/__init__.py` | Package |
| `radbot/worker/__main__.py` | Entry point: A2A + terminal routes, --workspace-id/--session-id |
| `radbot/worker/terminal_handler.py` | Shared PTY module: `TerminalManager`, `TerminalSession`, binary WS handler |
| `radbot/worker/idle_watchdog.py` | `ActivityWatchdog` + `ActivityMiddleware` |
| `radbot/worker/history_loader.py` | Shared: seed ADK session from chat DB |
| `radbot/worker/nomad_template.py` | `build_worker_job_spec()` + `build_workspace_worker_spec()` |
| `radbot/worker/db.py` | `session_workers` + `workspace_workers` tables |
| `radbot/web/api/terminal.py` | Terminal REST + WS proxy (local/remote mode) |
| `radbot/web/api/terminal_proxy.py` | `WorkspaceProxy`: workspace worker lifecycle |
| `radbot/web/api/session/session_proxy.py` | `SessionProxy`: chat session A2A proxy |
| `radbot/web/api/session/session_manager.py` | Mode switching (local/remote) |
| `radbot/web/api/session/dependencies.py` | FastAPI dep: Runner or Proxy based on mode |
| `radbot/tools/nomad/nomad_client.py` | `list_services()`, `find_service_by_tag()` |
