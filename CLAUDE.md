# RadBot - Claude Code Instructions

RadBot is an AI agent framework built on Google ADK 1.24.1, PostgreSQL, Qdrant,
and MCP. The main agent "beto" has a 90s SoCal personality. Multi-agent architecture
with specialized sub-agents (casa, planner, tracker, comms, scout, axel, search, code execution).

**Package manager**: `uv` — always use `uv run` to execute Python commands.

---

## WARNING: Configuration Rules

**Do NOT add integration config to `config.yaml`.** Integration settings live in
the PostgreSQL credential store, managed via the Admin UI at `/admin/`.

### What config.yaml contains (ONLY these three things)

```yaml
database:          # PostgreSQL connection (host, port, user, password, db_name)
credential_key:    # Fernet encryption key for credential store
admin_token:       # Admin API bearer token
```

### Where each config type goes

| Config type | Storage location | Example |
|---|---|---|
| DB connection | `config.yaml` → `database:` | host, port, user, password |
| Encryption key | `config.yaml` → `credential_key` | Fernet key string |
| Admin token | `config.yaml` → `admin_token` | Bearer token string |
| Integration URLs, flags | DB as `config:<section>` | `config:integrations` → overseerr.url |
| API keys, tokens | DB encrypted in `radbot_credentials` | `overseerr_api_key` |
| Agent models | DB as `config:agent` | main_model, sub_model |

### Config priority (highest to lowest)

1. DB config (`config:<section>` entries merged by `config_loader.load_db_config()`)
2. File config (`config.yaml`)
3. Credential store (encrypted values by name)
4. Environment variables (`RADBOT_MAIN_MODEL`, `OVERSEERR_URL`, etc.)

### Integration client pattern (follow this for new integrations)

See `radbot/tools/overseerr/overseerr_client.py:30-58` — the canonical example:

```python
def _get_config() -> dict:
    # 1. Try config_loader (merged file+DB config)
    from radbot.config.config_loader import config_loader
    cfg = config_loader.get_integrations_config().get("overseerr", {})

    url = cfg.get("url") or os.environ.get("OVERSEERR_URL")
    api_key = cfg.get("api_key") or os.environ.get("OVERSEERR_API_KEY")

    # 2. Fall back to credential store for secrets
    if not api_key:
        from radbot.credentials.store import get_credential_store
        store = get_credential_store()
        api_key = store.get("overseerr_api_key")

    return {"url": url, "api_key": api_key, "enabled": cfg.get("enabled", True)}
```

### Hot-reload flow

Admin UI → `PUT /api/config/{section}` → `config_loader.load_db_config()` → client
`reset_*_client()` singleton reset → next tool call picks up new config.

### Key config files

| File | Purpose |
|---|---|
| `radbot/config/config_loader.py` | ConfigLoader with DB merge, `get_integrations_config()` |
| `radbot/credentials/store.py` | Encrypted credential store (PostgreSQL-backed) |
| `radbot/web/api/admin.py` | Admin API: save/test/status endpoints |
| `radbot/web/frontend/src/components/admin/panels/` | React admin panels |
| `radbot/web/frontend/src/pages/AdminPage.tsx` | Admin page (NAV_ITEMS + PANEL_MAP) |

---

## Project Structure

```
radbot/
├── agent/                        # Agent definitions and setup
│   ├── agent_core.py             # Root agent (beto) creation — orchestrator only
│   ├── agent_initializer.py      # Basic ADK imports and config
│   ├── agent_tools_setup.py      # Schema init callback, search/code/scout creation
│   ├── specialized_agent_factory.py  # Creates all domain agents (casa, planner, tracker, comms, axel)
│   ├── home_agent/               # Casa agent (Home Assistant + Overseerr)
│   ├── planner_agent/            # Planner agent (Calendar + Scheduler + Reminders)
│   ├── tracker_agent/            # Tracker agent (Todo + Webhooks)
│   ├── comms_agent/              # Comms agent (Gmail + Jira)
│   ├── execution_agent/          # Axel agent (shell + filesystem + MCP)
│   └── research_agent/           # Scout agent (research + sequential thinking)
├── tools/                        # All tool modules (see inventory below)
├── web/
│   ├── app.py                    # FastAPI app, startup, route registration
│   ├── __main__.py               # Entry: python -m radbot.web
│   ├── api/                      # REST routers (admin, tasks, scheduler, etc.)
│   ├── db/                       # Chat history DB (connection.py, chat_operations.py)
│   └── frontend/                 # React SPA (Vite + React 18 + TypeScript + Tailwind)
├── config/
│   ├── config_loader.py          # Config manager with DB merge
│   ├── schema/config_schema.json # JSON schema for config validation
│   └── default_configs/
│       ├── instructions/         # Agent instruction .md files
│       └── schemas/              # Agent config schemas
├── credentials/
│   └── store.py                  # Encrypted PostgreSQL credential store
├── memory/
│   └── enhanced_memory/          # Qdrant-backed semantic memory
├── callbacks/                    # ADK callback handlers
├── cache/                        # Response caching
├── cli/                          # CLI entry point
└── filesystem/                   # Filesystem utilities
```

---

## Sub-Agents

Beto is a **pure orchestrator** with only memory tools. All domain tools live on specialized sub-agents.
Beto routes requests via ADK's `transfer_to_agent` — no wrapper tools needed.

| Agent | Factory location | Tools | Purpose |
|---|---|---|---|
| **beto** (root) | `agent/agent_core.py` | 2 memory | Orchestrator, routes to specialists |
| **casa** | `agent/home_agent/factory.py` | 6 HA + 4 Overseerr + 2 memory | Smart home, media requests |
| **planner** | `agent/planner_agent/factory.py` | 1 time + 5 calendar + 3 scheduler + 3 reminder + 2 memory | Calendar, scheduling, reminders |
| **tracker** | `agent/tracker_agent/factory.py` | 8 todo + 3 webhook + 2 memory | Task/project management |
| **comms** | `agent/comms_agent/factory.py` | 4 gmail + 6 jira + 2 memory | Email, issue tracking |
| **scout** | `agent/research_agent/factory.py` | 2 memory | Technical research, design collab |
| **axel** | `agent/execution_agent/factory.py` | 11 exec + 4 fs + MCP + shell + 2 memory | Implementation, shell, files |
| **search_agent** | `tools/adk_builtin/search_tool.py` | 1 google_search | Google Search grounding |
| **code_execution_agent** | `tools/adk_builtin/code_execution_tool.py` | BuiltInCodeExecutor | Python code execution |

- `transfer_to_agent` is **auto-injected by ADK** — never register it manually (causes duplicate error)
- Agent instructions loaded from `config/default_configs/instructions/{agent_name}.md`
- Each sub-agent has **scoped memory** (`source_agent` tag in Qdrant) via `create_agent_memory_tools()`
- Sub-agents MUST call `transfer_to_agent(agent_name='beto')` when done to return control

---

## Tool Modules

| Module | Key files | Tool names | Purpose |
|---|---|---|---|
| `tools/basic/` | `basic_tools.py`, `weather_connector.py` | `get_current_time`, `get_weather` | Time and weather |
| `tools/memory/` | `memory_tools.py`, `agent_memory_factory.py` | `search_past_conversations`, `store_important_information`, `create_agent_memory_tools()` | Qdrant semantic memory (global + per-agent scoped) |
| `tools/todo/` | `db_tools.py`, `todo_tools.py`, `db/` | `add_task_tool`, `complete_task_tool`, `list_all_tasks_tool`, +5 more | Task/project management |
| `tools/calendar/` | `calendar_tools.py`, `calendar_manager.py` | `list_calendar_events_tool`, `create_calendar_event_tool`, +3 more | Google Calendar CRUD |
| `tools/gmail/` | `gmail_tools.py`, `gmail_manager.py` | `list_emails_tool`, `search_emails_tool`, `get_email_tool`, `list_gmail_accounts_tool` | Gmail read-only |
| `tools/homeassistant/` | `ha_tools_impl.py`, `ha_rest_client.py` | `list_ha_entities`, `get_ha_entity_state`, `turn_on/off/toggle_ha_entity`, `search_ha_entities` | Home Assistant REST |
| `tools/scheduler/` | `schedule_tools.py`, `db.py`, `engine.py` | `create_scheduled_task_tool`, `list_scheduled_tasks_tool`, `delete_scheduled_task_tool` | APScheduler cron tasks |
| `tools/reminders/` | `reminder_tools.py`, `db.py` | `create_reminder_tool`, `list_reminders_tool`, `delete_reminder_tool` | One-shot reminders |
| `tools/webhooks/` | `webhook_tools.py`, `db.py`, `template_renderer.py` | `create_webhook_tool`, `list_webhooks_tool`, `delete_webhook_tool` | External POST webhooks |
| `tools/overseerr/` | `overseerr_tools.py`, `overseerr_client.py` | `search_overseerr_media_tool`, `request_overseerr_media_tool`, +2 more | Media requests |
| `tools/jira/` | `jira_tools.py`, `jira_client.py` | `list_my_jira_issues_tool`, `get_jira_issue_tool`, `transition_jira_issue_tool`, +3 more | Jira Cloud |
| `tools/shell/` | `shell_tool.py`, `shell_command.py` | `shell_command_tool` (via `get_shell_tool()`) | Shell execution |
| `tools/adk_builtin/` | `search_tool.py`, `code_execution_tool.py` | Agent factories (not direct tools) | ADK search + code exec agents |
| `tools/mcp/` | `mcp_tools.py`, `dynamic_tools_loader.py` | `create_fileserver_toolset()`, `load_dynamic_mcp_tools()` | MCP server integration |
| `tools/ntfy/` | `ntfy_client.py` | `NtfyClient` class (async push notifications) | ntfy.sh push notifications |
| `tools/ollama/` | `ollama_client.py` | `OllamaClient` class (admin model management) | Ollama local LLM server |
| `tools/tts/` | `tts_service.py` | `TTSService` class (REST only, no FunctionTool) | Google Cloud TTS |
| `tools/stt/` | `stt_service.py` | `STTService` class (REST only, no FunctionTool) | Google Cloud STT |
| `tools/specialized/` | `base_toolset.py`, 11 toolset files | `create_specialized_toolset()` | Domain toolsets for sub-agents |
| `tools/shared/` | `db_schema.py`, `errors.py`, `validation.py` | Utilities (no FunctionTools) | Shared helpers |

---

## Database Tables

All tables use the shared pool from `radbot/tools/todo/db/connection.py` unless noted.

| Table | Module | Key columns |
|---|---|---|
| `tasks` | `tools/todo/db/schema.py` | `task_id` (UUID), `project_id`, `title`, `status` (backlog/inprogress/done), `related_info` (JSONB) |
| `projects` | `tools/todo/db/schema.py` | `project_id` (UUID), `name` (UNIQUE) |
| `scheduled_tasks` | `tools/scheduler/db.py` | `task_id` (UUID), `name`, `cron_expression`, `prompt`, `enabled`, `metadata` (JSONB) |
| `reminders` | `tools/reminders/db.py` | `reminder_id` (UUID), `message`, `remind_at` (TIMESTAMPTZ), `status`, `delivered` |
| `webhook_definitions` | `tools/webhooks/db.py` | `webhook_id` (UUID), `name` (UNIQUE), `path_suffix` (UNIQUE), `prompt_template`, `secret` |
| `scheduler_pending_results` | `tools/scheduler/db.py` | `result_id` (UUID), `task_name`, `prompt`, `response`, `session_id`, `delivered` |
| `radbot_credentials` | `credentials/store.py` | `name` (PK), `encrypted_value`, `salt`, `credential_type` |
| `chat_messages` | `web/db/chat_operations.py` | `message_id` (UUID), `session_id`, `role`, `content`, `agent_name`, `metadata` (JSONB) |
| `chat_sessions` | `web/db/chat_operations.py` | `session_id` (UUID), `name`, `user_id`, `preview`, `is_active` |

Chat tables use a **separate** DB (`radbot_chathistory` schema) with its own pool in `web/db/connection.py`.

---

## Running

| Command | Description |
|---|---|
| `uv run python -m radbot.web` / `make run-web` | Start FastAPI web server |
| `uv run python -m radbot` / `make run-cli` | Start CLI interface |
| `make dev-frontend` | Vite dev server at :5173 (proxies to FastAPI :8000) |
| `make build-frontend` | Build React SPA → `radbot/web/static/dist/` |
| `make test` / `make test-unit` | Run all tests / unit tests only |
| `make lint` | Lint with ruff |
| `make format` | Format with ruff |

---

## Production Deployment

- **Endpoint**: `https://radbot.demonsafe.com`
- **Nomad job**: `~/git/perrymanuk/hashi-homelab/nomad_jobs/ai-ml/radbot/nomad.job`
- **Docker image**: `ghcr.io/perrymanuk/radbot` — auto-built by `.github/workflows/docker-build.yml` on push to `main`
- **Versioning**: Auto-incremented `v{MAJOR}.{BUILD}` tags (e.g. `v0.3`). Update the `image` tag in the Nomad job after pushing.
- **Reverse proxy**: Traefik (via Consul service discovery). `ProxyHeadersMiddleware` handles `X-Forwarded-Proto`.
- **Bootstrap config**: Nomad templates a minimal `config.yaml` with only `database:` section. All other config is loaded from the DB credential store at startup.
- **Bootstrap env vars**: `RADBOT_CREDENTIAL_KEY`, `RADBOT_ADMIN_TOKEN`, `RADBOT_CONFIG_FILE=/app/config.yaml`

### Reverse proxy gotchas

FastAPI behind Traefik generates redirect URLs using the internal HTTP scheme unless `ProxyHeadersMiddleware` is active. Frontend API calls to router root paths (e.g. `/api/sessions` → 307 to `/api/sessions/`) will fail if the redirect uses `http://` on an HTTPS site. **Always use trailing slashes** in frontend fetch calls that hit router root paths, or define routes without relying on the trailing-slash redirect.

---

## Adding New Modules

### New tool module

1. Create `radbot/tools/<module>/` with `__init__.py`, `db.py`, `<module>_tools.py`
2. Add tools to the appropriate **domain agent factory** (e.g., `radbot/agent/home_agent/factory.py`)
3. Add `init_<module>_schema()` call in `setup_before_agent_call()` in `agent_tools_setup.py`
4. If REST API needed: create `radbot/web/api/<module>.py` router, register in `app.py`
5. Add schema init to `initialize_app_startup()` in `app.py`
6. **Store all integration config in DB credential store** — NOT in `config.yaml`
7. **Do NOT add tools to `agent_initializer.py` or `agent_core.py`** — beto is a pure orchestrator

### New domain agent

1. Create `radbot/agent/<domain>_agent/` with `__init__.py` and `factory.py`
2. Follow pattern from `radbot/agent/home_agent/factory.py`
3. Add `create_agent_memory_tools("<domain>")` for scoped memory
4. Create instruction file: `radbot/config/default_configs/instructions/<domain>.md`
5. Import and add factory call in `radbot/agent/specialized_agent_factory.py`
6. Add agent to routing table in `instructions/main_agent.md`

### New Admin UI integration

1. Add test endpoint in `radbot/web/api/admin.py` (`/api/test/<service>`)
2. Add status check in `get_integration_status()` in `admin.py`
3. Add panel in `radbot/web/frontend/src/components/admin/panels/ConnectionPanels.tsx`
4. Register panel in `AdminPage.tsx` (NAV_ITEMS + PANEL_MAP)
5. Add client reset hook in `save_config_section()` for hot-reload
6. Follow the integration client pattern from `overseerr_client.py` (see above)
7. **Config goes to DB** — the admin UI `PUT /api/config/{section}` stores it there

---

## Common Patterns

- **Lazy imports**: Use inside functions to avoid circular deps and import-time crashes
- **DB connections**: Reuse pool from `radbot.tools.todo.db.connection` (call `get_db_pool()`)
- **Schema init**: Idempotent `init_*_schema()` with `CREATE TABLE IF NOT EXISTS`
- **Singleton clients**: `_client` module-level + `get_client()`/`reset_client()` (see `overseerr_client.py`)
- **Agent tools**: Wrap plain functions as `FunctionTool` from `google.adk.tools`
- **Error returns**: Agent tools return `{"status": "success/error", ...}` dicts
- **Config access**: `config_loader.get_integrations_config().get("<service>", {})`
- **Credential access**: `get_credential_store().get("<key_name>")`
- **Model resolution**: Always use `config_manager.resolve_model(model_string)` in agent factories — wraps Ollama models (`ollama_chat/...`) in `LiteLlm`, passes Gemini strings through unchanged

---

## Known Gotchas

- **google-genai 1.62.0** is installed — NOT `google-generativeai` (different package/API)
- **BuiltInCodeExecutor**: Use `code_executor=BuiltInCodeExecutor()` on Agent, not as a tool
- **ADK async**: `InMemorySessionService.get_session/create_session` are async — must be awaited
- **Runner.run_async()** for async contexts; `Runner.run()` blocks the event loop
- **Memory service**: Access via `tool_context._invocation_context.memory_service` (not `tool_context.memory_service`)
- **Embedding model**: `gemini-embedding-001` with `output_dimensionality=768`
- **User ID**: Single-user system, all sessions use `user_id="web_user"`
- **transfer_to_agent duplication**: ADK auto-injects it; adding manually causes "Duplicate function" error
- **Config schema drift**: Specialized agent schemas use `additionalProperties: true` to avoid breakage
- **Makefile**: Must use `uv run python` — bare `python3` won't use the venv
- **`RADBOT_ENV`**: Set to `dev` to load `config.dev.yaml` instead of `config.yaml`. Each search directory tries `config.{env}.yaml` first. See `docs/implementation/dev_environment_setup.md`.
- **`RADBOT_CONFIG_FILE`**: Alias for `RADBOT_CONFIG` — both are supported. Nomad sets `RADBOT_CONFIG_FILE`.
- **Trailing-slash redirects**: FastAPI router root paths (`@router.get("/")`) redirect without trailing slash via 307. Behind a reverse proxy this can produce `http://` redirect URLs that browsers block as mixed content. Always use trailing slashes in frontend API calls to router root paths.
- **Ollama models**: Use `ollama_chat/<model>` prefix (e.g. `ollama_chat/mistral-small3.2`). `search_agent` (google_search) and `code_execution_agent` (BuiltInCodeExecutor) require Gemini and will NOT work with Ollama.

---

## Pre-Commit Checklist

Before every commit, review and update these if the changes affect them:

1. **README.md** — Feature descriptions, project structure, tech stack
2. **docs/implementation/** — Add or update implementation docs for new features
3. **CLAUDE.md** — Update if new conventions, patterns, or architecture decisions
4. **config_schema.json** — Update if new config sections (`radbot/config/schema/`)
