# Integrations

## Architecture

All integrations follow a common pattern:

1. **Config loading**: `config_loader.get_integrations_config().get("<service>", {})` (merged file+DB config)
2. **Credential fallback**: `get_credential_store().get("<key>")` for secrets
3. **Env var fallback**: `os.environ.get("SERVICE_KEY")` as last resort
4. **Singleton client**: Module-level `_client` + `get_client()` / `reset_client()`
5. **Hot-reload**: Admin UI save → `reset_*_client()` → next call picks up new config

Canonical example: `radbot/tools/overseerr/overseerr_client.py:30-58`

## Integration Matrix

| Service | Client Class | Connection | Config Keys | Admin Panel | Test Endpoint |
|---------|-------------|------------|-------------|-------------|---------------|
| Home Assistant | `HomeAssistantRESTClient` | HTTP REST + WebSocket | `integrations.home_assistant.url`, credential: `ha_token` | ConnectionPanels | `/api/test/home-assistant` |
| Overseerr | `OverseerrClient` | HTTP REST | `integrations.overseerr.url`, credential: `overseerr_api_key` | ConnectionPanels | `/api/test/overseerr` |
| Picnic | `PicnicClientWrapper` | HTTP REST (python_picnic_api2) | credential: `picnic_username`, `picnic_password`, `picnic_country_code` | MediaPanels | `/api/test/picnic` |
| Jira | `atlassian.Jira` | HTTP REST (atlassian lib) | `integrations.jira.url`, `jira.email`, credential: `jira_api_token` | ConnectionPanels | `/api/test/jira` |
| Gmail | `GmailManager` | Google API (OAuth) | credential: `gmail_token_<account>` (JSON) | SecurityPanels | `/api/test/gmail` |
| Google Calendar | `CalendarManager` | Google API (SA/OAuth) | credential: `calendar_token` (JSON) | SecurityPanels | `/api/test/calendar` |
| ntfy | `NtfyClient` | async HTTP (httpx) | `integrations.ntfy.url`, `ntfy.topic`, credential: `ntfy_token` | NotificationPanels | `/api/test/ntfy` |
| GitHub | `GitHubAppClient` | HTTP REST (JWT auth) | `integrations.github.app_id`, `github.installation_id`, credential: `github_app_private_key` | DeveloperPanels | `/api/test/github` |
| Nomad | `NomadClient` | async HTTP (httpx) | `integrations.nomad.addr`, credential: `nomad_token` | InfrastructurePanels | `/api/test/nomad` |
| Claude Code | subprocess CLI | subprocess | credential: `claude_code_oauth_token` | DeveloperPanels | `/api/test/claude-code` |
| Google API | — | — | credential store (API key) | CorePanels | `/api/test/google` |
| Qdrant | `QdrantMemoryService` | gRPC | `qdrant.host`, `qdrant.port` | CorePanels | `/api/test/qdrant` |
| TTS | `TTSService` | HTTP REST (urllib) | Google API key | — | — |
| STT | `STTService` | HTTP REST (urllib) | Google API key | — | — |
| MCP Servers | stdio subprocess | stdio | Dynamic config | MCPPanel | — |

## Integration Details

### Home Assistant

- **Client**: `tools/homeassistant/ha_rest_client.py` — `HomeAssistantRESTClient`
- **WebSocket**: `tools/homeassistant/ha_websocket_client.py` — async WS at `wss://host/api/websocket`
- **Auth**: Long-lived access token in `Authorization: Bearer` header
- **Config**: `HA_URL`, `HA_TOKEN` env vars or DB config
- **Singletons**: Separate for REST (`ha_client_singleton.py`) and WS (`ha_ws_singleton.py`)
- **Health check**: `GET /api/` → expects "API running." message
- **Dashboard CRUD**: WebSocket only (Lovelace API not available via REST)

### Overseerr

- **Client**: `tools/overseerr/overseerr_client.py` — `OverseerrClient`
- **Auth**: API key in `X-Api-Key` header
- **Config**: `OVERSEERR_URL`, `OVERSEERR_API_KEY` env vars or DB config
- **Health check**: `GET /api/v1/status` → returns version info
- **Methods**: `search()`, `get_movie()`, `get_tv()`, `create_request()`, `list_requests()`

### Picnic

- **Client**: `tools/picnic/picnic_client.py` — `PicnicClientWrapper` (wraps `python_picnic_api2.PicnicAPI`)
- **Auth**: Username/password → cached auth token in credential store (`picnic_auth_token`)
- **Config**: `PICNIC_USERNAME`, `PICNIC_PASSWORD` env vars or DB config
- **Country code**: `picnic_country_code` (default "DE")
- **Health check**: `get_cart()` during initialization

### Jira

- **Client**: `tools/jira/jira_client.py` — uses `atlassian.Jira` library directly
- **Auth**: Email + API token (Jira Cloud basic auth)
- **Config**: `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` env vars or DB config
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
- **Auth**: Optional bearer token in `Authorization` header
- **Config**: `NTFY_URL` (default `https://ntfy.sh`), `NTFY_TOPIC`, `NTFY_TOKEN`
- **Subscriber**: `ntfy_subscriber.py` — SSE listener for incoming notifications
- **Priorities**: min, low, default, high, max
- **Health check**: Sends test notification

### GitHub App

- **Client**: `tools/github/github_app_client.py` — `GitHubAppClient`
- **Auth**: JWT (10 min TTL) → installation token (1 hour TTL, cached)
- **Config**: `GITHUB_APP_ID`, `GITHUB_INSTALLATION_ID`, credential: `github_app_private_key` (PEM)
- **Git operations**: subprocess with token in URL auth
- **Methods**: `clone_repo()`, `push_changes()`

### Nomad

- **Client**: `tools/nomad/nomad_client.py` — `NomadClient` (async httpx, 15s timeout)
- **Auth**: Optional `X-Nomad-Token` header (ACL token)
- **Config**: `NOMAD_ADDR`, `NOMAD_TOKEN`, `NOMAD_NAMESPACE` (default "default")
- **Query params**: Auto-include namespace on all requests

### Claude Code

- **Client**: `tools/claude_code/claude_code_client.py` — subprocess wrapper (not a traditional client)
- **Auth types**:
  - API key (`sk-ant-*`) → `ANTHROPIC_API_KEY` env var
  - OAuth token → written to `~/.claude/remote/.oauth_token`
- **Credential**: `claude_code_oauth_token` in credential store
- **Onboarding**: Writes `hasCompletedOnboarding` + trust dialog settings before each run
- **Modes**: plan (`--print`, read-only), execute (`--print --output-format stream-json`)

### TTS (Text-to-Speech)

- **Service**: `tools/tts/tts_service.py` — `TTSService`
- **Auth**: Google API key (same as Gemini)
- **API**: `https://texttospeech.googleapis.com/v1/text:synthesize` (v1beta1 for Chirp3-HD voices)
- **Cache**: In-memory LRU
- **Output**: MP3 bytes
- **Singleton**: `create_instance()` / `get_instance()`

### STT (Speech-to-Text)

- **Service**: `tools/stt/stt_service.py` — `STTService`
- **Auth**: Google API key (same as Gemini)
- **API**: `https://speech.googleapis.com/v1/speech:recognize`
- **Input**: WEBM/Opus at 48000 Hz (browser MediaRecorder format)
- **Model**: `latest_long`
- **Singleton**: `create_instance()` / `get_instance()`

### MCP Servers

- **Location**: `tools/mcp/mcp_tools.py` (re-export hub)
- **Clients**: `context7_client.py`, `mcp_fileserver_client.py`, `mcp_stdio_client.py`
- **Connection**: stdio subprocess
- **Tools**: Dynamically loaded, variable count

## Admin UI Panels

| Panel File | Integrations |
|-----------|--------------|
| `CorePanels.tsx` | Google API key, Qdrant |
| `ConnectionPanels.tsx` | Home Assistant, Jira, Overseerr |
| `SecurityPanels.tsx` | Gmail (OAuth), Google Calendar (OAuth) |
| `NotificationPanels.tsx` | ntfy |
| `MediaPanels.tsx` | Picnic |
| `DeveloperPanels.tsx` | GitHub App, Claude Code |
| `InfrastructurePanels.tsx` | Nomad |
| `MCPPanel.tsx` | MCP servers |

Location: `radbot/web/frontend/src/components/admin/panels/`

## Hot-Reload

When the admin UI saves config via `PUT /api/config/{section}`, all singleton clients are reset:

```python
# admin.py — save_config_section()
if section == "integrations":
    reset_overseerr_client()
    reset_ha_client()
    reset_ha_ws_client()
    reset_ntfy_client()
    reset_picnic_client()
    reset_github_client()
    reset_nomad_client()
```

Next tool call on any agent triggers re-initialization with fresh config from DB.

## Key Files

| File | Purpose |
|------|---------|
| `tools/{service}/{service}_client.py` | Integration client implementation |
| `tools/{service}/{service}_tools.py` | FunctionTool wrappers |
| `config/config_loader.py` | `get_integrations_config()` — merged file+DB config |
| `credentials/store.py` | Encrypted credential store |
| `web/api/admin.py` | Test endpoints, hot-reload, status aggregation |
| `web/frontend/src/components/admin/panels/` | React admin panels |
