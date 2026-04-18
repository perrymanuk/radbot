# Integrations

## Architecture

All integrations follow a common pattern:

1. **Config loading**: `config_loader.get_integrations_config().get("<service>", {})` (merged file+DB config)
2. **Credential fallback**: `get_credential_store().get("<key>")` for secrets
3. **Env var fallback**: `os.environ.get("SERVICE_KEY")` as last resort
4. **Singleton client**: Module-level `_client` + `get_client()` / `reset_client()`
5. **Hot-reload**: Admin UI save → `reset_*_client()` → next call picks up new config

Canonical example: `radbot/tools/overseerr/overseerr_client.py`. Prefer `get_integration_config()` from `tools/shared/config_helper.py` for new clients.

## Integration Matrix

| Service | Client Class | Connection | Config Keys | Admin Panel | Test Endpoint |
|---------|-------------|------------|-------------|-------------|---------------|
| Home Assistant | `HAMcpClient` (primary) + `HomeAssistantRESTClient` (fallback) + WS client | MCP streamable-HTTP + HTTP REST + WebSocket | `integrations.home_assistant.url`, `integrations.home_assistant.use_mcp` (default true), credential: `ha_token` | `HomeAssistantPanel` | `/admin/api/test/home-assistant` (probes REST + MCP) |
| Overseerr | `OverseerrClient` | HTTP REST | `integrations.overseerr.url`, credential: `overseerr_api_key` | `OverseerrPanel` | `/admin/api/test/overseerr` |
| Lidarr | `LidarrClient` | HTTP REST | `integrations.lidarr.url`, credential: `lidarr_api_key` | `LidarrPanel` | `/admin/api/test/lidarr` |
| Picnic | `PicnicClientWrapper` | HTTP REST (python_picnic_api2) | credentials: `picnic_username`, `picnic_password`, `picnic_country_code`, `picnic_auth_token` (cached) | `PicnicPanel` | `/admin/api/test/picnic` |
| Jira | `atlassian.Jira` | HTTP REST (atlassian lib) | `integrations.jira.url`, `jira.email`, credential: `jira_api_token` | `JiraPanel` | `/admin/api/test/jira` |
| Gmail | `GmailManager` | Google API (OAuth) | credential: `gmail_token_<account>` (JSON) | `GmailPanel` | `/admin/api/test/gmail` |
| Google Calendar | `CalendarManager` | Google API (SA/OAuth) | credential: `calendar_token` (JSON) | `CalendarPanel` | `/admin/api/test/calendar` |
| ntfy | `NtfyClient` + `NtfySubscriber` | async HTTP (httpx) + SSE | `integrations.ntfy.url`, `ntfy.topic`, credential: `ntfy_token` | `NtfyPanel` | `/admin/api/test/ntfy` |
| GitHub App | `GitHubAppClient` | HTTP REST (JWT auth) | `integrations.github.app_id`, `github.installation_id`, credential: `github_app_private_key` | `GitHubAppPanel` | `/admin/api/test/github` |
| Nomad | `NomadClient` | async HTTP (httpx) | `integrations.nomad.addr`, credential: `nomad_token` | `NomadPanel` | `/admin/api/test/nomad` |
| Alertmanager | (pipeline — no client) | Inbound webhook | `integrations.alertmanager.*` | `AlertmanagerPanel` | — |
| Claude Code | subprocess CLI | subprocess | credential: `claude_code_oauth_token` | `ClaudeCodePanel` | `/admin/api/test/claude-code` |
| Google API | — | — | credential store (API key) | `GooglePanel` | `/admin/api/test/google` |
| Qdrant | `QdrantMemoryService` | gRPC/HTTP | `vector_db.host`, `vector_db.port`, `vector_db.collection`, `vector_db.url`, `vector_db.api_key` | `QdrantPanel` | `/admin/api/test/qdrant` |
| PostgreSQL | shared pool | libpq | `database.*` in `config.yaml` | `PostgresqlPanel` | `/admin/api/test/postgres` |
| TTS | `TTSService` | HTTP REST (urllib) | Google API key | `TTSPanel` | — |
| STT | `STTService` | HTTP REST (urllib) | Google API key | `STTPanel` | — |
| Ollama | `OllamaClient` | HTTP REST | `integrations.ollama.base_url` | (integrated into model pickers) | — |
| YouTube Data API | `YouTubeClient` | HTTP REST | credential: `youtube_api_key` | `YouTubePanel` | `/admin/api/test/youtube` |
| CuriosityStream | `CuriosityStreamClient` | HTTP REST | credential: `curiositystream_api_key` | (in `YouTubePanel` or separate) | — |
| Kideo | `KideoClient` | HTTP REST | `integrations.kideo.*` | `KideoPanel` | `/admin/api/test/kideo` |
| MCP Servers | stdio subprocess | stdio | Dynamic config in `config:mcp_servers` | `MCPServersPanel` | — |

## Integration Details

### Home Assistant

- **MCP client (primary tool surface)**: `tools/homeassistant/ha_mcp_client.py` — `HAMcpClient`, stateless streamable-HTTP against `POST <ha_url>/api/mcp`. Discovery via `list_tools_sync()` at factory time; invocation via async `call_tool(name, arguments)`. Singleton via `get_ha_mcp_client()` / `reset_ha_mcp_client()`. FunctionTool adapter: `tools/homeassistant/ha_mcp_tools.py` → `build_ha_mcp_function_tools(client)` wraps each MCP tool as an ADK FunctionTool, sanitizes names to valid identifiers, and unwraps HA's `{"success": bool, "result": ...}` envelope before returning to the LLM. Tool set includes ~19 built-in Assist intents (`HassTurnOn`, `HassTurnOff`, `HassLightSet`, `HassClimateSetTemperature`, `HassMediaSearchAndPlay`, `HassSetVolume`, `HassVacuumStart`, `HassFanSetSpeed`, `HassBroadcast`, `HassStartTimer`, `GetLiveContext`, `GetDateTime`, ...) plus every user-exposed HA script.
- **REST client (fallback + direct web endpoints)**: `tools/homeassistant/ha_rest_client.py` — `HomeAssistantRESTClient`. Used by `web/api/ha.py` for frontend device buttons; loaded onto casa only when `integrations.home_assistant.use_mcp = false` or MCP discovery fails at startup.
- **WebSocket**: `tools/homeassistant/ha_websocket_client.py` — async WS at `wss://host/api/websocket`. Used for dashboard (Lovelace) CRUD and — planned — entity/area/floor registry alias management (see `docs/plans/ha_alias_learning.md`).
- **State cache**: `tools/homeassistant/ha_state_cache.py` — legacy in-memory snapshot for the REST-based `search_ha_entities`. Unused when MCP path is active (MCP's `GetLiveContext` returns only Assist-exposed entities on demand).
- **Auth**: Long-lived access token in `Authorization: Bearer` header for all three transports (REST, MCP streamable-HTTP, WS).
- **Singletons**: Separate for REST (`ha_client_singleton.py`), WS (`ha_ws_singleton.py`), and MCP (`ha_mcp_client.py`). All three reset together on admin config change via `_INTEGRATION_RESET_REGISTRY`.
- **Health check**: `GET /api/` → expects "API running." message. The `/admin/api/test/home-assistant` endpoint probes REST + MCP `tools/list` and reports tool count.
- **Dashboard CRUD**: WebSocket only (Lovelace API not available via REST or MCP).
- **Direct REST endpoints**: `web/api/ha.py` exposes `GET /api/ha/state/{entity_id}` + `POST /api/ha/service` for frontend device buttons (bypasses agent).
- **HA-side prerequisite**: the `mcp_server` core integration must be enabled in HA (2025.2+). Tool availability is gated by Assist entity exposure (Settings → Voice assistants → Expose).

### Overseerr

- **Client**: `tools/overseerr/overseerr_client.py` — `OverseerrClient`
- **Auth**: API key in `X-Api-Key` header
- **Health check**: `GET /api/v1/status` → returns version info
- **Methods**: `search()`, `get_movie()`, `get_tv()`, `create_request()`, `list_requests()`
- **TMDB poster helper**: `tmdb_poster_url()` — used by Casa's `show_media_card` and by `web/api/media.py`
- **Direct REST**: `web/api/media.py` wraps Overseerr for `/api/media/search`, `/api/media/{tmdb_id}`, `/api/media/request` — no agent LLM call needed for the quick-action frontend buttons

### Lidarr (new 2026-03-23)

- **Client**: `tools/lidarr/lidarr_client.py` — `LidarrClient`
- **Auth**: API key in `X-Api-Key` header
- **Config**: `integrations.lidarr.url`, credential `lidarr_api_key`
- **Methods**: `search_artist()`, `search_album()`, `add_artist()`, `add_album()`, `list_quality_profiles()`
- **Wired on**: Casa agent

### Picnic

- **Client**: `tools/picnic/picnic_client.py` — `PicnicClientWrapper` (wraps `python_picnic_api2.PicnicAPI`)
- **Auth**: Username/password → cached auth token in credential store (`picnic_auth_token`)
- **Country code**: `picnic_country_code` (default `"DE"`)
- **Health check**: `get_cart()` during initialization

### Jira

- **Client**: `tools/jira/jira_client.py` — uses `atlassian.Jira` library directly
- **Auth**: Email + API token (Jira Cloud basic auth)
- **Health check**: `myself()` → verifies auth + returns display name

### Gmail

- **Client**: `tools/gmail/gmail_manager.py` — `GmailManager`
- **Auth**: OAuth 2.0 (per-account tokens)
- **Token storage**: `gmail_token_<account_label>` in credential store (JSON)
- **File fallback**: `~/.config/radbot/gmail_tokens/<account>.json`
- **Multi-account**: Default + named accounts, cached by label in `_gmail_managers` dict
- **OAuth flow**: `GET /admin/api/credentials/gmail/setup?account=<label>` → callback → store token
- **Read-only**: No send/compose tools

### Google Calendar

- **Client**: `tools/calendar/calendar_manager.py` — `CalendarManager`
- **Auth**: Service account (file or env JSON) OR OAuth token
- **Workspace**: Supports domain-wide delegation via impersonation
- **OAuth flow**: `GET /admin/api/credentials/calendar/setup` → callback → `calendar_token` in credential store
- **Health check**: `calendars().get(calendarId='primary')`

### ntfy

- **Client**: `tools/ntfy/ntfy_client.py` — `NtfyClient` (async httpx, 10s timeout)
- **Subscriber**: `tools/ntfy/ntfy_subscriber.py` — SSE listener for inbound notifications; writes to the `notifications` table
- **Auth**: Optional bearer token in `Authorization` header
- **Config**: `NTFY_URL` (default `https://ntfy.sh`), `NTFY_TOPIC`, `NTFY_TOKEN`
- **Priorities**: min, low, default, high, max
- **Health check**: Sends test notification

### GitHub App

- **Client**: `tools/github/github_app_client.py` — `GitHubAppClient`
- **Auth**: JWT (10 min TTL) → installation token (1 hour TTL, cached)
- **Git operations**: subprocess with token in URL auth
- **Methods**: `clone_repo()`, `push_changes()`
- **Worker usage**: Workspace workers load DB config on startup to reach GitHub credentials (fix in commit `2694efa`)

### Nomad

- **Client**: `tools/nomad/nomad_client.py` — `NomadClient` (async httpx, 15s timeout)
- **Auth**: Optional `X-Nomad-Token` header (ACL token)
- **Service discovery**: `list_services(name)`, `find_service_by_tag(name, tag)` — used for worker discovery by `WorkspaceProxy`. Switched from Consul → Nomad service discovery in commit `ccfeeb3`, with Consul fallback in `2811156`.
- **Query params**: Auto-include namespace on all requests (default `"default"`)

### Alertmanager

- **Pipeline**: `tools/alertmanager/processor.py` — `process_alert_from_payload()`
- **ntfy bridge**: `tools/alertmanager/ntfy_handler.py` — relays alerts to ntfy
- **Inbound endpoint**: `POST /api/alerts/webhook`
- **Remediation**: auto-applies policies from `alert_remediation_policies` (action, max_auto_remediations, window_minutes, enabled). Axel is consulted for complex remediations.

### Claude Code

- **Client**: `tools/claude_code/claude_code_client.py` — subprocess wrapper
- **Auth types**:
  - API key (`sk-ant-*`) → `ANTHROPIC_API_KEY` env var
  - OAuth token → written to `~/.claude/remote/.oauth_token`
- **Credential**: `claude_code_oauth_token` in credential store
- **Onboarding**: Writes `hasCompletedOnboarding` + trust dialog settings before each run (bypasses interactive prompts, see commit `76b86b0`)
- **Session persistence**: Last session ID stored on `coder_workspaces.last_session_id` so `--resume` works across container restarts (`1b3b29c`)
- **Modes**: plan (`--print`, read-only), execute (`--print --output-format stream-json`)

### YouTube / CuriosityStream / Kideo (new 2026-04-12)

- **YouTube Data API**: `tools/youtube/youtube_client.py`
- **CuriosityStream**: `tools/youtube/curiositystream_client.py`
- **Kideo (internal video library)**: `tools/youtube/kideo_client.py`
- **Tag generation**: `tools/youtube/tag_generator.py` — uses transcript + description via Gemini for AI tagging
- **Shorts filter**: Rejects YouTube Shorts at search/ingest time (`5051c45`)
- **Wired on**: `kidsvid` agent

### TTS (Text-to-Speech)

- **Service**: `tools/tts/tts_service.py` — `TTSService`
- **Auth**: Google API key (same as Gemini)
- **API**: `https://texttospeech.googleapis.com/v1/text:synthesize` (v1beta1 for Chirp3-HD voices)
- **Cache**: In-memory LRU
- **Output**: MP3 bytes

### STT (Speech-to-Text)

- **Service**: `tools/stt/stt_service.py` — `STTService`
- **Auth**: Google API key (same as Gemini)
- **API**: `https://speech.googleapis.com/v1/speech:recognize`
- **Input**: WEBM/Opus at 48000 Hz (browser MediaRecorder format)
- **Model**: `latest_long`

### MCP Servers

- **Location**: `tools/mcp/mcp_tools.py` (re-export hub), `tools/mcp/dynamic_tools_loader.py`
- **Connection**: stdio subprocess
- **Config**: `config:mcp_servers` DB entry (list of `{name, command, args, env}`)
- **Tools**: Dynamically loaded, variable count — attached to axel only

### Ollama (local LLM)

- **Client**: `tools/ollama/ollama_client.py` — `OllamaClient` (admin model management)
- **Models**: Prefix `ollama_chat/<model>` (e.g. `ollama_chat/mistral-small3.2`) — wrapped in `LiteLlm` by `config_manager.resolve_model()`
- **Limitations**: `search_agent` (google_search) and `code_execution_agent` (BuiltInCodeExecutor) require Gemini — will NOT work with Ollama

## Admin UI Panels

See `specs/web.md` § Admin Panel Modules for the full flat list. Location: `radbot/web/frontend/src/components/admin/panels/`. Registered in `pages/AdminPage.tsx` via `NAV_ITEMS` + `PANEL_MAP`.

## Hot-Reload Registry

When the admin UI saves config via `PUT /admin/api/config/{section}`, `_INTEGRATION_RESET_REGISTRY` in `web/api/admin.py` is consulted to reset affected singleton clients:

```
reset_overseerr_client, reset_lidarr_client, reset_ha_client, reset_ha_ws_client,
reset_ntfy_client, reset_picnic_client, reset_github_client, reset_nomad_client,
reset_jira_client, reset_kideo_client, reset_youtube_client, ...
```

Next tool call on any agent triggers re-initialization with fresh config from DB.

## Key Files

| File | Purpose |
|------|---------|
| `tools/{service}/{service}_client.py` | Integration client implementation |
| `tools/{service}/{service}_tools.py` | FunctionTool wrappers |
| `tools/shared/config_helper.py` | `get_integration_config()` resolver (preferred) |
| `tools/shared/client_utils.py` | `client_or_error()` singleton helper |
| `config/config_loader.py` | `get_integrations_config()` — merged file+DB config |
| `credentials/store.py` | Encrypted credential store |
| `web/api/admin.py` | Test endpoints, hot-reload registry, status aggregation |
| `web/api/media.py` + `web/api/ha.py` | Direct-action REST endpoints (bypass agent) |
| `web/frontend/src/components/admin/panels/` | React admin panels |
