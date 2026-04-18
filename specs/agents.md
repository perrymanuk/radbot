# Agents

## Architecture

Beto is a **pure orchestrator** — it holds only memory tools and routes requests to specialized sub-agents via ADK's auto-injected `transfer_to_agent`. Each sub-agent owns its domain tools and returns control by calling `transfer_to_agent(agent_name='beto')`.

```
                              beto (orchestrator)
                                    │
     ┌─────────┬──────────┬─────────┼─────────┬──────────┬─────────┐
     │         │          │         │         │          │         │
   casa     planner    tracker    comms     axel     kidsvid    scout
  (smart   (calendar  (todo +   (email +  (execution (children   (research +
   home +   schedule + projects   Jira)     + infra)  video       design
   media +  reminders) + webhooks)                    curation)   collab)
   music +
   grocery)
                                                  │
                              scout also peers with search_agent
                              & code_execution_agent (ADK built-ins)
```

**Key architectural refinements (post-2026-03-22):**

- `scope_sub_agent_context_callback` (before-model callback on every sub-agent) trims LLM input to the *current user turn only*. Prevents context bleed (e.g. Casa volunteering movie cards because an earlier turn mentioned movies) and keeps sub-agent prompts from growing linearly with session length. Root Beto keeps full history for conversational coherence. See `radbot/callbacks/scope_to_current_turn.py`.
- `/api/agents/agent-info` walks `root_agent.sub_agents` at runtime to return the live roster (name, config key, resolved model, gemini_only flag) — the frontend admin palette reads this instead of a hard-coded list.
- Agents emit **structured UI cards** via fenced code blocks (`` ```radbot:<kind> ``). Casa ships `CARD_TOOLS` (`show_media_card`, `show_season_breakdown`, `show_ha_device_card`). Every `agent_transfer` event is also auto-wrapped as a `radbot:handoff` block by `session_runner.py` — no LLM call needed. See `radbot/tools/shared/card_protocol.py`.

## Agent Summary

| Agent | Factory | Model | Tool Count | Purpose |
|-------|---------|-------|------------|---------|
| **beto** | `agent/agent_core.py` | `config_manager.get_main_model()` (default `gemini-2.5-pro`) | 2 | Orchestrator, routes to specialists |
| **casa** | `agent/home_agent/factory.py` | `resolve_agent_model("casa_agent")` | ~38 | Smart home, media, music, grocery, card emission |
| **planner** | `agent/planner_agent/factory.py` | `resolve_agent_model("planner_agent")` | 14 | Calendar, scheduling, reminders |
| **tracker** | `agent/tracker_agent/factory.py` | `resolve_agent_model("tracker_agent")` | 13 | Tasks, projects, webhooks |
| **comms** | `agent/comms_agent/factory.py` | `resolve_agent_model("comms_agent")` | 12 | Email (Gmail), Jira |
| **axel** | `agent/execution_agent/factory.py` | `config_manager.get_agent_model("axel_agent_model")` | 17+ MCP | Shell, files, code exec, Claude Code, Nomad, MCP |
| **kidsvid** | `agent/youtube_agent/factory.py` | `resolve_agent_model("kidsvid_agent")` | 17 | Children's video curation (YouTube + CuriosityStream + Kideo) |
| **scout** | `agent/research_agent/factory.py` | `config_manager.get_agent_model("scout_agent")` | 2 | Research, design collaboration (sequential thinking) |
| **search_agent** | `tools/adk_builtin/search_tool.py` | Gemini 2+ (hardcoded) | 1 | Google Search grounding |
| **code_execution_agent** | `tools/adk_builtin/code_execution_tool.py` | Gemini 2+ (hardcoded) | 0* | Python code execution |

\* Uses `code_executor=BuiltInCodeExecutor()`, not FunctionTools.

## Root Agent — beto

- **Temperature**: 0.2
- **Global instruction**: injects today's date
- **Tools**: `search_agent_memory`, `store_agent_memory` (via `create_agent_memory_tools("beto")`)
- **Before-agent callback**: `setup_before_agent_call` — DB schema init (todo, scheduler, webhook, reminder, notifications, alerts, telemetry), HA client check
- **Before-model callbacks**: `[filter_tool_events_from_prompt, scrub_empty_content_before_model, sanitize_before_model_callback]`
- **After-model callbacks**: `[handle_empty_response_after_model, telemetry_after_model_callback]`
- **Instruction file**: `config/default_configs/instructions/main_agent.md`
- **Full conversation history**: root keeps all prior user/assistant text turns. Sub-agent tool_call and function_response events are dropped from the LLM prompt by `filter_tool_events_from_prompt` (session state is retained) to keep the cacheable prefix stable — without this, churning tool-response blobs pushed beto's prompt-cache hit rate to ~1%.

## Domain Agents

### casa — Smart Home, Media, Music, Grocery

| Tool Group | Count | Source |
|------------|-------|--------|
| Home Assistant (MCP, primary) | dynamic (~19 built-in + user-exposed scripts) | `radbot.tools.homeassistant.ha_mcp_tools.build_ha_mcp_function_tools` — discovered at factory time from HA's `mcp_server` (HA 2025.2+). Falls back to the REST row below if `use_mcp=false` or discovery fails. |
| Home Assistant REST (fallback) | 6 | `radbot.tools.homeassistant` (`search_ha_entities`, `list_ha_entities`, `get_ha_entity_state`, `turn_on/off/toggle_ha_entity`) — used when MCP disabled/unavailable |
| HA Dashboard (WS) | 6 | `radbot.tools.homeassistant.ha_dashboard_tools.HA_DASHBOARD_TOOLS` |
| Overseerr | 4 | `radbot.tools.overseerr.OVERSEERR_TOOLS` |
| Lidarr | 5 | `radbot.tools.lidarr.LIDARR_TOOLS` (`search_lidarr_artist`, `search_lidarr_album`, `add_lidarr_artist`, `add_lidarr_album`, `list_lidarr_quality_profiles`) |
| Picnic | 12 | `radbot.tools.picnic.PICNIC_TOOLS` |
| Card protocol | 3 | `radbot.tools.shared.card_protocol.CARD_TOOLS` (`show_media_card`, `show_season_breakdown`, `show_ha_device_card`) |
| Memory | 2 | `create_agent_memory_tools("casa")` |

Emits UI cards inline with replies. Casa is the only agent that currently ships `CARD_TOOLS`.

### planner — Calendar, Scheduling, Reminders

| Tool Group | Count | Source |
|------------|-------|--------|
| Time | 1 | `radbot.tools.basic.get_current_time` |
| Calendar | 5 | `list_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event`, `check_calendar_availability` |
| Scheduler | 3 | `radbot.tools.scheduler.SCHEDULER_TOOLS` |
| Reminders | 3 | `radbot.tools.reminders.REMINDER_TOOLS` |
| Memory | 2 | `create_agent_memory_tools("planner")` |

### tracker — Tasks, Projects, Webhooks

| Tool Group | Count | Source |
|------------|-------|--------|
| Todo | 8 | `radbot.tools.todo.ALL_TOOLS` |
| Webhooks | 3 | `radbot.tools.webhooks.WEBHOOK_TOOLS` |
| Memory | 2 | `create_agent_memory_tools("tracker")` |

### comms — Email, Jira

| Tool Group | Count | Source |
|------------|-------|--------|
| Gmail | 4 | `list_emails`, `search_emails`, `get_email`, `list_gmail_accounts` |
| Jira | 6 | `radbot.tools.jira.JIRA_TOOLS` |
| Memory | 2 | `create_agent_memory_tools("comms")` |

### axel — Execution & Infrastructure

| Tool Group | Count | Source |
|------------|-------|--------|
| Execution | 4 | `execution_tools` list: `code_execution_tool`, `run_tests`, `validate_code`, `generate_documentation` |
| Memory | 2 | `create_agent_memory_tools("axel")` |
| MCP (filesystem) | variable | `create_fileserver_toolset()` |
| MCP (dynamic) | variable | `load_dynamic_mcp_tools()` |
| Claude Code | 6 | `CLAUDE_CODE_TOOLS`: `clone_repository`, `claude_code_plan`, `claude_code_continue`, `claude_code_execute`, `commit_and_push`, `list_workspaces` |
| Nomad | 7 | `NOMAD_TOOLS` |
| ADK | 1 | `load_artifacts` |
| Shell | 1 | `get_shell_tool(strict_mode=True)` (when `enable_code_execution=True`) |

`enable_code_execution=True` is set in `specialized_agent_factory._create_axel_agent`.

### kidsvid — Children's Video Curation

| Tool Group | Count | Source |
|------------|-------|--------|
| YouTube | 3 | `YOUTUBE_TOOLS`: `search_youtube_videos`, `get_youtube_video_details`, `get_youtube_channel_info` |
| CuriosityStream | 2 | `CURIOSITYSTREAM_TOOLS`: `search_curiositystream`, `list_curiositystream_categories` |
| Kideo library | 10 | `KIDEO_TOOLS`: `add_video_to_kideo`, `add_videos_to_kideo_batch`, `list_kideo_collections`, `create_kideo_collection`, `generate_video_tags`, `set_kideo_video_tags`, `get_kideo_popular_videos`, `get_kideo_tag_stats`, `get_kideo_channel_stats`, `retag_untagged_kideo_videos` |
| Memory | 2 | `create_agent_memory_tools("kidsvid")` |

YouTube Shorts are filtered out at ingest time in `kideo_tools.py` (both search and Kideo submission paths).

### scout — Research & Design

- **Tools**: 2 memory (`search_agent_memory`, `store_agent_memory`)
- **Special**: `enable_sequential_thinking=True`; wrapped by `ResearchAgent` class
- Commonly used for rubber-ducking, architecture, and spec collaboration. Axel can transfer to scout for research, and vice versa.

## Built-in Agents

### search_agent

- **Tool**: `google_search` (ADK built-in grounding tool)
- **Flags**: `disallow_transfer_to_parent=True`, `disallow_transfer_to_peers=True`
- **Reason**: Google Search grounding cannot be mixed with function declarations in the same agent
- **Model**: Must be Gemini 2+ (Ollama / LiteLLM won't work)

### code_execution_agent

- **Tool**: `BuiltInCodeExecutor` (via `generate_content_config`)
- **Flags**: `disallow_transfer_to_parent=True`, `disallow_transfer_to_peers=True`
- **Reason**: Built-in tools + Function Calling can't be combined in Gemini API
- **Model**: Must be Gemini 2+

## Creation Flow

All assembly happens in `radbot/agent/agent_core.py` at module import time:

1. `create_agent_memory_tools("beto")` — beto's 2 memory tools
2. `create_search_agent()`, `create_code_execution_agent()`, `create_research_agent(name="scout", as_subagent=False)` — the three "peer" sub-agents
3. `create_specialized_agents()` builds the domain agents in order: casa → planner → tracker → comms → axel → kidsvid. None-returning factories are filtered out.
4. `all_sub_agents` = builtin sub-agents + specialized — passed to the root `Agent(...)` constructor
5. **Before construction**, callbacks are attached to each sub-agent:
   - `before_model_callback = [scope_sub_agent_context_callback, scrub_empty_content_before_model]`
   - `after_model_callback = [handle_empty_response_after_model, telemetry_after_model_callback]`
6. Root `Agent(...)` is constructed — ADK's `model_post_init()` builds the `_Mesh` routing graph once, setting `parent_agent` on every sub-agent

**Critical**: agents added to `sub_agents` after construction are NOT part of the mesh — `transfer_to_agent` will not find them. See `docs/implementation/session_id_tracking.md` for history.

## Per-Turn Context Scoping

`scope_sub_agent_context_callback` (in `radbot/callbacks/scope_to_current_turn.py`) runs before every sub-agent LLM call. It:

1. Walks `llm_request.contents` bottom-up
2. Finds the most recent `role='user'` entry whose parts include actual text (not just a `function_response`)
3. Slices `contents` from that index forward

What remains: the current user message, any in-flight model output, any function_response parts from the current invocation. What gets dropped: every prior user/assistant turn.

**Result**: Each sub-agent prompt contains only the current turn → no cross-domain context bleed, no linear token growth with session length.

## Routing Rules

From `config/default_configs/instructions/main_agent.md`:

| Request Type | Agent |
|-------------|-------|
| Smart home, lights, sensors, climate, media requests, music (Lidarr), grocery (Picnic) | `casa` |
| Calendar, reminders, scheduled tasks, time queries | `planner` |
| Todo lists, projects, task management, webhooks | `tracker` |
| Email (Gmail), Jira issues | `comms` |
| Web research, design discussion, rubber-ducking | `scout` |
| Code implementation, file ops, shell, GitHub, Nomad, alerts | `axel` |
| Children's video curation / Kideo library | `kidsvid` |
| Python calculations, quick code execution | `code_execution_agent` |
| Web search grounding | `search_agent` |
| Chitchat, greetings | `beto` (direct response) |

## Callback Inventory

| Callback | File | Applied To | Purpose |
|----------|------|------------|---------|
| `setup_before_agent_call` | `agent/agent_tools_setup.py` | beto (before_agent) | DB schema init; HA client warm-up |
| `sanitize_before_model_callback` | `callbacks/sanitize_callback.py` | beto (before_model) | Strip PII / sensitive tokens |
| `scrub_empty_content_before_model` | `callbacks/empty_content_callback.py` | all (before_model) | Drop Content entries with empty text parts (Gemini API errors) |
| `scope_sub_agent_context_callback` | `callbacks/scope_to_current_turn.py` | sub-agents only (before_model) | Trim to current turn |
| `filter_tool_events_from_prompt` | `callbacks/filter_tool_events.py` | beto only (before_model) | Drop tool-only Content (function_call / function_response) from the LLM prompt so beto's cacheable prefix stays stable across turns |
| `handle_empty_response_after_model` | `callbacks/empty_content_callback.py` | all (after_model) | Replace empty model responses with a "still thinking" marker |
| `telemetry_after_model_callback` | `callbacks/telemetry_callback.py` | all (after_model) | Record token usage + cost in `llm_usage_log` with `session_id` |
| `tool_call_repair_callback` | `callbacks/tool_call_repair_callback.py` | (available, not wired by default) | Repair malformed function calls |

## Key Files

| File | Purpose |
|------|---------|
| `agent/agent_core.py` | Root agent creation, sub-agent assembly, callback wiring |
| `agent/agent_tools_setup.py` | DB schema init callback, search/code/scout creation |
| `agent/specialized_agent_factory.py` | Domain agent creation (casa, planner, tracker, comms, axel, kidsvid) |
| `agent/{domain}_agent/factory.py` | Per-domain agent factory function |
| `agent/shared.py` | `load_agent_instruction`, `resolve_agent_model`, task/transfer instruction helpers |
| `config/default_configs/instructions/*.md` | Agent instruction files (main_agent.md, casa.md, planner.md, tracker.md, comms.md, axel.md, scout.md, kidsvid.md) |
| `tools/adk_builtin/search_tool.py` | `search_agent` factory |
| `tools/adk_builtin/code_execution_tool.py` | `code_execution_agent` factory |
| `callbacks/scope_to_current_turn.py` | Per-turn context scoping for sub-agents |
| `callbacks/filter_tool_events.py` | Strip tool-only Content from beto's LLM prompt to keep cacheable prefix stable |
| `tools/shared/card_protocol.py` | `radbot:<kind>` fenced-block card emission |
