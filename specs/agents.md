# Agents

## Architecture

Beto is a **pure orchestrator** — it holds only memory tools and routes requests to specialized sub-agents via ADK's auto-injected `transfer_to_agent`. Each sub-agent owns its domain tools and returns control by calling `transfer_to_agent(agent_name='beto')`.

```
                              beto (orchestrator + Telos project hierarchy)
                                    │
     ┌─────────┬──────────┬─────────┬─────────┬──────────┐
     │         │          │         │         │          │
   casa     planner     comms     axel     kidsvid    scout
  (smart   (calendar  (email +  (execution (children   (research +
   home +   schedule + Jira)     + infra)  video       design
   media +  reminders +          curation)   collab)
   music +  webhooks)
   grocery)
                                                  │
                              scout also peers with search_agent
                              & code_execution_agent (ADK built-ins)
```

Beto owns **all project/task management directly** via Telos tools (projects, milestones, project_tasks, explorations). The earlier tracker sub-agent + `tools/todo` module have been retired — webhooks moved to planner.


**Key architectural refinements (post-2026-03-22):**

- `scope_sub_agent_context_callback` (before-model callback on every sub-agent) trims LLM input to the *current user turn only*. Prevents context bleed (e.g. Casa volunteering movie cards because an earlier turn mentioned movies) and keeps sub-agent prompts from growing linearly with session length. Root Beto keeps full history for conversational coherence. See `radbot/callbacks/scope_to_current_turn.py`.
- `/api/agents/agent-info` walks `root_agent.sub_agents` at runtime to return the live roster (name, config key, resolved model, gemini_only flag) — the frontend admin palette reads this instead of a hard-coded list.
- Agents emit **structured UI cards** via fenced code blocks (`` ```radbot:<kind> ``). Casa ships `show_media_card`, `show_season_breakdown`, `show_ha_device_card`; kidsvid ships `show_video_card` (kid-video cards with ADD TO KIDEO button). Every `agent_transfer` event is also auto-wrapped as a `radbot:handoff` block by `session_runner.py` — no LLM call needed. See `radbot/tools/shared/card_protocol.py`.

## Agent Summary

| Agent | Factory | Model | Tool Count | Purpose |
|-------|---------|-------|------------|---------|
| **beto** | `agent/agent_core.py` | `config_manager.get_main_model()` (default `gemini-2.5-pro`) | 29 | Orchestrator, routes to specialists; owns Telos (persistent user context + project hierarchy) |
| **casa** | `agent/home_agent/factory.py` | `resolve_agent_model("casa_agent")` | ~37 | Smart home, media, music, grocery, card emission |
| **planner** | `agent/planner_agent/factory.py` | `resolve_agent_model("planner_agent")` | 17 | Calendar, scheduling, reminders, webhooks |
| **comms** | `agent/comms_agent/factory.py` | `resolve_agent_model("comms_agent")` | 12 | Email (Gmail), Jira |
| **axel** | `agent/execution_agent/factory.py` | `config_manager.get_agent_model("axel_agent_model")` | 17+ MCP | Shell, files, code exec, Claude Code, Nomad, MCP |
| **kidsvid** | `agent/youtube_agent/factory.py` | `resolve_agent_model("kidsvid_agent")` | 18 | Children's video curation (YouTube + CuriosityStream + Kideo + video card) |
| **scout** | `agent/research_agent/factory.py` | `config_manager.get_agent_model("scout_agent")` (`gemini-3.1-pro-preview`) | 17 | Research + planning; writes plans to Telos (exploration + project_tasks). Selectable as session root (see "Session Roots" below). |
| **search_agent** | `tools/adk_builtin/search_tool.py` | Gemini 2+ (hardcoded) | 1 | Google Search grounding |
| **code_execution_agent** | `tools/adk_builtin/code_execution_tool.py` | Gemini 2+ (hardcoded) | 0* | Python code execution |

\* Uses `code_executor=BuiltInCodeExecutor()`, not FunctionTools.

## Root Agent — beto

- **Temperature**: 0.2
- **Global instruction**: injects today's date
- **Tools**: `search_agent_memory`, `store_agent_memory` (via `create_agent_memory_tools("beto")`) + 27 Telos tools (`TELOS_TOOLS`, see `specs/tools.md`; includes projects / milestones / project_tasks / explorations hierarchy tools)
- **Before-agent callback**: `setup_before_agent_call` — DB schema init (scheduler, webhook, reminder, telos, notifications, alerts, telemetry), HA client check
- **Before-model callbacks**: `[scrub_empty_content_before_model, sanitize_before_model_callback, sanitize_tool_schemas_before_model, inject_telos_context]`
- **After-model callbacks**: `[handle_empty_response_after_model, telemetry_after_model_callback]`
- **Instruction file**: `config/default_configs/instructions/main_agent.md`
- **Telos persona injection** (beto only): `inject_telos_context` appends an anchor (~300B: identity + mission + counts + tool pointer) to `llm_request.config.system_instruction` on every turn. On the first turn of each session it also appends the full block (~2KB: mission, problems, goals, active projects, challenges, wisdom, last 5 journal entries), gated by `callback_context.state["telos_bootstrapped"]`. Sub-agents are tool executors and do **not** receive Telos context. See `docs/implementation/telos.md`.
- **Full conversation history**: root keeps all prior turns (unlike sub-agents, which are scoped to the current turn)

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
| Card protocol | 3 | `radbot.tools.shared.card_protocol` (`show_media_card`, `show_season_breakdown`, `show_ha_device_card`) |
| Memory | 2 | `create_agent_memory_tools("casa")` |

Emits UI cards inline with replies. Casa ships the movie/TV/HA card tools; kidsvid ships `show_video_card` for kid-video cards.

### planner — Calendar, Scheduling, Reminders, Webhooks

| Tool Group | Count | Source |
|------------|-------|--------|
| Time | 1 | `radbot.tools.basic.get_current_time` |
| Calendar | 5 | `list_calendar_events`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event`, `check_calendar_availability` |
| Scheduler | 3 | `radbot.tools.scheduler.SCHEDULER_TOOLS` |
| Reminders | 3 | `radbot.tools.reminders.REMINDER_TOOLS` |
| Webhooks | 3 | `radbot.tools.webhooks.WEBHOOK_TOOLS` (moved here when the tracker sub-agent was retired) |
| Memory | 2 | `create_agent_memory_tools("planner")` |

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
| Card protocol | 1 | `show_video_card` (from `radbot.tools.shared.card_protocol`) — emits `radbot:video` block rendered as `<VideoCard />` with ADD TO KIDEO button |

YouTube Shorts are filtered out at ingest time in `kideo_tools.py` (both search and Kideo submission paths).

### scout — Research & Planning

| Tool Group | Count | Source |
|------------|-------|--------|
| Memory | 2 | `create_agent_memory_tools("scout")` |
| Wiki (read-only) | 3 | `radbot.tools.wiki.WIKI_TOOLS` (`wiki_list`, `wiki_search`, `wiki_read`) — wraps `radbot.mcp_server.tools.wiki` handlers |
| Web research | 1 | `radbot.tools.web_research.WEB_RESEARCH_TOOLS` (`web_fetch` — guardrailed fetch with strict sanitization; PT19 tracks adding raw search) |
| Telos subset | 11 | `radbot.tools.telos.SCOUT_TELOS_TOOLS` — read (`telos_get_section/entry/full`, `telos_search_journal`, `telos_list_projects`, `telos_get_project`, `telos_list_tasks`) + plan writes (`telos_add_exploration`, `telos_add_task`, `telos_add_milestone`, `telos_add_journal`) |

- **Instruction file**: `config/default_configs/instructions/scout.md` (loaded via `config_manager.get_instruction("scout")`; falls back to the Python `RESEARCH_AGENT_INSTRUCTION` only if the file is missing)
- **Special**: `enable_sequential_thinking=True`; wrapped by `ResearchAgent` class
- **Session-root capable**: see **Session Roots** below
- **Telos persona**: scout gets `inject_telos_context` when she runs as a session root (plans must be grounded in identity/mission/goals); the sub-agent instance does not
- **Output contract**: a plan is always persisted as a Telos exploration (`EX<N>`), with actionable steps split out as `telos_add_task` rows (`PT<N>`). Handoff to execution is external: Perry invokes Claude Code with MCP pointing at radbot, which fetches the exploration + tasks by ref. No transfer_to_agent('axel') for plan execution.

**Note**: scout does **not** hand plans off to axel inside the agent tree. Axel's role is narrowed to quick-fix alert remediation (see axel section).

## Session Roots (2026-04-19)

Chat sessions can run with either **beto** or **scout** as the root agent. The choice is stored on `chat_sessions.agent_name` (immutable for a session's lifetime, because the ADK session-service partition is keyed by `app_name`) and selected via a UI toggle at create time.

- **beto session** (default) — full orchestrator tree; routes to any sub-agent (casa, planner, comms, axel, kidsvid, scout-as-subagent, search_agent, code_execution_agent). Used for general chat and cross-domain work.
- **scout session** — skips beto's routing layer for extended back-and-forth planning. Scout is root with her own minimal tree (just `search_agent` as sub-agent for grounded Google). No re-routing tax per turn, full conversation history stays with scout.

Registry: `radbot.agent.agent_core.ROOT_AGENTS` maps `agent_name` → root agent object. `get_root_agent(name)` resolves it, falling back to beto on unknown names.

Scout is a **second Python instance** when acting as root (ADK binds each sub-agent to one parent). `agent_core.py` constructs both:

- `scout_agent = create_research_agent(name="scout", as_subagent=False)` — beto's sub-agent (for quick research detours mid-beto-chat)
- `scout_root_agent = create_research_agent(name="scout", as_root=True, sub_agents=[scout_search_agent])` — root of scout sessions

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
3. `create_specialized_agents()` builds the domain agents in order: casa → planner → comms → axel → kidsvid. None-returning factories are filtered out.
4. `all_sub_agents` = builtin sub-agents + specialized — passed to the root `Agent(...)` constructor
5. **Before construction**, callbacks are attached to each sub-agent:
   - `before_model_callback = [scope_sub_agent_context_callback, scrub_empty_content_before_model, sanitize_tool_schemas_before_model]`
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
| Calendar, reminders, scheduled tasks, webhooks, time queries | `planner` |
| Project / milestone / task / exploration work | `beto` (direct via Telos tools) |
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
| `sanitize_tool_schemas_before_model` | `callbacks/sanitize_tool_schemas.py` | all (before_model) | Strip the non-standard `additional_properties` key from every tool's parameters schema before it hits Gemini. Works around the Pydantic→Schema-proto snake-case leak from google-genai 1.72.0 that Gemini validators reject with HTTP 400 INVALID_ARGUMENT. Surfaces on any agent with `Optional[Dict[...]]` or `Optional[List[...]]` tool params (e.g. Telos's `telos_add_entry.metadata`). |
| `inject_telos_context` | `tools/telos/callback.py` | beto only (before_model) | Inject Telos anchor every turn + full block on first turn of session into `system_instruction` |
| `handle_empty_response_after_model` | `callbacks/empty_content_callback.py` | all (after_model) | Replace empty model responses with a "still thinking" marker |
| `telemetry_after_model_callback` | `callbacks/telemetry_callback.py` | all (after_model) | Record token usage + cost in `llm_usage_log` with `session_id` |
| `tool_call_repair_callback` | `callbacks/tool_call_repair_callback.py` | (available, not wired by default) | Repair malformed function calls |

## Key Files

| File | Purpose |
|------|---------|
| `agent/agent_core.py` | Root agent creation, sub-agent assembly, callback wiring |
| `agent/agent_tools_setup.py` | DB schema init callback, search/code/scout creation |
| `agent/specialized_agent_factory.py` | Domain agent creation (casa, planner, comms, axel, kidsvid) |
| `agent/{domain}_agent/factory.py` | Per-domain agent factory function |
| `agent/shared.py` | `load_agent_instruction`, `resolve_agent_model`, task/transfer instruction helpers |
| `config/default_configs/instructions/*.md` | Agent instruction files (main_agent.md, casa.md, planner.md, comms.md, axel.md, scout.md, kidsvid.md) |
| `tools/adk_builtin/search_tool.py` | `search_agent` factory |
| `tools/adk_builtin/code_execution_tool.py` | `code_execution_agent` factory |
| `callbacks/scope_to_current_turn.py` | Per-turn context scoping for sub-agents |
| `callbacks/sanitize_tool_schemas.py` | Strip the non-standard `additional_properties` key from tool parameter schemas before Gemini rejects them |
| `tools/telos/callback.py` | Inject Telos user-context into beto's `system_instruction` (anchor every turn, full block session-start) |
| `tools/shared/card_protocol.py` | `radbot:<kind>` fenced-block card emission |
