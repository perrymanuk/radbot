# Home Assistant MCP Migration

<!-- Status: shipped | See also: docs/plans/ha_alias_learning.md (follow-up) -->

## What changed

Casa's Home Assistant tool surface moved from 6 hand-rolled REST FunctionTools to the tools HA itself exposes through its built-in `mcp_server` core integration (HA 2025.2+). The REST tools stay in the tree as a fallback path, gated by `integrations.home_assistant.use_mcp` (default `true`).

## Why

### Capability

The REST tool set only supported `turn_on` / `turn_off` / `toggle` per entity. Everything else — brightness, color, climate temperature, media search, volume, vacuum, fan speed, timers, broadcast TTS, scenes, user scripts — was unreachable from radbot.

HA's `mcp_server` exposes the full **Assist LLM API** as MCP tools. On Perry's HA (probed live at `http://192.168.50.104:8123`, HA 2026.4.1): 19 built-in intent tools plus 18 user-exposed scripts, 37 total. Concrete intents now reachable include `HassLightSet` (brightness/color/temperature), `HassClimateSetTemperature`, `HassMediaSearchAndPlay`, `HassSetVolume`, `HassVacuumStart`, `HassFanSetSpeed`, `HassBroadcast`, `HassStartTimer`, `GetLiveContext`, plus every user script (`morning_heat`, `water_plants`, `start_plex`, `executa_hisense_*`, …) with zero radbot-side code.

### Search / resolution

Previously: LLM called `search_ha_entities(search_term)` → radbot string-matched on an in-memory snapshot of all entities → returned candidate list → LLM picked one → called `turn_*_ha_entity(entity_id)`. Two LLM roundtrips every time.

With MCP: HA's intent resolver (`MatchTargets`) is invoked by the action tool itself. The LLM emits `HassTurnOff(name="basement plant", domain=["light","switch"])` and HA's resolver handles name, area, floor, domain-array, device-class, and alias matching natively. One roundtrip typical; on ambiguity HA returns a structured `MatchFailedError` the LLM can retry with a narrower filter.

The `domain: string[]` parameter is the critical feature: a phrase like "basement plant lights" that could resolve to `light.*` or `switch.*` (common when growlights are actually smart outlets with bulbs) is handled in one call by expanding the domain array.

### Exposure model

HA gates the MCP tool surface by "Expose to Assist" (Settings → Voice assistants → Expose). Only exposed entities appear in `GetLiveContext`; only exposed entities are resolvable via action intents. On Perry's HA: 99 exposed entities out of ~500 total, 13 areas. The exposure list is the authoritative "what the LLM is allowed to see," which radbot defers to rather than re-implementing.

### Measured token cost

Live probe against the same HA that casa talks to in production:

| | Before (REST) | After (MCP) |
|---|---|---|
| Tool schema footprint on casa's prompt | 6 tools × ~250B each ≈ 1.5 KB | 37 tools, 9.8 KB total (~2.45K tokens) |
| Entity state "snapshot" call | `list_ha_entities` unbounded, 500+ entities, ~30-50 KB per call | `GetLiveContext`, 99 exposed entities, ~3.25 KB per call (~10× smaller) |
| Startup `list_entities()` in `setup_before_agent_call` | Always fired, full dump | Removed — health check is now just `GET /api/` |

Tool schemas are larger (we're paying for the capability we gained). Per-call state-lookup cost is far smaller. Net effect on typical casa turns is lower prompt size, and much higher capability per turn.

## Architecture

### Transport

HA's `mcp_server` exposes two transports:

- `GET /mcp_server/sse` — SSE transport (original)
- `POST /api/mcp` — **streamable-HTTP** transport (added in 2025.11 line, current MCP spec)

We use streamable-HTTP. It's stateless (no session id, no keepalive, no exit stack) — each JSON-RPC request is independent. That matches both the agent-factory sync bootstrap and the per-call async runtime cleanly.

Why not ADK's bundled `McpToolset`: it targets SSE and returns an `AsyncExitStack` the caller must keep alive across the tool's lifetime. That fits badly with the agent factory (sync context at construction, then ADK's loop runs tools later) and created lifetime bugs in the existing scaffold (`radbot/tools/mcp/mcp_homeassistant.py` runs a throwaway event loop and drops the exit stack — the transport wouldn't survive real use). A 170-line streamable-HTTP client with httpx sidesteps all of it.

### Modules

| File | Purpose |
|---|---|
| `radbot/tools/homeassistant/ha_mcp_client.py` | `HAMcpClient` — streamable-HTTP JSON-RPC client. `list_tools_sync()` for factory-time discovery, `call_tool(name, arguments)` async for runtime invocation. Singleton via `get_ha_mcp_client()` / `reset_ha_mcp_client()`, same config/credential chain as the REST client. |
| `radbot/tools/homeassistant/ha_mcp_tools.py` | `build_ha_mcp_function_tools(client)` — wraps each MCP tool as an ADK `FunctionTool` with `function_schema` translated from MCP's `inputSchema`. Sanitizes HA tool names to valid Python identifiers (user scripts can have leading digits / non-ASCII). Unwraps HA's `{"success": bool, "result": ...}` envelope before returning to the LLM. |
| `radbot/agent/home_agent/factory.py` | Wired — prefers MCP tools, falls back to the REST six if `use_mcp=false` or MCP discovery fails. |
| `radbot/agent/agent_tools_setup.py` | `list_entities()` startup dump removed. HA health check is now just `GET /api/`. |
| `radbot/web/api/admin.py` | `/api/test/home-assistant` now probes REST + MCP and reports tool count. `_INTEGRATION_RESET_REGISTRY` includes `reset_ha_mcp_client` so admin hot-reload clears the singleton. |
| `radbot/web/frontend/src/components/admin/panels/ConnectionPanels.tsx` | Dropped the `mcp_sse_url` input; added a "Use MCP" toggle. URL is derived from the existing `url` field. |

### Config

```yaml
integrations:
  home_assistant:
    enabled: true
    url: http://192.168.50.104:8123/       # same as REST
    # token stored in credential store as `ha_token`
    use_mcp: true                          # default true; false falls back to REST tools
```

The `mcp_sse_url` field is gone — the MCP endpoint is `urljoin(url, "api/mcp")`.

### Tool discovery and naming

`HAMcpClient.list_tools_sync()` runs an `initialize` → `notifications/initialized` → `tools/list` trio at factory time and returns the raw MCP tool list. `build_ha_mcp_function_tools` then:

1. Reads each entry's `name`, `description`, `inputSchema`.
2. Sanitizes `name` to a valid Python identifier (ADK requirement). Original name is kept in the closure used for `tools/call` so the mapping survives sanitization.
3. Produces `FunctionTool(function=<async closure>, function_schema=<JSON schema>)`. ADK sees exactly what it expects — a callable and a schema.
4. On invocation, drops `None` values from the arguments (ADK occasionally passes explicit nulls that HA rejects).
5. Returns the unwrapped `result` on success, or `{"status": "error", "error": ...}` on failure.

### Fallback behaviour

`create_home_agent()` attempts MCP first. If `use_mcp=false`, HA is unconfigured, or `list_tools_sync()` raises (MCP server not loaded in HA, token rejected, etc.), it falls back to importing the REST tool set. There is no mixed mode — a casa agent is all-MCP or all-REST — to avoid doubling the tool surface when both paths work.

## Probed behaviour (live, 2026-04-18)

```
POST /api/mcp  →  {"protocolVersion":"2024-11-05", ... serverInfo:{name:"home-assistant", version:"1.26.0"}, ...}
tools/list     →  37 tools
GetLiveContext →  99 entities across 13 areas, 55% currently unavailable
                  domains: sensor(33) switch(26) binary_sensor(18) light(7) scene(7) fan(4) media_player(2) lock(1) vacuum(1)
HassTurnOff(name="nonexistent zxqw widget", domain=["light","switch"])
               →  isError=true, MatchFailedError{is_match=False, no_match_reason=NAME, ...}
GetDateTime    →  {"date":"2026-04-18","time":"15:58:39","timezone":"CEST","weekday":"Saturday"}
```

## Follow-ups

- **HA alias learning loop** — `docs/plans/ha_alias_learning.md`. Turn recurring fuzzy resolutions ("grow" → area `all grow lights`) into persistent HA entity/area aliases via the WebSocket registry API, with a candidate queue in postgres and human-in-the-loop promotion. Deliberately deferred until we have usage data from the MCP migration in production.
- **Dashboard tools on MCP?** — HA's `mcp_server` doesn't expose Lovelace CRUD. The WS-based dashboard tools stay as-is.
- **Push state updates** — MCP Resources / Notifications aren't implemented in HA yet (tools+prompts only). State changes still need to be polled via `GetLiveContext` or the REST `GET /api/states` path.
