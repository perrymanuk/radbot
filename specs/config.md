# Config

## Priority (highest → lowest)

1. DB config (`config:<section>` entries merged by `config_loader.load_db_config()`)
2. File config (`config.yaml` / `config.dev.yaml`)
3. Credential store (encrypted values by name)
4. Environment variables (`RADBOT_MAIN_MODEL`, `OVERSEERR_URL`, etc.)

## config.yaml (bootstrap only)

```yaml
database:          # PostgreSQL connection (host, port, user, password, db_name)
credential_key:    # Fernet encryption key for credential store
admin_token:       # Admin API bearer token
```

**Do NOT add integration config to `config.yaml`.** Everything else goes in DB-backed config sections or the credential store, managed via Admin UI at `/admin/`.

## Env Var Bootstrap

| Env var | Purpose |
|---------|---------|
| `RADBOT_CREDENTIAL_KEY` | Fernet key for encrypted credentials in DB |
| `RADBOT_ADMIN_TOKEN` | Bearer token for `/admin/` API |
| `RADBOT_MCP_TOKEN` | Bootstrap bearer token for the MCP bridge HTTP transport. Credential-store entry `mcp_token` wins over this; rotating from the admin UI leaves the env var untouched but irrelevant |
| `RADBOT_WIKI_PATH` | Filesystem root for the ai-intel wiki that `mcp_server.tools.wiki` operates on (default `/mnt/ai-intel`; Nomad bind-mounts `${var.shared_dir}ai-intel` here) |
| `RADBOT_CONFIG_FILE` | Path to `config.yaml` (alias: `RADBOT_CONFIG`, default: auto-discovered) |
| `RADBOT_ENV` | `dev` → loads `config.dev.yaml` before `config.yaml` in each search directory |
| `RADBOT_MAIN_MODEL` / `RADBOT_SUB_MODEL` | Model overrides (if no DB/file entry exists) |
| `RADBOT_NAMING_MODEL` | Model override for the session auto-naming service (`radbot/services/session_naming.py`). Takes precedence over `config:agent.agent_models.naming_model`; falls back to `main_model` when neither is set |
| `RADBOT_WORKER_IMAGE_TAG` | Overrides `config:agent.worker_image_tag` for new workers |
| `LOG_LEVEL` | Controls log verbosity at runtime (default `INFO`) |

## DB Config Sections

Stored as `config:<section>` entries in `radbot_credentials` (`credential_type='config'`).

| Section | Keys | Purpose |
|---------|------|---------|
| `config:agent` | `main_model`, `sub_model`, per-agent models (`casa_agent`, `planner_agent`, `comms_agent`, `axel_agent`/`axel_agent_model`, `scout_agent`, `kidsvid_agent`), `naming_model` (cheap model for `radbot/services/session_naming.py`; env override `RADBOT_NAMING_MODEL`; falls back to `main_model`), `session_mode`, `max_workspace_workers` (legacy alias `max_session_workers` auto-mapped at load with deprecation warning), `worker_image_tag`, `terse_protocol_enabled` (bool; env override `RADBOT_TERSE_PROTOCOL_ENABLED`; default false), `thinking_enabled` (bool; default false; gates Gemini Chain-of-Thought streaming via `ThinkingConfig(include_thoughts=True)` for models matching family prefixes in `radbot/config/adk_config.py:THINKING_CAPABLE_MODELS` — currently `gemini-2.5-`, `gemini-3-`, `gemini-3.0-`, `gemini-3.1-`, `gemini-4-`, `gemini-4.0-`) | Agent model selection + session/worker config + terse-protocol feature flag + CoT toggle |
| `config:integrations` | `home_assistant.*`, `overseerr.*`, `lidarr.*`, `picnic.*`, `jira.*`, `ntfy.*`, `github.*`, `nomad.*`, `kideo.*`, `alertmanager.*`, `ollama.*` | Integration endpoints, flags, non-secret keys |
| `config:vector_db` | `url`, `api_key`, `host`, `port`, `collection` | Qdrant connection + collection |
| `config:scheduler` | `enabled` | Scheduler engine toggle |
| `config:webhooks` | `enabled` | Webhook engine toggle |
| `config:tts` | `enabled`, `voice`, `language_code` | TTS settings |
| `config:stt` | `enabled`, `language_code` | STT settings |
| `config:logging` | `level`, `structured` | Logging overrides |
| `config:mcp_servers` | list of `{name, command, args, env}` | Dynamic MCP server definitions (axel) |
| `config:cost_tracking` | `enabled`, rate cards | Telemetry + cost calc settings |

Use `config:full` as an Admin-UI read-only diagnostic that returns the merged config tree.

## Session Mode Config

| Key | Values | Default | Effect |
|-----|--------|---------|--------|
| `session_mode` | `local`, `remote` | `local` | **Terminal/workspace workers only** (chat is always local post-2026-03-23). `remote` spawns Nomad service jobs for each terminal workspace. |
| `max_workspace_workers` | integer | `10` | Max concurrent workspace worker jobs |
| `max_session_workers` | integer | — | **Deprecated** — automatically aliased to `max_workspace_workers` at config load (warning emitted). Old key left in DB for rollback safety; new code reads `max_workspace_workers`. |
| `worker_image_tag` | string | `latest` | Docker tag for newly-spawned workers |

**Note**: the `session_mode` name predates the terminal-only split. It now only affects terminal/workspace workers.

## Per-Agent Model Resolution

Each agent factory calls `resolve_agent_model(key)` (`radbot/agent/shared.py`) which:

1. Checks `config:agent.<key>` (e.g. `casa_agent`) — DB first
2. Falls back to `config:agent.sub_model`
3. Falls back to env var (`RADBOT_SUB_MODEL`)

Model strings are passed to ADK unchanged (no `LiteLlm` wrapping layer exists today). `search_agent` and `code_execution_agent` require Gemini.

## Integration Client Pattern

Follow this for new integrations:

```python
from radbot.tools.shared.config_helper import get_integration_config

def _get_config() -> dict:
    return get_integration_config(
        "overseerr",
        fields={"url": "OVERSEERR_URL", "api_key": "OVERSEERR_API_KEY"},
        credential_keys={"api_key": "overseerr_api_key"},
    )
```

This resolves config → env vars → credential store automatically.

For new integrations also:

1. Add test endpoint in `web/api/admin.py` (`/admin/api/test/<service>`)
2. Add status check in `get_integration_status()` in `admin.py`
3. Add panel in `web/frontend/src/components/admin/panels/...`
4. Register panel in `pages/AdminPage.tsx` (NAV_ITEMS + PANEL_MAP)
5. Add `(name, module_path, "reset_X_client")` to `ClientProvider.clear()` in `clients/provider.py` for hot-reload
6. Update `config_schema.json` if new `config:<section>` keys are introduced

## Hot-Reload Flow

```
Admin UI edits section / credential
   ↓
PUT /admin/api/config/{section}  |  POST /admin/api/credentials
   ↓
config_loader.load_db_config()   — merges DB overrides into in-memory config
   ↓
config/runtime.py:apply_runtime_config(section=…, credential=…)   — run in a worker thread
   ↓
next tool / LLM call             — sees fresh state
```

`apply_runtime_config()` is also what `web/app.py` startup calls once the assembly is built — one code path for boot and hot-reload. Steps, in order, each fail-soft (status dict returned in the API response under `reload`):

| Step | What it re-derives | Runs on |
|---|---|---|
| `genai_env` | `setup_vertex_environment()` → `GOOGLE_API_KEY` / Vertex env / `GOOGLE_CLOUD_PROJECT` | every save |
| `agent_models` | `config_manager.apply_model_config()` on the live agent tree | every save |
| `logging` | root logger level from `logging.level` | every save |
| `integration_clients` | `ClientProvider.clear()` + Gmail / Calendar service caches | every save |
| `filesystem` | `reload_filesystem_config()` | every save |
| `ha_tools` | `home_agent.factory.refresh_home_assistant_tools()` — rebuilds casa's HA (MCP or REST) tools in place | `integrations` section, `ha_token` |
| `mcp_tools` | `execution_agent.factory.refresh_axel_mcp_tools()` — stops cached MCP clients, reloads axel's dynamic tools | `integrations` section, `mcp_*` credentials |
| `media_services` | `TTSService` / `STTService` singletons recreated from `tts` / `stt` | every save |
| `memory_service` | `initialize_memory_service()` re-attached to every root agent | `vector_db` section, `qdrant_api_key` |

ntfy subscriber restart stays in `admin.py` (async, needs the request loop) and fires on `integrations` saves.

Needs a restart regardless: `web.host` / `web.port` / `web.debug` (uvicorn bind), `database:` (bootstrap pool, not editable from admin).

## Environment Separation (Dev)

Setting `RADBOT_ENV=dev`:

- Loads `config.dev.yaml` before `config.yaml` in each search directory
- Recommended: separate PostgreSQL DB (`radbot_dev`), Qdrant collection (`radbot_dev`)
- Use `scripts/migrate_credentials_to_dev.py` (one-off) to copy prod credentials into a dev key-space
- Startup banner logs env, config path, database, Qdrant collection — check logs to verify env

See `docs/implementation/dev_environment_setup.md` for full procedure.

## Key Files

| File | Purpose |
|------|---------|
| `config/config_loader.py` | `ConfigLoader` with DB merge, `get_integrations_config()` |
| `config/schema/config_schema.json` | JSON schema for validation (uses `additionalProperties: true` for agent schemas to tolerate drift) |
| `config/default_configs/instructions/*.md` | Per-agent instruction files |
| `config/default_configs/schemas/*` | Per-agent config sub-schemas |
| `credentials/store.py` | Encrypted credential store (PostgreSQL-backed) |
| `web/api/admin.py` | Admin API: save/test/status endpoints, reset registry |
