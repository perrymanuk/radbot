# Agents

## Architecture

Beto is a **pure orchestrator** — it holds only memory tools and routes requests to specialized sub-agents via ADK's auto-injected `transfer_to_agent`. Each sub-agent owns its domain tools and returns control by calling `transfer_to_agent(agent_name='beto')`.

```
                         beto (orchestrator)
                              │
        ┌─────────┬───────────┼───────────┬──────────┐
        │         │           │           │          │
      casa    planner     tracker      comms       axel
   (smart     (calendar   (todo        (email     (execution
    home)      schedule)   projects)    jira)      infra)
        │
        └── scout, search_agent, code_execution_agent
```

## Agent Summary

| Agent | Factory | Model | Tool Count | Purpose |
|-------|---------|-------|------------|---------|
| **beto** | `agent/agent_core.py` | `get_main_model()` (gemini-2.5-pro) | 2 | Orchestrator, routes to specialists |
| **casa** | `agent/home_agent/factory.py` | `resolve_agent_model("casa_agent")` | 28 | Smart home, media, dashboards, grocery |
| **planner** | `agent/planner_agent/factory.py` | `resolve_agent_model("planner_agent")` | 14 | Calendar, scheduling, reminders |
| **tracker** | `agent/tracker_agent/factory.py` | `resolve_agent_model("tracker_agent")` | 13 | Tasks, projects, webhooks |
| **comms** | `agent/comms_agent/factory.py` | `resolve_agent_model("comms_agent")` | 12 | Email (Gmail), Jira |
| **axel** | `agent/execution_agent/factory.py` | `get_agent_model("axel_agent")` | 17+ | Shell, files, Claude Code, Nomad, MCP |
| **scout** | `agent/research_agent/factory.py` | `get_agent_model("scout_agent")` | 2 | Research, design collaboration |
| **search_agent** | `tools/adk_builtin/search_tool.py` | Gemini 2+ required | 1 | Google Search grounding |
| **code_execution_agent** | `tools/adk_builtin/code_execution_tool.py` | Gemini 2+ required | 0* | Python code execution |

\* Uses `code_executor=BuiltInCodeExecutor()`, not FunctionTools.

## Root Agent — beto

- **Temperature**: 0.2
- **Tools**: `search_agent_memory`, `store_agent_memory` (via `create_agent_memory_tools("beto")`)
- **Before-agent callback**: `setup_before_agent_call` — DB schema init (todo, scheduler, webhook, reminder), HA client check
- **Before-model callbacks**: `sanitize_before_model_callback`
- **After-model callbacks**: `handle_empty_response_after_model`, `telemetry_after_model_callback`
- **Instruction file**: `config/default_configs/instructions/main_agent.md`

## Domain Agents

### casa (Smart Home & Media)

| Tool Group | Count | Tools |
|------------|-------|-------|
| Home Assistant REST | 6 | `list_ha_entities`, `get_ha_entity_state`, `turn_on_ha_entity`, `turn_off_ha_entity`, `toggle_ha_entity`, `search_ha_entities` |
| HA Dashboard (WS) | 6 | `list_ha_dashboards`, `get_ha_dashboard_config`, `create_ha_dashboard`, `update_ha_dashboard`, `delete_ha_dashboard`, `save_ha_dashboard_config` |
| Overseerr | 4 | `search_overseerr_media`, `get_overseerr_media_details`, `request_overseerr_media`, `list_overseerr_requests` |
| Picnic | 10 | `search_picnic_product`, `get_picnic_cart`, `add_to_picnic_cart`, `remove_from_picnic_cart`, `clear_picnic_cart`, `get_picnic_delivery_slots`, `set_picnic_delivery_slot`, `submit_shopping_list_to_picnic`, `get_picnic_order_history`, `get_picnic_delivery_details` |
| Memory | 2 | `search_agent_memory`, `store_agent_memory` |

### planner (Calendar & Scheduling)

| Tool Group | Count | Tools |
|------------|-------|-------|
| Time | 1 | `get_current_time` |
| Calendar | 5 | `list_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event`, `check_calendar_availability` |
| Scheduler | 3 | `create_scheduled_task`, `list_scheduled_tasks`, `delete_scheduled_task` |
| Reminders | 3 | `create_reminder`, `list_reminders`, `delete_reminder` |
| Memory | 2 | `search_agent_memory`, `store_agent_memory` |

### tracker (Tasks & Projects)

| Tool Group | Count | Tools |
|------------|-------|-------|
| Todo | 8 | `add_task`, `complete_task`, `remove_task`, `list_projects`, `list_project_tasks`, `list_all_tasks`, `update_task`, `update_project` |
| Webhooks | 3 | `create_webhook`, `list_webhooks`, `delete_webhook` |
| Memory | 2 | `search_agent_memory`, `store_agent_memory` |

### comms (Email & Issue Tracking)

| Tool Group | Count | Tools |
|------------|-------|-------|
| Gmail | 4 | `list_emails`, `search_emails`, `get_email`, `list_gmail_accounts` |
| Jira | 6 | `list_my_jira_issues`, `get_jira_issue`, `get_issue_transitions`, `transition_jira_issue`, `add_jira_comment`, `search_jira_issues` |
| Memory | 2 | `search_agent_memory`, `store_agent_memory` |

### axel (Execution & Infrastructure)

| Tool Group | Count | Tools |
|------------|-------|-------|
| Claude Code | 6 | `clone_repository`, `claude_code_plan`, `claude_code_continue`, `claude_code_execute`, `commit_and_push`, `list_workspaces` |
| Nomad | 7 | `list_nomad_jobs`, `get_nomad_job_status`, `get_nomad_allocation_logs`, `restart_nomad_allocation`, `plan_nomad_job_update`, `submit_nomad_job_update`, `check_nomad_service_health` |
| Shell | 1 | `execute_shell_command` (via `get_shell_tool()`) |
| ADK | 1 | `load_artifacts` |
| MCP (filesystem) | variable | Via `create_fileserver_toolset()` |
| MCP (dynamic) | variable | Via `load_dynamic_mcp_tools()` |
| Memory | 2 | `search_agent_memory`, `store_agent_memory` |

Has `code_executor=BuiltInCodeExecutor()` enabled. Can transfer to scout for research tasks.

### scout (Research & Design)

- **Tools**: 2 memory (`search_agent_memory`, `store_agent_memory`)
- **Special**: `enable_sequential_thinking=True`
- Wrapped by `ResearchAgent` class

## Built-in Agents

### search_agent

- **Tool**: `google_search` (ADK built-in grounding tool)
- **Flags**: `disallow_transfer_to_parent=True`, `disallow_transfer_to_peers=True`
- **Reason**: Google Search grounding tool cannot be mixed with function declarations
- **Model**: Must be Gemini 2+ (hardcoded)

### code_execution_agent

- **Tool**: `BuiltInCodeExecutor` (via `generate_content_config`)
- **Flags**: `disallow_transfer_to_parent=True`, `disallow_transfer_to_peers=True`
- **Reason**: Built-in tools and Function Calling cannot be combined in Gemini API
- **Model**: Must be Gemini 2+ (hardcoded)

## Creation Flow

1. `agent_core.py:create_agent()` creates `search_agent`, `code_execution_agent`, `scout_agent`
2. Root agent created with those 3 as initial `sub_agents`
3. `specialized_agent_factory.py:create_specialized_agents(root_agent)` creates casa, planner, tracker, comms, axel
4. Each appended to `root_agent.sub_agents`
5. **Critical**: `parent_agent` manually set on each — ADK only sets it at construction time via `model_post_init()`
6. Before-model callbacks (`scrub_empty_content`, `sanitize`) and after-model callbacks (`handle_empty_response`, `telemetry`) attached to all sub-agents

## Routing Rules

From `main_agent.md` instruction file:

| Request Type | Agent |
|-------------|-------|
| Smart home, lights, sensors, climate, media requests, grocery | `casa` |
| Calendar, reminders, scheduled tasks, time queries | `planner` |
| Todo lists, projects, task management, webhooks | `tracker` |
| Email (Gmail), Jira issues | `comms` |
| Web research, design discussion, rubber-ducking | `scout` |
| Code implementation, file ops, shell, GitHub, Nomad, alerts | `axel` |
| Python calculations, quick code execution | `code_execution_agent` |
| Web search grounding | `search_agent` |
| Chitchat, greetings | `beto` (direct response) |

## Key Files

| File | Purpose |
|------|---------|
| `agent/agent_core.py` | Root agent creation, callback wiring |
| `agent/agent_tools_setup.py` | DB schema init callback, search/code/scout creation |
| `agent/specialized_agent_factory.py` | Domain agent creation + parent_agent wiring |
| `agent/{domain}_agent/factory.py` | Per-domain agent factory function |
| `config/default_configs/instructions/*.md` | Agent instruction files |
| `tools/adk_builtin/search_tool.py` | search_agent factory |
| `tools/adk_builtin/code_execution_tool.py` | code_execution_agent factory |
