# Workers

## Overview

Workers are persistent Nomad service jobs spawned by the main radbot app for **terminal/workspace** sessions. Each worker runs a minimal PTY server — no ADK, no agent stack, no A2A — and serves the terminal over WebSocket. The main app acts as a gateway: `WorkspaceProxy` in `web/api/terminal_proxy.py` manages lifecycle and proxies WebSocket frames.

**Design shift (2026-03-22)**: the worker was originally designed to host the full ADK agent stack and proxy chat via A2A. That path was reverted in commit `393c173` (and the session-worker chat flow finally removed in `12e4901`) because:

- Keeping ADK state per session was expensive and rarely needed for chat
- `InMemorySessionService` already reseeds from chat DB on cold starts (good enough)
- Terminal (Claude Code CLI) is the real use case for per-session workers — it genuinely needs persistent state (the Claude Code session ID for `--resume`)

**Current state**: workers are persistent, lean PTY servers. Chat always runs in-process in the main app.

## Two Worker Flavors

Both share `radbot/worker/` and the `workspace_workers` / `session_workers` tables in PostgreSQL.

| Flavor | Spec builder | DB table | Active usage |
|--------|--------------|----------|--------------|
| Workspace worker (terminal) | `build_workspace_worker_spec()` | `workspace_workers` | Active — each cloned workspace gets one |
| Session worker (chat, legacy) | `build_worker_job_spec()` | `session_workers` | Not used for routing chat post-`12e4901`; code kept for potential revival |

Only the workspace worker is active in production flow.

## Architecture (Active — Workspace/Terminal)

```
                    ┌──────────────────────────────────┐
                    │       Main radbot App             │
                    │   (Gateway / UI / Scheduler)      │
                    │                                   │
  Browser ◄──WS──► │  /terminal/ws/{workspace_id}      │
                    │       │                           │
                    │  WorkspaceProxy                   │
                    │   mode=remote? spawn Nomad job    │
                    │   mode=local?  local PTY          │
                    └──────────────────────┼────────────┘
                                           │ WebSocket
                              ┌────────────▼─────────────┐
                              │   Nomad Service Job       │
                              │  radbot-workspace-{id[:8]}│
                              │                           │
                              │  python -m radbot.worker  │
                              │    --workspace-id <UUID>  │
                              │                           │
                              │  Starlette + uvicorn      │
                              │    /ws (PTY WebSocket)    │
                              │    /health, /info         │
                              │                           │
                              │  TerminalManager          │
                              │    PTY (Claude Code CLI)  │
                              └───────────────────────────┘
```

## Worker Process

### Entry Point — `radbot/worker/__main__.py`

```
python -m radbot.worker --workspace-id <UUID> [--host 0.0.0.0] [--port 8000]
```

Startup (minimal — no ADK):

1. `setup_logging()` + `load_dotenv()`
2. Schema init (workspace_workers, coder_workspaces) — called directly, NOT via ADK callback (`ec49f62`)
3. DB config load so GitHub App credentials are available for clones (`2694efa`)
4. Build Starlette app with routes:
   - `GET /health` — returns `{status, workspace_id, idle_seconds, uptime_seconds}`
   - `GET /info` — metadata
   - `WS /ws` — PTY terminal (delegated to `terminal_handler.handle_terminal_websocket`)
5. `ActivityMiddleware` touches a watchdog on every request
6. Add `ActivityWatchdog` for observability only (no idle-shutdown — `f988aca`)
7. Run with `uvicorn` (`uvicorn[standard]` for WebSocket support — `ab13a23`)

Workers use a `Starlette` lifespan context manager (`b9465ed`) and an empty `__init__.py` built into the Dockerfile (`5252d0c`) to avoid shared-app import fallout (`2e3efd3`, `db2a290`).

### Docker Image

- Separate from main app: `radbot-worker` built via `Dockerfile.worker`
- Multi-stage build with `uv` + GHA layer caching (`c20e8b2`, `c1cbdd8`)
- Python 3.14-slim base
- Shell ergonomics preinstalled (`485b83d`): `zsh`, `fzf`, `git-delta`, `jq`, `tree`, `bat`, `fd-find`, `less`
- Bundles Claude Code CLI

### Terminal Handler

`radbot/worker/terminal_handler.py` — shared module also used by `web/api/terminal.py` for local-mode.

- `TerminalManager` — per-workspace map of `TerminalSession`s
- `TerminalSession` — PTY subprocess (Claude Code CLI by default), `TERM=xterm-256color` (`e8b5b47`), scrollback buffer, multi-client fan-out
- **Binary WebSocket protocol** (`661ff39`) for PTY I/O — shorter frames, GPU canvas addon on the frontend
- **Multi-client** (`0442134`) — multiple browsers can share one PTY
- **Scrollback replay** on reconnect (`324611f`)
- **Session-ID persistence** (`1b3b29c`) — Claude Code's session ID is saved to `coder_workspaces.last_session_id` so the next spawn does `claude --resume`
- **Directory auto-recreate** (`6e38f25`) — if a workspace dir is missing after container restart, re-clone from GitHub App

### Idle Watchdog — `radbot/worker/idle_watchdog.py`

Two components, **observability only**:

- `ActivityWatchdog` — tracks `last_activity` + `uptime_seconds`
- `ActivityMiddleware` — calls `watchdog.touch()` on every HTTP/WS request

Workers do NOT self-terminate on idle (`f988aca`). Stop them explicitly via `NomadClient.stop_job()` or workspace deletion.

## Gateway Side (Main App)

### WorkspaceProxy — `radbot/web/api/terminal_proxy.py`

Duck-typed replacement for local PTY flow when `session_mode=remote`:

- Spawns Nomad service job on first terminal open
- Discovers existing worker via Nomad service catalog (`find_service_by_tag("workspace_id=<UUID>")`)
- Falls back to `session_workers` / `workspace_workers` DB rows, then DB config → Consul if needed (`2811156`)
- Proxies WebSocket frames 1:1 between browser and worker (`/ws`)
- Pre-spawns the worker on workspace *creation*, not just first open (`3e93b63`), to avoid cold-start on first click
- Guards against duplicate spawns with a lock (`08e59bf`) and a 120s startup timeout

### Terminal Router — `radbot/web/api/terminal.py`

- REST endpoints: list workspaces, clone, delete, workspace health
- `register_terminal_websocket(app)` wires the WS route — delegates to `WorkspaceProxy` when remote, or to the local `terminal_handler` when local
- Differentiates OAuth vs. API-key token injection for Claude Code PTY (`be55369`)
- Scrollable workspace tabs in header bar (`7548aa5`)
- Multiple workspaces per repo/branch supported (`dd9919e`)
- Onboarding bypass + trust prompts pre-answered (`76b86b0`)

## Nomad Job Templates — `radbot/worker/nomad_template.py`

Two builder functions (both return `{"Job": {...}}` for Nomad HTTP API):

| Function | Purpose |
|----------|---------|
| `build_worker_job_spec(session_id=..., ...)` | Legacy session worker (chat) — kept for potential future use |
| `build_workspace_worker_spec(workspace_id=..., ...)` | Active workspace worker (terminal) |

Shared properties:

- `type = "service"` — Nomad restarts on crash, runs until explicitly stopped
- `restart: attempts=1, mode=fail` — minimal retry, no restart loop
- Dynamic port on `host_network = "lan"`
- Service name with `workspace_id=<UUID>` or `session_id=<UUID>` tag for discovery
- Health check `GET /health` every 30s
- Config via Nomad template stanza mirrors main job's credential bootstrap

## Worker DB — `radbot/worker/db.py`

Two tables, same shape:

**`session_workers`** (legacy, not used for chat routing):

| Column | Type | Purpose |
|--------|------|---------|
| `session_id` | UUID PK | Links to `chat_sessions` |
| `nomad_job_id` | TEXT | e.g. `radbot-session-550e8400` |
| `worker_url` | TEXT | e.g. `http://10.0.1.5:28432` |
| `status` | TEXT | `starting` → `healthy` → `stopped` / `failed` |
| `created_at` | TIMESTAMPTZ | |
| `last_active_at` | TIMESTAMPTZ | |
| `image_tag` | TEXT | |
| `metadata` | JSONB | |

**`workspace_workers`** (active):

Same columns, keyed by `workspace_id` UUID PK.

Operations: `upsert_worker`, `get_worker`, `update_worker_status`, `touch_worker`, `list_active_workers`, `count_active_workers`, `delete_worker`.

## Nomad Service Discovery

Added to `NomadClient` (`radbot/tools/nomad/nomad_client.py`):

| Method | API | Purpose |
|--------|-----|---------|
| `list_services(name)` | `GET /v1/service/{name}` | All registrations for a service |
| `find_service_by_tag(name, tag)` | filter above | Find worker by `workspace_id=<UUID>` tag |

Consul remains as a fallback (`2811156`), but Nomad's native service discovery is the primary path (`ccfeeb3`).

## Config

| Key | Location | Default | Purpose |
|-----|----------|---------|---------|
| `session_mode` | `config:agent` | `local` | Terminal/workspace workers only — `local` = local PTY, `remote` = Nomad workers |
| `max_session_workers` | `config:agent` | `10` | Max concurrent worker jobs (shared budget) |
| `worker_image_tag` | `config:agent` or `RADBOT_WORKER_IMAGE_TAG` | `latest` | Docker tag for newly-spawned workers |

## Sequence Diagrams

### Open a terminal (remote mode, cold)

```
Browser ──WS──► /terminal/ws/{workspace_id}
                  │
                  ▼
            WorkspaceProxy._ensure_worker()
              ├─ _discover_worker() → None (first open)
              └─ _spawn_worker()
                   ├─ count_active_workers() < limit
                   ├─ build_workspace_worker_spec()
                   ├─ NomadClient.submit_job()
                   ├─ upsert_worker(status="starting")
                   └─ _wait_for_healthy()
                        └─ poll find_service_by_tag() + /health
                             │
                             ▼ worker healthy
            WorkspaceProxy bridges WS frames ──► worker /ws (PTY)
```

### Reconnect after main app restart

```
Browser ──WS──► /terminal/ws/{workspace_id}
                  │
                  ▼
            WorkspaceProxy._ensure_worker()
              └─ _discover_worker()
                   └─ find_service_by_tag("workspace_id=xxx")
                        │
                        ▼ worker still running
                   _check_health(url) → 200 OK
                  │
                  ▼
            Bridge WS frames — Claude Code can --resume from saved session ID
            Scrollback buffer replayed on WS reconnect
```

### Worker crash

```
PTY subprocess exits / allocation OOMs
      │
Nomad service job restart policy
      └─ Fresh allocation on same host (or rescheduled)
           └─ Worker boots, mounts workspace dir (auto-recreate if missing)
                └─ Terminal client reconnects, resumes Claude Code session
```

## Testing

### Unit Tests — `tests/unit/test_worker_components.py`

| Class | Tests | Covers |
|-------|-------|--------|
| `TestNomadJobTemplate` | Job structure, args, env, service tags, resources, constraints, serialization |
| `TestActivityWatchdog` | Activity tracking, touch reset, uptime |
| `TestHistoryLoader` | DB loading (legacy chat path), empty handling, invocation ID pairing |

### E2E Tests — `tests/e2e/test_session_worker.py` + `tests/e2e/test_terminal_worker.py`

- `TestSessionWorkerAPI` — `/health` endpoint, schema init
- `TestNomadJobSubmission` — Nomad connectivity, template validation (`requires_nomad`)
- `TestWorkerDBTracking` — CRUD on both worker tables
- `TestNomadServiceDiscovery` — Service lookup edge cases

## Files

| File | Purpose |
|------|---------|
| `radbot/worker/__init__.py` | Package marker |
| `radbot/worker/__main__.py` | Entry point — PTY server with /health, /info, /ws |
| `radbot/worker/terminal_handler.py` | Shared PTY module — `TerminalManager`, `TerminalSession`, binary WS handler |
| `radbot/worker/idle_watchdog.py` | `ActivityWatchdog` + `ActivityMiddleware` (observability only) |
| `radbot/worker/nomad_template.py` | `build_worker_job_spec()` + `build_workspace_worker_spec()` |
| `radbot/worker/db.py` | `session_workers` + `workspace_workers` CRUD |
| `radbot/worker/history_loader.py` | Shared: seed ADK session from chat DB (used by main-app chat, not workers) |
| `radbot/web/api/terminal.py` | Terminal REST + WS registration (local/remote mode) |
| `radbot/web/api/terminal_proxy.py` | `WorkspaceProxy` — workspace worker lifecycle + WS bridge |
| `radbot/web/api/session/session_manager.py` | Chat `SessionRunner` registry (always local) |
| `radbot/tools/nomad/nomad_client.py` | `list_services()`, `find_service_by_tag()` |
