# Tools

## Architecture

All agent tools are `google.adk.tools.FunctionTool` wrappers around plain Python functions. Tools return `{"status": "success/error", ...}` dicts. Each tool module exports an `ALL_TOOLS` or named list (e.g., `HA_TOOLS`, `SCHEDULER_TOOLS`) for registration in agent factories.

Non-tool services (TTS, STT, ntfy) expose REST endpoints only — they are not registered as agent FunctionTools.

## Tool Inventory

| Module | Count | Agent | Tool Names |
|--------|-------|-------|------------|
| `tools/basic/` | 1 | planner | `get_current_time` |
| `tools/memory/` | 2/agent | all | `search_agent_memory`, `store_agent_memory` |
| `tools/todo/api/` | 8 | tracker | `add_task`, `complete_task`, `remove_task`, `list_projects`, `list_project_tasks`, `list_all_tasks`, `update_task`, `update_project` |
| `tools/calendar/` | 5 | planner | `list_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event`, `check_calendar_availability` |
| `tools/gmail/` | 4 | comms | `list_emails`, `search_emails`, `get_email`, `list_gmail_accounts` |
| `tools/homeassistant/` (REST) | 6 | casa | `list_ha_entities`, `get_ha_entity_state`, `turn_on_ha_entity`, `turn_off_ha_entity`, `toggle_ha_entity`, `search_ha_entities` |
| `tools/homeassistant/` (Dashboard) | 6 | casa | `list_ha_dashboards`, `get_ha_dashboard_config`, `create_ha_dashboard`, `update_ha_dashboard`, `delete_ha_dashboard`, `save_ha_dashboard_config` |
| `tools/scheduler/` | 3 | planner | `create_scheduled_task`, `list_scheduled_tasks`, `delete_scheduled_task` |
| `tools/reminders/` | 3 | planner | `create_reminder`, `list_reminders`, `delete_reminder` |
| `tools/webhooks/` | 3 | tracker | `create_webhook`, `list_webhooks`, `delete_webhook` |
| `tools/overseerr/` | 4 | casa | `search_overseerr_media`, `get_overseerr_media_details`, `request_overseerr_media`, `list_overseerr_requests` |
| `tools/picnic/` | 10 | casa | `search_picnic_product`, `get_picnic_cart`, `add_to_picnic_cart`, `remove_from_picnic_cart`, `clear_picnic_cart`, `get_picnic_delivery_slots`, `set_picnic_delivery_slot`, `submit_shopping_list_to_picnic`, `get_picnic_order_history`, `get_picnic_delivery_details` |
| `tools/jira/` | 6 | comms | `list_my_jira_issues`, `get_jira_issue`, `get_issue_transitions`, `transition_jira_issue`, `add_jira_comment`, `search_jira_issues` |
| `tools/shell/` | 1 | axel | `execute_shell_command` |
| `tools/claude_code/` | 6 | axel | `clone_repository`, `claude_code_plan`, `claude_code_continue`, `claude_code_execute`, `commit_and_push`, `list_workspaces` |
| `tools/nomad/` | 7 | axel | `list_nomad_jobs`, `get_nomad_job_status`, `get_nomad_allocation_logs`, `restart_nomad_allocation`, `plan_nomad_job_update`, `submit_nomad_job_update`, `check_nomad_service_health` |

**Total**: ~68 FunctionTools + variable MCP tools + 2 ADK built-ins

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

### todo — `tools/todo/api/`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `add_task` | `description`, `project_id`, `title`, `category`, `origin`, `related_info` | Create new task |
| `complete_task` | `task_id` | Mark task as done |
| `remove_task` | `task_id` | Delete task |
| `list_projects` | — | List all projects |
| `list_project_tasks` | `project_id`, `status_filter`, `include_done` | List tasks in a project |
| `list_all_tasks` | `status_filter`, `include_done` | List all tasks across projects |
| `update_task` | `task_id`, `title`, `description`, `status`, `category`, `related_info` | Update task fields |
| `update_project` | `project_id`, `name` | Rename project |

### calendar — `tools/calendar/calendar_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_calendar_events` | `calendar_id`, `max_results`, `query`, `days_ahead`, `is_workspace` | List upcoming events |
| `create_calendar_event` | `summary`, `start_time`, `end_time`, `description`, `location`, `attendees`, `calendar_id`, `timezone`, `is_workspace` | Create event |
| `update_calendar_event` | `event_id`, `summary`, `start_time`, `end_time`, `description`, `location`, `attendees`, `calendar_id`, `timezone`, `is_workspace` | Update event |
| `delete_calendar_event` | `event_id`, `calendar_id`, `is_workspace` | Delete event |
| `check_calendar_availability` | `calendar_ids`, `days_ahead`, `is_workspace` | Check free/busy times |

### gmail — `tools/gmail/gmail_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_emails` | `max_results`, `label`, `account` | List recent emails |
| `search_emails` | `query`, `max_results`, `account` | Search with Gmail query syntax |
| `get_email` | `message_id`, `account` | Get full email content |
| `list_gmail_accounts` | — | List configured accounts |

### homeassistant — `tools/homeassistant/ha_tools_impl.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_ha_entities` | — | List all entities |
| `get_ha_entity_state` | `entity_id` | Get entity state + attributes |
| `turn_on_ha_entity` | `entity_id` | Turn on device |
| `turn_off_ha_entity` | `entity_id` | Turn off device |
| `toggle_ha_entity` | `entity_id` | Toggle on/off |
| `search_ha_entities` | `search_term`, `domain_filter` | Search by name/ID |

### homeassistant dashboard — `tools/homeassistant/ha_dashboard_tools.py`

Uses WebSocket client (`ha_websocket_client.py`) for Lovelace CRUD.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_ha_dashboards` | — | List all Lovelace dashboards |
| `get_ha_dashboard_config` | `url_path` | Get dashboard views/cards config |
| `create_ha_dashboard` | `url_path`, `title`, `icon`, `require_admin` | Create new dashboard |
| `update_ha_dashboard` | `dashboard_id`, `title`, `icon`, `require_admin` | Update dashboard metadata |
| `delete_ha_dashboard` | `dashboard_id` | Delete dashboard |
| `save_ha_dashboard_config` | `config`, `url_path` | Save full Lovelace config JSON |

### scheduler — `tools/scheduler/schedule_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `create_scheduled_task` | `name`, `cron_expression`, `prompt`, `description` | Create recurring cron task |
| `list_scheduled_tasks` | — | List all scheduled tasks |
| `delete_scheduled_task` | `task_id` | Delete scheduled task |

### reminders — `tools/reminders/reminder_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `create_reminder` | `message`, `remind_at`, `delay_minutes`, `timezone_name` | Set one-shot reminder |
| `list_reminders` | `status` (pending/completed/cancelled/all) | List reminders |
| `delete_reminder` | `reminder_id` | Cancel/delete reminder |

### webhooks — `tools/webhooks/webhook_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `create_webhook` | `name`, `path_suffix`, `prompt_template`, `secret` | Register webhook endpoint |
| `list_webhooks` | — | List registered webhooks |
| `delete_webhook` | `webhook_id` | Delete webhook |

### overseerr — `tools/overseerr/overseerr_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `search_overseerr_media` | `query`, `page` | Search movies/TV shows |
| `get_overseerr_media_details` | `tmdb_id`, `media_type` | Get movie/TV details |
| `request_overseerr_media` | `tmdb_id`, `media_type`, `seasons` | Request media download |
| `list_overseerr_requests` | `max_results`, `filter_status` | List current requests |

### picnic — `tools/picnic/picnic_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `search_picnic_product` | `query` | Search grocery catalog |
| `get_picnic_cart` | — | View shopping cart |
| `add_to_picnic_cart` | `product_id`, `count` | Add product to cart |
| `remove_from_picnic_cart` | `product_id`, `count` | Remove from cart |
| `clear_picnic_cart` | — | Clear all items |
| `get_picnic_delivery_slots` | — | List available delivery times |
| `set_picnic_delivery_slot` | `slot_id` | Place order (commits) |
| `submit_shopping_list_to_picnic` | `project_name` | Add todo items to cart |
| `get_picnic_order_history` | — | View past orders |
| `get_picnic_delivery_details` | `delivery_id` | Get items in past order |

### jira — `tools/jira/jira_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_my_jira_issues` | `project`, `status`, `priority`, `max_results` | List assigned issues |
| `get_jira_issue` | `issue_key` | Get issue details |
| `get_issue_transitions` | `issue_key` | List valid status transitions |
| `transition_jira_issue` | `issue_key`, `status_name` | Change issue status |
| `add_jira_comment` | `issue_key`, `comment` | Add comment |
| `search_jira_issues` | `jql`, `max_results` | Search with JQL |

### shell — `tools/shell/shell_tool.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `execute_shell_command` | `command`, `arguments`, `timeout` | Run shell command (allow-listed in strict mode) |

### claude_code — `tools/claude_code/claude_code_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `clone_repository` | `owner`, `repo`, `branch` | Clone GitHub repo via GitHub App |
| `claude_code_plan` | `prompt`, `work_folder`, `session_id` | Run Claude Code in plan-only mode |
| `claude_code_continue` | `prompt`, `session_id`, `work_folder` | Continue planning with feedback |
| `claude_code_execute` | `prompt`, `work_folder`, `session_id` | Execute approved plan |
| `commit_and_push` | `work_folder`, `commit_message`, `branch` | Commit and push via GitHub App |
| `list_workspaces` | — | List active Claude Code workspaces |

### nomad — `tools/nomad/nomad_tools.py`

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_nomad_jobs` | `prefix` | List Nomad jobs |
| `get_nomad_job_status` | `job_id` | Job status + allocations |
| `get_nomad_allocation_logs` | `job_id`, `task`, `log_type`, `lines` | Fetch allocation logs |
| `restart_nomad_allocation` | `job_id`, `task` | Restart allocation |
| `plan_nomad_job_update` | `job_file_path` | Plan job update (dry-run) |
| `submit_nomad_job_update` | `job_file_path` | Submit job update |
| `check_nomad_service_health` | `service_name` | Check service health |

## MCP Tools

Loaded dynamically on axel agent:

- **Filesystem MCP**: `create_fileserver_toolset()` — file read/write via MCP stdio server
- **Dynamic MCP**: `load_dynamic_mcp_tools()` — additional MCP servers from config

Tool count varies based on available MCP servers.

## ADK Built-in Tools

| Tool | Agent | Type |
|------|-------|------|
| `google_search` | search_agent | Grounding tool (cannot mix with FunctionTools) |
| `BuiltInCodeExecutor` | code_execution_agent, axel | Code executor (via `generate_content_config`) |
| `load_artifacts` | axel | ADK artifact loading |

## Non-Tool Services

These expose REST endpoints but are not registered as agent FunctionTools:

| Service | Class | Endpoint | Purpose |
|---------|-------|----------|---------|
| TTS | `TTSService` | `POST /api/tts/synthesize` | Google Cloud Text-to-Speech |
| STT | `STTService` | `POST /api/stt/transcribe` | Google Cloud Speech-to-Text |
| ntfy | `NtfyClient` | (push, no REST endpoint) | Push notifications via ntfy.sh |
| Alertmanager | `process_alert_from_payload()` | `POST /api/alerts/webhook` | Alert ingestion + remediation pipeline |

## Key Files

| File | Purpose |
|------|---------|
| `tools/{module}/{module}_tools.py` | Tool function definitions + FunctionTool wrapping |
| `tools/{module}/__init__.py` | Exports `ALL_TOOLS` / named tool lists |
| `tools/specialized/base_toolset.py` | Base class for domain toolsets |
| `tools/specialized/*_toolset.py` | Toolset factories combining tools per agent |
| `tools/memory/agent_memory_factory.py` | `create_agent_memory_tools()` scoped memory factory |
