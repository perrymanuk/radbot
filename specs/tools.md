# Tools

## Architecture

All agent tools are `google.adk.tools.FunctionTool` wrappers around plain Python functions. Tools return `{"status": "success/error", ...}` dicts. Each tool module exports an `ALL_TOOLS` or named list (e.g., `HA_DASHBOARD_TOOLS`, `SCHEDULER_TOOLS`, `CARD_TOOLS`) for registration in agent factories.

Non-tool services (TTS, STT, ntfy) expose REST endpoints only — they are not registered as agent FunctionTools. A new class of **card-rendering tools** exists: they return pre-formatted ` ```radbot:<kind> ` fenced JSON blocks that the agent includes verbatim in its reply, which the frontend parses into UI components.

## Tool Inventory

| Module | Count | Agent | Tool Names |
|--------|-------|-------|------------|
| `tools/basic/` | 1 | planner | `get_current_time` |
| `tools/memory/` | 2/agent | all | `search_agent_memory`, `store_agent_memory` (scoped per agent) |
| `tools/todo/` | 8 | tracker | `add_task`, `complete_task`, `remove_task`, `list_projects`, `list_project_tasks`, `list_all_tasks`, `update_task`, `update_project` |
| `tools/calendar/` | 5 | planner | `list_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event`, `check_calendar_availability` |
| `tools/gmail/` | 4 | comms | `list_emails`, `search_emails`, `get_email`, `list_gmail_accounts` |
| `tools/homeassistant/` (MCP, primary) | dynamic (~19 built-in + user-exposed scripts) | casa | `HassTurnOn`, `HassTurnOff`, `HassLightSet`, `HassClimateSetTemperature`, `HassMediaSearchAndPlay`, `HassSetVolume`, `HassVacuumStart`, `HassFanSetSpeed`, `HassBroadcast`, `HassStartTimer`, `GetLiveContext`, `GetDateTime`, … (schemas discovered at factory time from `<ha_url>/api/mcp` via `HAMcpClient.list_tools_sync()`, wrapped by `ha_mcp_tools.build_ha_mcp_function_tools`). Disable by setting `integrations.home_assistant.use_mcp = false` to fall back to the REST row below. |
| `tools/homeassistant/` (REST, fallback) | 6 | casa (only when MCP disabled/unavailable) | `list_ha_entities`, `get_ha_entity_state`, `turn_on_ha_entity`, `turn_off_ha_entity`, `toggle_ha_entity`, `search_ha_entities` |
| `tools/homeassistant/` (Dashboard WS) | 6 | casa | `list_ha_dashboards`, `get_ha_dashboard_config`, `create_ha_dashboard`, `update_ha_dashboard`, `delete_ha_dashboard`, `save_ha_dashboard_config` |
| `tools/scheduler/` | 3 | planner | `create_scheduled_task`, `list_scheduled_tasks`, `delete_scheduled_task` |
| `tools/reminders/` | 3 | planner | `create_reminder`, `list_reminders`, `delete_reminder` |
| `tools/telos/` | 18 | beto | `telos_get_section`, `telos_get_entry`, `telos_get_full`, `telos_search_journal`, `telos_add_journal`, `telos_add_prediction`, `telos_resolve_prediction`, `telos_note_wrong`, `telos_note_taste`, `telos_add_wisdom`, `telos_add_idea`, `telos_upsert_identity`, `telos_add_entry`, `telos_update_entry`, `telos_add_goal`, `telos_complete_goal`, `telos_archive`, `telos_import_markdown` |
| `tools/webhooks/` | 3 | tracker | `create_webhook`, `list_webhooks`, `delete_webhook` |
| `tools/overseerr/` | 4 | casa | `search_overseerr_media`, `get_overseerr_media_details`, `request_overseerr_media`, `list_overseerr_requests` |
| `tools/lidarr/` | 5 | casa | `search_lidarr_artist`, `search_lidarr_album`, `add_lidarr_artist`, `add_lidarr_album`, `list_lidarr_quality_profiles` |
| `tools/picnic/` | 12 | casa | `search_picnic_product`, `get_picnic_cart`, `add_to_picnic_cart`, `remove_from_picnic_cart`, `clear_picnic_cart`, `get_picnic_delivery_slots`, `set_picnic_delivery_slot`, `submit_shopping_list_to_picnic`, `get_picnic_lists`, `get_picnic_list_details`, `get_picnic_order_history`, `get_picnic_delivery_details` |
| `tools/jira/` | 6 | comms | `list_my_jira_issues`, `get_jira_issue`, `get_issue_transitions`, `transition_jira_issue`, `add_jira_comment`, `search_jira_issues` |
| `tools/shell/` | 1 | axel | `execute_shell_command` (via `get_shell_tool()`) |
| `tools/claude_code/` | 6 | axel | `clone_repository`, `claude_code_plan`, `claude_code_continue`, `claude_code_execute`, `commit_and_push`, `list_workspaces` |
| `tools/nomad/` | 7 | axel | `list_nomad_jobs`, `get_nomad_job_status`, `get_nomad_allocation_logs`, `restart_nomad_allocation`, `plan_nomad_job_update`, `submit_nomad_job_update`, `check_nomad_service_health` |
| `tools/youtube/` (YouTube) | 3 | kidsvid | `search_youtube_videos`, `get_youtube_video_details`, `get_youtube_channel_info` |
| `tools/youtube/` (CuriosityStream) | 2 | kidsvid | `search_curiositystream`, `list_curiositystream_categories` |
| `tools/youtube/` (Kideo) | 10 | kidsvid | `add_video_to_kideo`, `add_videos_to_kideo_batch`, `list_kideo_collections`, `create_kideo_collection`, `generate_video_tags`, `set_kideo_video_tags`, `get_kideo_popular_videos`, `get_kideo_tag_stats`, `get_kideo_channel_stats`, `retag_untagged_kideo_videos` |
| `tools/shared/card_protocol.py` (cards) | 4 | casa, kidsvid | `show_media_card`, `show_season_breakdown`, `show_ha_device_card`, `show_video_card` |
| Axel execution tools | 4 | axel | `code_execution_tool`, `run_tests`, `validate_code`, `generate_documentation` |
| `load_artifacts` (ADK) | 1 | axel | built-in |

**Total**: ~105 FunctionTools + variable MCP tools + 2 ADK built-ins (`google_search`, `BuiltInCodeExecutor`).

## Module Details

### basic — `tools/basic/basic_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `get_current_time` | `city` (default "UTC") | Current time for city/timezone |

### memory — `tools/memory/agent_memory_factory.py`

Created per-agent via `create_agent_memory_tools(agent_name)`. Scoped by `source_agent` tag in Qdrant.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `search_agent_memory` | `query`, `max_results`, `time_window_days`, `memory_type` | Search this agent's scoped memories |
| `store_agent_memory` | `information`, `memory_type` | Store memory in agent's namespace |

Global variants (`search_past_conversations`, `store_important_information`) exist but are not currently assigned to any agent.

### telos project hierarchy — `tools/telos/telos_tools.py`

Projects are Telos entries in section `projects` (PRJ ref_codes). Their children live in their own sections and link back via `metadata.parent_project`. Tools for adding/completing/archiving tasks/milestones are all part of `TELOS_TOOLS` on beto (no dedicated "tracker" sub-agent).

| Tool | Parameters | Description |
|------|-----------|-------------|
| `telos_list_projects` | — | List active Telos projects |
| `telos_get_project` | `ref_or_name` | Render a project with all its milestones, tasks grouped by kanban status, explorations, and linked goals |
| `telos_add_milestone` | `title`, `parent_project`, `deadline?`, `details?` | Add a milestone under a project (confirm-required, auto-assigns `MS<N>`) |
| `telos_complete_milestone` | `ref_code`, `resolution?` | Mark a milestone completed (silent) |
| `telos_add_task` | `description`, `parent_project`, `parent_milestone?`, `title?`, `category?`, `task_status?` | Add a project task (confirm-required, auto-assigns `PT<N>`). `task_status` ∈ `backlog` / `inprogress` / `done`, default `backlog` |
| `telos_list_tasks` | `parent_project?`, `parent_milestone?`, `task_status?`, `include_inactive?` | Filter project tasks |
| `telos_complete_task` | `ref_code` | Flip task's `metadata.task_status` → `done` (silent) |
| `telos_archive_task` | `ref_code`, `reason?` | Soft-delete a task (confirm-required) |
| `telos_add_exploration` | `topic`, `parent_project`, `notes?` | Record an open research thread under a project (confirm-required, auto-assigns `EX<N>`). Use for "I want to look into X" capture before it becomes a task |

### calendar — `tools/calendar/calendar_tools.py`

| Tool | Parameters |
|------|-----------|
| `list_calendar_events` | `calendar_id`, `max_results`, `query`, `days_ahead`, `is_workspace` |
| `create_calendar_event` | `summary`, `start_time`, `end_time`, `description`, `location`, `attendees`, `calendar_id`, `timezone`, `is_workspace` |
| `update_calendar_event` | `event_id`, `summary`, `start_time`, `end_time`, `description`, `location`, `attendees`, `calendar_id`, `timezone`, `is_workspace` |
| `delete_calendar_event` | `event_id`, `calendar_id`, `is_workspace` |
| `check_calendar_availability` | `calendar_ids`, `days_ahead`, `is_workspace` |

### gmail — `tools/gmail/gmail_tools.py`

| Tool | Parameters |
|------|-----------|
| `list_emails` | `max_results`, `label`, `account` |
| `search_emails` | `query`, `max_results`, `account` |
| `get_email` | `message_id`, `account` |
| `list_gmail_accounts` | — |

### homeassistant (MCP, primary) — `tools/homeassistant/ha_mcp_client.py` + `ha_mcp_tools.py`

Casa's default HA tool surface. Discovered dynamically from HA's `mcp_server` integration (HA 2025.2+) at agent-construction time via `HAMcpClient.list_tools_sync()`; each tool wrapped as an ADK FunctionTool whose implementation forwards to `HAMcpClient.call_tool(name, arguments)` via streamable-HTTP JSON-RPC. Tool set depends on Assist exposure in HA — typical shape:

| Tool | Parameters | Notes |
|------|-----------|-------|
| `HassTurnOn` / `HassTurnOff` | `name?`, `area?`, `floor?`, `domain[]?`, `device_class[]?` | HA's `MatchTargets` resolves — no `entity_id` required. `domain` as array (e.g. `["light","switch"]`) spans multiple domains in one call. |
| `HassLightSet` | `name?`, `area?`, `floor?`, `domain[]?`, `color?`, `temperature?`, `brightness?` | Brightness 0-100, color as CSS color name, temperature Kelvin. |
| `HassClimateSetTemperature` / `HassClimateGetTemperature` | `name?`, `area?`, `temperature?` | (exposed only if HA has climate entities on the Assist allowlist) |
| `HassMediaSearchAndPlay` | `search_query`, `media_class?`, `name?`, `area?`, `floor?` | `media_class` enum: album, app, artist, channel, ... |
| `HassMediaPause` / `HassMediaUnpause` / `HassMediaNext` / `HassMediaPrevious` / `HassSetVolume` / `HassSetVolumeRelative` / `HassMediaPlayerMute` / `HassMediaPlayerUnmute` | `name?`, `area?` (+ `volume_level` for `HassSetVolume`) | |
| `HassVacuumStart` / `HassVacuumReturnToBase` / `HassVacuumCleanArea` | `name?`, `area?` | |
| `HassFanSetSpeed` | `name?`, `area?`, `speed` (0-100) | |
| `HassBroadcast` | `message` | TTS broadcast through whole home. |
| `HassCancelAllTimers` / `HassStartTimer` | timer-specific | (exposure-dependent) |
| `GetLiveContext` | — | Returns YAML-formatted snapshot of all Assist-exposed entities. Replaces the legacy `list_ha_entities` / `search_ha_entities`. |
| `GetDateTime` | — | HA's system date/time. |
| `<user_script_name>` | user-defined | Every HA script the user has exposed to Assist appears as its own tool. Names are sanitized to valid Python identifiers on the radbot side. |

HA wraps each response in `{"success": bool, "result": ...}`; `ha_mcp_tools._unwrap_ha_envelope` unwraps before returning to the LLM.

### homeassistant (REST, fallback) — `tools/homeassistant/ha_tools_impl.py`

Loaded only when `integrations.home_assistant.use_mcp = false` or MCP tool discovery fails at startup. Kept as an escape hatch for non-exposed entities and for `web/api/ha.py`'s frontend device buttons.

| Tool | Parameters |
|------|-----------|
| `list_ha_entities` | — |
| `get_ha_entity_state` | `entity_id` |
| `turn_on_ha_entity` | `entity_id` |
| `turn_off_ha_entity` | `entity_id` |
| `toggle_ha_entity` | `entity_id` |
| `search_ha_entities` | `search_term`, `domain_filter` |

### homeassistant (Dashboard) — `tools/homeassistant/ha_dashboard_tools.py`

Uses WebSocket client (`ha_websocket_client.py`) for Lovelace CRUD.

| Tool | Parameters |
|------|-----------|
| `list_ha_dashboards` | — |
| `get_ha_dashboard_config` | `url_path` |
| `create_ha_dashboard` | `url_path`, `title`, `icon`, `require_admin` |
| `update_ha_dashboard` | `dashboard_id`, `title`, `icon`, `require_admin` |
| `delete_ha_dashboard` | `dashboard_id` |
| `save_ha_dashboard_config` | `config`, `url_path` |

### scheduler — `tools/scheduler/schedule_tools.py`

| Tool | Parameters |
|------|-----------|
| `create_scheduled_task` | `name`, `cron_expression`, `prompt`, `description` |
| `list_scheduled_tasks` | — |
| `delete_scheduled_task` | `task_id` |

### reminders — `tools/reminders/reminder_tools.py`

| Tool | Parameters |
|------|-----------|
| `create_reminder` | `message`, `remind_at`, `delay_minutes`, `timezone_name` |
| `list_reminders` | `status` (pending/completed/cancelled/all) |
| `delete_reminder` | `reminder_id` |

### telos — `tools/telos/telos_tools.py`

Persistent user-context store (mission, goals, problems, projects, challenges, wisdom, predictions, taste, journal, etc.). Beto-only. An anchor (~300B) is injected into `system_instruction` every turn via `inject_telos_context`; the full block (~2KB) is injected on the first turn of each session (gated by `callback_context.state['telos_bootstrapped']`). One-time onboarding via `uv run python -m radbot.tools.telos.cli onboard`.

See `docs/implementation/telos.md` for the design and update policy (silent vs. confirm-required tools).

**Read tools**

| Tool | Parameters |
|------|-----------|
| `telos_get_section` | `section`, `include_inactive` |
| `telos_get_entry` | `section`, `ref_code` |
| `telos_get_full` | — |
| `telos_search_journal` | `query`, `limit` |

**Silent-update tools** (agent calls without asking)

| Tool | Parameters |
|------|-----------|
| `telos_add_journal` | `entry`, `event_type`, `related_refs` |
| `telos_add_prediction` | `claim`, `probability`, `deadline` |
| `telos_resolve_prediction` | `ref_code`, `outcome`, `actual_value` (auto-adds `wrong_about` on miscalibration) |
| `telos_note_wrong` | `thing`, `why` |
| `telos_note_taste` | `category`, `item`, `sentiment`, `note` |
| `telos_add_wisdom` | `principle`, `origin` |
| `telos_add_idea` | `idea` |

**Confirm-required tools** (agent proposes, user approves)

| Tool | Parameters |
|------|-----------|
| `telos_upsert_identity` | `content`, `name`, `location`, `role`, `pronouns` |
| `telos_add_entry` | `section`, `content`, `metadata`, `ref_code` |
| `telos_update_entry` | `section`, `ref_code`, `content`, `metadata_merge`, `status` |
| `telos_add_goal` | `title`, `deadline`, `kpi`, `parent_problem` |
| `telos_complete_goal` | `ref_code`, `resolution` (also writes a journal entry) |
| `telos_archive` | `section`, `ref_code`, `reason` |
| `telos_import_markdown` | `markdown_text`, `replace` |

### webhooks — `tools/webhooks/webhook_tools.py`

| Tool | Parameters |
|------|-----------|
| `create_webhook` | `name`, `path_suffix`, `prompt_template`, `secret` |
| `list_webhooks` | — |
| `delete_webhook` | `webhook_id` |

### overseerr — `tools/overseerr/overseerr_tools.py`

| Tool | Parameters |
|------|-----------|
| `search_overseerr_media` | `query`, `page` |
| `get_overseerr_media_details` | `tmdb_id`, `media_type` |
| `request_overseerr_media` | `tmdb_id`, `media_type`, `seasons` |
| `list_overseerr_requests` | `max_results`, `filter_status` |

### lidarr — `tools/lidarr/lidarr_tools.py`

| Tool | Parameters |
|------|-----------|
| `search_lidarr_artist` | `query` |
| `search_lidarr_album` | `query` |
| `add_lidarr_artist` | `foreign_artist_id`, `quality_profile_id`, `root_folder_path`, `monitor` |
| `add_lidarr_album` | `foreign_album_id`, `quality_profile_id`, `root_folder_path`, `monitor` |
| `list_lidarr_quality_profiles` | — |

### picnic — `tools/picnic/picnic_tools.py`

| Tool | Parameters |
|------|-----------|
| `search_picnic_product` | `query` |
| `get_picnic_cart` | — |
| `add_to_picnic_cart` | `product_id`, `count` |
| `remove_from_picnic_cart` | `product_id`, `count` |
| `clear_picnic_cart` | — |
| `get_picnic_delivery_slots` | — |
| `set_picnic_delivery_slot` | `slot_id` |
| `submit_shopping_list_to_picnic` | `project_name` |
| `get_picnic_lists` | — |
| `get_picnic_list_details` | `list_id` |
| `get_picnic_order_history` | — |
| `get_picnic_delivery_details` | `delivery_id` |

### jira — `tools/jira/jira_tools.py`

| Tool | Parameters |
|------|-----------|
| `list_my_jira_issues` | `project`, `status`, `priority`, `max_results` |
| `get_jira_issue` | `issue_key` |
| `get_issue_transitions` | `issue_key` |
| `transition_jira_issue` | `issue_key`, `status_name` |
| `add_jira_comment` | `issue_key`, `comment` |
| `search_jira_issues` | `jql`, `max_results` |

### shell — `tools/shell/shell_tool.py`

| Tool | Parameters |
|------|-----------|
| `execute_shell_command` | `command`, `arguments`, `timeout` — allow-listed in strict mode |

### claude_code — `tools/claude_code/claude_code_tools.py`

| Tool | Parameters |
|------|-----------|
| `clone_repository` | `owner`, `repo`, `branch` |
| `claude_code_plan` | `prompt`, `work_folder`, `session_id` |
| `claude_code_continue` | `prompt`, `session_id`, `work_folder` |
| `claude_code_execute` | `prompt`, `work_folder`, `session_id` |
| `commit_and_push` | `work_folder`, `commit_message`, `branch` |
| `list_workspaces` | — |

### nomad — `tools/nomad/nomad_tools.py`

| Tool | Parameters |
|------|-----------|
| `list_nomad_jobs` | `prefix` |
| `get_nomad_job_status` | `job_id` |
| `get_nomad_allocation_logs` | `job_id`, `task`, `log_type`, `lines` |
| `restart_nomad_allocation` | `job_id`, `task` |
| `plan_nomad_job_update` | `job_file_path` |
| `submit_nomad_job_update` | `job_file_path` |
| `check_nomad_service_health` | `service_name` |

### youtube — `tools/youtube/`

Three client modules wired onto the kidsvid agent.

**YouTube** (`youtube_tools.py`, `youtube_client.py`):

| Tool | Parameters |
|------|-----------|
| `search_youtube_videos` | `query`, `max_results`, `safe_search` — blocks YouTube Shorts at ingest |
| `get_youtube_video_details` | `video_id` |
| `get_youtube_channel_info` | `channel_id` |

**CuriosityStream** (`curiositystream_tools.py`, `curiositystream_client.py`):

| Tool | Parameters |
|------|-----------|
| `search_curiositystream` | `query`, `max_results` |
| `list_curiositystream_categories` | — |

**Kideo library** (`kideo_tools.py`, `kideo_client.py`, `tag_generator.py`):

| Tool | Parameters | Notes |
|------|-----------|-------|
| `add_video_to_kideo` | `video_id`, `collection_id`, `tags` | Blocks Shorts |
| `add_videos_to_kideo_batch` | `video_ids`, `collection_id` | Bulk ingest |
| `list_kideo_collections` | — | |
| `create_kideo_collection` | `name`, `description` | |
| `generate_video_tags` | `video_id` | AI tags from transcript + description |
| `set_kideo_video_tags` | `video_id`, `tags` | Overwrite tags |
| `get_kideo_popular_videos` | `limit` | Analytics: play counts |
| `get_kideo_tag_stats` | — | Tag usage stats |
| `get_kideo_channel_stats` | `channel_id` | Per-channel analytics |
| `retag_untagged_kideo_videos` | `batch_size` | Backfill AI tags |

### card_protocol — `tools/shared/card_protocol.py`

Emits ` ```radbot:<kind> ` fenced JSON blocks the agent includes verbatim in its reply. Frontend parses into UI components.

Valid kinds: `media`, `seasons`, `ha-device`, `handoff`, `video`.

| Tool | Parameters | Notes |
|------|-----------|-------|
| `show_media_card` | `tmdb_id`, `media_type`, `title`, `year`, ... | Best-effort Overseerr poster lookup when `tmdb_id` + `media_type` known |
| `show_season_breakdown` | `tmdb_id`, `title`, `seasons` (list) | Per-season progress/status |
| `show_ha_device_card` | `entity_id`, `state`, `brightness_pct`, ... | Domain-inferred icon |
| `show_video_card` | `title`, `source`, `url`, `video_id`, `channel`, `duration_seconds`, `thumbnail_url`, `tags`, `note`, ... | Kidsvid card. Auto-resolves Kideo library status via `kideo_client.find_video_by_url`. Direct-action ADD TO KIDEO button hits `/api/videos/add-to-kideo` |

`handoff` blocks are emitted server-side, not by agents — `session_runner.py` wraps every `agent_transfer` event as a `radbot:handoff` block (reflexive/duplicate transfers filtered).

### execution tools — `agent/execution_agent/tools.py`

Axel-specific (not a standalone module):

| Tool | Purpose |
|------|---------|
| `code_execution_tool` | Runs Python code in a temp file via shell (30s timeout) |
| `run_tests` | pytest runner |
| `validate_code` | Syntax/lint validation |
| `generate_documentation` | Docstring / README generation |

## MCP — Consumer Side

Loaded dynamically on the axel agent only:

- **Filesystem MCP**: `create_fileserver_toolset()` — file read/write via MCP stdio server
- **Dynamic MCP**: `load_dynamic_mcp_tools()` — additional MCP servers from config

Tool count varies based on available MCP servers.

## MCP — Bridge Server (`radbot/mcp_server/`)

Exposes **radbot itself** as an MCP server so external clients (primarily Claude Code on the user's laptop / desktop) can read and mutate radbot state. Distinct from the `tools/mcp/` consumer side. See `docs/implementation/mcp_bridge.md`.

**Transports:**

- **stdio**: `uv run python -m radbot.mcp_server` (local, no auth)
- **HTTP/SSE**: `GET /mcp/sse` + `POST /mcp/messages/` mounted on the FastAPI app (bearer token)

**Tool surface** (16, all returning markdown `TextContent`):

| Group | Tools |
|---|---|
| Telos | `telos_get_full`, `telos_get_section`, `telos_get_entry`, `telos_search_journal` |
| Wiki (at `$RADBOT_WIKI_PATH`) | `wiki_read`, `wiki_list`, `wiki_search`, `wiki_write` (strict path sanitization) |
| Projects | `project_match(cwd)`, `project_list`, `project_register`, `project_get_context` |
| Tasks / schedule | `list_tasks`, `list_reminders`, `list_scheduled_tasks` |
| Memory | `search_memory` (Qdrant, default scope=`beto`, pass `agent_scope="all"` to widen) |

**Return convention:** markdown for any structured output, plain single-line text for primitives (`project_match` → name) and action confirmations (`wiki_write` → `Wrote N bytes to <path>`). Never JSON to the LLM — JSON consumers hit the REST API at `/api/*`.

**Token auth (HTTP):** credential store (`mcp_token` key) wins over `RADBOT_MCP_TOKEN` env var. Rotatable from the "MCP Bridge" admin panel via `POST /api/mcp/token/rotate`. Fails closed (503) when both unset.

## ADK Built-in Tools

| Tool | Agent | Type |
|------|-------|------|
| `google_search` | search_agent | Grounding tool (cannot mix with FunctionTools) |
| `BuiltInCodeExecutor` | code_execution_agent, axel | Code executor (via `generate_content_config` / `code_executor=`) |
| `load_artifacts` | axel | ADK artifact loading |

## Non-Tool Services

REST-only, not registered as agent FunctionTools:

| Service | Class | Endpoint | Purpose |
|---------|-------|----------|---------|
| TTS | `TTSService` | `POST /api/tts/synthesize` | Google Cloud Text-to-Speech |
| STT | `STTService` | `POST /api/stt/transcribe` | Google Cloud Speech-to-Text |
| ntfy | `NtfyClient` | (push + SSE subscriber, no REST endpoint) | Push notifications + inbound triggers |
| Alertmanager | `process_alert_from_payload()` | `POST /api/alerts/webhook` | Alert ingestion + remediation pipeline |
| Notifications | unified store | `GET/POST /api/notifications/*` | Cross-source notification feed (scheduled, reminder, alert, ntfy) |
| Direct media actions | Overseerr wrapper | `GET/POST /api/media/*` | Non-agent media search + request |
| Direct HA actions | HA REST wrapper | `GET/POST /api/ha/*` | Non-agent device state + service calls |
| Per-session token stats | `llm_usage_log` aggregation | `GET /api/sessions/{id}/stats` | Session token/cost totals |

## Key Files

| File | Purpose |
|------|---------|
| `tools/{module}/{module}_tools.py` | Tool function definitions + FunctionTool wrapping |
| `tools/{module}/__init__.py` | Exports `ALL_TOOLS` / named tool lists |
| `tools/memory/agent_memory_factory.py` | `create_agent_memory_tools()` scoped memory factory |
| `tools/shared/card_protocol.py` | Card block formatting + `CARD_TOOLS` |
| `tools/shared/config_helper.py` | `get_integration_config()` resolver |
| `tools/shared/client_utils.py` | `client_or_error()`, singleton helpers |
| `tools/shared/tool_decorator.py` | `@tool_error_handler` |
| `tools/shared/retry.py` | `@retry_on_error` |
| `tools/shared/db_schema.py` | `init_table_schema()` idempotent helper |
| `agent/factory_utils.py` | `load_tools(module, attr, agent, label)` |
