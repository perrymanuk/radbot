# Web

## Architecture

FastAPI backend (`radbot/web/`) + React SPA frontend (`radbot/web/frontend/`).

| Layer | Stack | Entry |
|-------|-------|-------|
| Backend | FastAPI, uvicorn[standard], Python 3.14 | `python -m radbot.web` |
| Frontend | React 18, Vite 6, TypeScript, Tailwind, Zustand | `make dev-frontend` (dev) / `make build-frontend` (prod) |
| State | Zustand | `stores/app-store.ts` |
| WS | native WebSocket + reconnect | `hooks/use-websocket.ts` |

## Session Modes

**Chat sessions always run in-process** via `SessionRunner` — the `session_mode` config setting no longer affects chat. Remote Nomad workers are now **only used for terminal/workspace sessions**, managed separately by `radbot/web/api/terminal.py` + `terminal_proxy.py`.

This was changed in commit `12e4901` (2026-03-23) to fix `AttributeError` on session_service access when chat was incorrectly routed through `SessionProxy`.

```
Chat:     Browser ◄──WS──► FastAPI app.py ──► SessionRunner ──► ADK Runner ──► root_agent
Terminal: Browser ◄──WS──► FastAPI terminal.py ──► WorkspaceProxy ──► Nomad Worker (PTY only)
```

See `specs/workers.md` for worker/terminal architecture.

### Key Session Files

| File | Purpose |
|------|---------|
| `web/api/session/session_runner.py` | ADK runner, event processing, history loading, card/handoff block injection |
| `web/api/session/session_manager.py` | Per-session `SessionRunner` registry with lock-based TOCTOU guard |
| `web/api/session/dependencies.py` | FastAPI dep: `get_or_create_runner_for_session()` |
| `web/api/session/memory_api.py` | `/api/memory` router for explicit memory store/recall |
| `web/api/session_proxy.py` (legacy) | No longer used for chat — reference only |
| `worker/history_loader.py` | Shared: seeds ADK session from chat DB history |

## WebSocket Protocol

Endpoint: `GET /ws/{session_id}` (handled in `radbot/web/app.py`)

### Client → Server

```json
{"message": "user text"}                    // chat message
{"type": "heartbeat"}                        // keep-alive
{"type": "history_request", "limit": 50}    // request replay
```

### Server → Client (`type` values in use)

| Type | Payload | Purpose |
|------|---------|---------|
| `status` | `{content: "ready"|"thinking"|...}` | Ready / processing / done indicators |
| `events` | `{content: [event, ...]}` | Streaming agent events (tool calls, transfers) |
| `message` | `{content: "text"}` | Final assistant reply |
| `model_response` | `{content, agent_name, ...}` | Model response event |
| `heartbeat` | (empty) | Server echo |
| `history` | `{session_id, messages: [...]}` | Replay of prior session messages |
| `sync_response` | `{messages: [...]}` | Reply to sync request |
| `system` | `{content: "..."}` | System-injected messages |

**Inline UI cards** and **agent handoff chips** travel as fenced code blocks inside `message` payloads — they do NOT use dedicated WS message types. See `specs/tools.md` § `card_protocol`.

## API Routes

All registered in `radbot/web/app.py` via `app.include_router()` / `register_*_router()`.

| File | Prefix | Purpose |
|------|--------|---------|
| `api/sessions.py` | `/api/sessions` | Session CRUD + `GET /{id}/stats` (token/cost totals) + reset |
| `api/messages.py` | `/api/messages` | Chat message history |
| `api/events.py` | `/api/events` | Event log per session |
| `api/agent_info.py` | `/api/agents` + `/api/claude` | Dynamic agent roster (reads live `root_agent.sub_agents`) + Claude metadata |
| `api/session/memory_api.py` | `/api/memory` | Memory store/recall |
| `api/admin.py` | `/admin/api/*` | Config, credentials, test endpoints, hot-reload triggers |
| `api/tasks_api.py` via admin | `/api/tasks` | Todo CRUD (registered elsewhere) |
| `api/scheduler.py` | `/api/scheduler` | Scheduled tasks REST |
| `api/reminders.py` | `/api/reminders` | Reminders REST |
| `api/webhooks.py` | `/api/webhooks` | Webhook definitions + inbound endpoints |
| `api/alerts.py` | `/api/alerts` | Alertmanager ingestion + policies |
| `api/notifications.py` | `/api/notifications` | Unified notification feed (new 2026-04-11) |
| `api/media.py` | `/api/media` | Direct Overseerr/TMDB actions — bypasses agent (new 2026-04-18) |
| `api/videos.py` | `/api/videos` | Direct Kideo actions for kidsvid `<VideoCard />` — bypasses agent |
| `api/ha.py` | `/api/ha` | Direct Home Assistant state + service — bypasses agent (new 2026-04-18) |
| `api/telos.py` | `/api/telos` | Telos user-context store — admin-token-protected CRUD + bulk + markdown import/export + prediction resolve |
| `api/terminal.py` | `/terminal` | Terminal PTY WebSocket + workspace REST |
| `api/terminal_proxy.py` | (helper) | `WorkspaceProxy`: workspace worker lifecycle |
| `api/tts.py` | `/api/tts` | Text-to-speech |
| `api/stt.py` | `/api/stt` | Speech-to-text |
| `api/health.py` | `/health` | Liveness endpoint for Nomad health check |
| `api/malformed_function_handler.py` | (helper) | Malformed-tool-call repair utilities |
| `api/mcp.py` | `/api/mcp` | MCP bridge admin: status, token reveal/rotate, project registry CRUD (admin-token-protected) |
| `api/setup.py` | `/setup` | `GET /setup/claude-code.md` — unauth'd markdown bootstrap guide, base_url templated from request |
| `mcp_server/http_transport.py` | `/mcp/sse`, `/mcp/messages/` | MCP SSE + messages endpoints (bearer-token-protected, 503 when unconfigured) |

## Direct-Action Endpoints (2026-04-18)

Frontend buttons on Casa-rendered UI cards hit these REST endpoints directly — no LLM roundtrip needed for quick actions.

### Media (`/api/media`) — `web/api/media.py`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/media/search?query=X` | `MediaCardData[]` with TMDB `poster_url` (max 15 results) |
| `GET` | `/api/media/{tmdb_id}?media_type=movie\|tv` | Enriched detail (seasons, on-server fractions, content_rating) |
| `POST` | `/api/media/request` | Wraps Overseerr `create_request` — auto-fills all seasons for TV |

### Telos (`/api/telos`) — `web/api/telos.py`

Admin-authed CRUD drives the `TelosPanel` admin UI and supports power-user markdown import/export. Two **unauth'd public read** endpoints feed the `/projects` page (single-user radbot — matches the rest of `/api/*`).

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/telos/projects/summary` | none | Flat list of projects + derived counts (milestone_count, active_task_count, done_task_count). Feeds `/projects` left rail. |
| `GET` | `/api/telos/projects/entries?sections=projects,milestones,project_tasks,explorations,goals&include_inactive=false` | none | Bulk-fetch multiple telos sections in one call. Feeds `/projects` detail panes. Unknown section names are skipped. |
| `GET` | `/api/telos/status` | admin | `{has_identity}` — wizard-vs-editor branch |
| `GET` | `/api/telos/sections` | admin | Per-section active-entry counts + headers |
| `GET` | `/api/telos/section/{section}?include_inactive=false` | admin | Entries in a section |
| `GET` | `/api/telos/entry/{section}/{ref_code}` | admin | Single entry |
| `POST` | `/api/telos/entry/{section}` | admin | Add entry (body: `{content, ref_code?, metadata?, status?, sort_order?}`) |
| `PUT` | `/api/telos/entry/{section}/{ref_code}` | admin | Patch entry (body: `{content?, metadata_merge?, metadata_replace?, status?, sort_order?}`) |
| `POST` | `/api/telos/archive/{section}/{ref_code}` | admin | Soft delete (body: `{reason?}`) |
| `POST` | `/api/telos/bulk` | admin | Atomic multi-section upsert — used by the onboarding wizard (body: `{entries, replace?}`) |
| `POST` | `/api/telos/import` | admin | Merge-or-replace from canonical Telos markdown (body: `{markdown, replace?}`) |
| `GET` | `/api/telos/export` | admin | Current Telos as canonical markdown (text/plain) |
| `POST` | `/api/telos/resolve-prediction/{ref_code}` | admin | Resolve a prediction; auto-adds `wrong_about` on miscalibration (body: `{outcome, actual_value?}`) |

### Home Assistant (`/api/ha`) — `web/api/ha.py`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/ha/state/{entity_id}` | Normalized `HaDevice` (domain-inferred icon, `brightness_pct`, state mapping) |
| `POST` | `/api/ha/service` | `ha_client.call_service()`, returns fresh entity state |

### Kideo videos (`/api/videos`) — `web/api/videos.py`

Powers the ADD TO KIDEO button + library-status pill on kidsvid's `<VideoCard />`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/videos/collections` | Kideo collections for the picker dropdown |
| `GET` | `/api/videos/kideo-status?url=X` | Library status for a video URL (`in_library` / `queued` / `processing` / `not_added`) |
| `POST` | `/api/videos/add-to-kideo` | `{url, collection_id?, generate_tags?}` — adds + (best-effort) AI-tags YouTube videos |

## Per-Session Token Stats (2026-04-18)

`telemetry_after_model_callback` threads `_invocation_context.session.id` into `llm_usage_log.session_id` (new nullable column). Aggregation exposed via:

- `GET /api/sessions/{session_id}/stats` → `SessionStats` (camelCase): `inputTokens`, `outputTokens`, `totalTokens`, `costToday`, `costMonth`, `contextWindow`
- `radbot/telemetry/db.py:get_session_stats(session_id)` — per-session totals + rolling today/month cost
- Known-model context window map in `telemetry/db.py`, 200k default fallback

Frontend calls the stats endpoint after each turn and renders in the chat footer.

## Notifications Feed (2026-04-11)

Unified notification store (`tools/notifications/db.py`) tracks scheduled-task results, reminder deliveries, alert events, and inbound ntfy messages with read/unread state.

Endpoints (`api/notifications.py`, prefix `/api/notifications`):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | List with filters (`type`, `unread_only`, `limit`, `offset`) |
| `GET` | `/unread-count` | Badge count |
| `GET` | `/{notification_id}` | Single notification |
| `POST` | `/{notification_id}/read` | Mark read |
| `POST` | `/read-all` | Bulk read (optional type filter) |
| `DELETE` | `/{notification_id}` | Delete |

Frontend: `pages/NotificationsPage.tsx` — date-grouped feed + a notifications drawer on the chat page.

## Dynamic Agent Info (2026-04-18)

`GET /api/agents/agent-info` walks `root_agent.sub_agents` at request time and returns:

```json
{
  "sub_agents_detail": [
    {"name": "casa", "config_key": "casa_agent", "resolved_model": "gemini-2.5-flash", "gemini_only": false},
    {"name": "search_agent", "config_key": null, "resolved_model": "gemini-2.5-flash", "gemini_only": true},
    ...
  ]
}
```

The admin UI palette reads this to render model pickers dynamically — no hardcoded agent list to maintain.

## Frontend

Build: `make build-frontend` → `radbot/web/static/dist/`
Dev: `make dev-frontend` → Vite at `:5173`, proxies `/api` and `/ws` to FastAPI on `:8000`.

Feature flag: if `static/dist/index.html` exists, FastAPI serves the React SPA; otherwise legacy vanilla JS served from `web/static/` (retained for emergency fallback).

### Pages (`radbot/web/frontend/src/pages/`)

| Page | Purpose |
|------|---------|
| `ChatPage.tsx` | Main chat UI; renders inline cards + handoff chips; calls `/api/sessions/{id}/stats` after each turn |
| `TerminalPage.tsx` | Terminal emulator with workspace search, health indicator, scrollback replay, binary WS protocol, GPU renderer, multi-client WS |
| `NotificationsPage.tsx` | Unified notification feed with date grouping |
| `ProjectsPage.tsx` | Telos project hierarchy viewer — two-pane (list rail + tabbed detail). Routes `/projects` and `/projects/:refCode`. Read-only v1. |
| `AdminPage.tsx` | Admin panels + palette refresh; dynamic agent roster |

Routing uses `react-router-dom` v6 — `App.tsx` wraps the tree in `<BrowserRouter>` with `<Routes>` dispatching to the pages above (fallthrough `*` → `ChatPage`). Deep-linkable tab state on `/projects/:refCode?tab=milestones` via `useSearchParams`.

### Projects Page (`pages/ProjectsPage.tsx`, 2026-04-19)

Visualizes the Telos project hierarchy: project → milestones → tasks (grouped by `metadata.task_status`) + explorations + goals. Parent linkage is read from `metadata.parent_project` / `metadata.parent_milestone` — the DB stays flat, trees are assembled client-side.

- **Data**: `stores/projects-store.ts` (Zustand) — bulk-fetches all 5 sections via `GET /api/telos/projects/entries` + `GET /api/telos/projects/summary` once on mount. Normalized store: `entries: Record<"section:ref_code", TelosEntry>` + `childrenByParent` index. Pure selectors (`selectMilestonesForProject`, `selectTasksForMilestone`, `selectUnmilestonedTasks`, `selectOrphans`, `bucketTasks`) derive hierarchy.
- **Components** (`components/projects/`): `ProjectList` (left rail w/ filter), `ProjectDetail` (tab shell, deep-linked via `?tab=`), `OverviewTab` / `MilestonesTab` / `TasksTab` / `ExplorationsTab` / `GoalsTab`, `MilestoneCard` (collapsible, `done` bucket collapsed by default), `TaskRow`, `EntryMarkdown` (memoized `react-markdown` wrapper).
- **Orphan vs. Unmilestoned**: distinct UX. Orphaned entries (parent ref_code points at a missing project/milestone) → red badge in page header. Unmilestoned tasks (task with `parent_project` but no `parent_milestone`) → warning-styled block inside the project's Milestones tab.
- **Task status buckets**: canonical set is `inprogress | backlog | done`, with a catch-all `other` bucket for non-canonical values (data hygiene surface until the status field is canonicalized in the DB).
- **API client**: `lib/telos-api.ts` — typed fetch wrappers for the two unauth'd read endpoints. No admin bearer.
- **Header link**: `ChatHeader.tsx` PROJ button next to TERM.

### Admin Panel Modules (`components/admin/panels/`)

Flat panel structure (no more grouping superclasses).

| Module | Panels |
|--------|--------|
| `CorePanels.tsx` | `GooglePanel`, `AgentModelsPanel`, `WebServerPanel`, `LoggingPanel` |
| `ConnectionPanels.tsx` | `GmailPanel`, `CalendarPanel`, `JiraPanel`, `OverseerrPanel`, `LidarrPanel`, `HomeAssistantPanel`, `PicnicPanel`, `FilesystemPanel`, `YouTubePanel`, `KideoPanel` |
| `SecurityPanels.tsx` | `SanitizationPanel` |
| `AlertmanagerPanels.tsx` | `NomadPanel`, `AlertmanagerPanel` |
| `AutomationPanels.tsx` | `SchedulerPanel`, `WebhooksPanel` |
| `MediaPanels.tsx` | `TTSPanel`, `STTPanel` |
| `NotificationPanels.tsx` | `NtfyPanel` |
| `DeveloperPanels.tsx` | `GitHubAppPanel`, `ClaudeCodePanel` |
| `InfrastructurePanels.tsx` | `PostgresqlPanel`, `QdrantPanel` |
| `TelemetryPanels.tsx` | `CostTrackingPanel` |
| `TelosPanel.tsx` | `TelosPanel` (wizard for fresh install, editor after — per-section nav, add/edit/archive, prediction resolve, markdown import/export) |
| `MCPPanel.tsx` | `MCPServersPanel` |
| `CredentialsPanel.tsx` | `CredentialsPanel` |
| `RawConfigPanel.tsx` | `RawConfigPanel` |

Registered in `pages/AdminPage.tsx` via `PANEL_MAP`. The sidebar nav catalog
(categories + icons + status keys) lives in
`components/admin/shell/catalog.ts` as `PANEL_CATEGORIES`, decoupled from the
panel registry.

### Admin Shell (`components/admin/shell/`, 2026-04-19 redesign)

The admin area uses a scoped design system (class `admin-scope` on the page
root) with its own palette/font tokens (`--bg`, `--surface`, `--sunset`,
`--crt`, `--mono` = JetBrains Mono, `--pixel` = VT323) defined in
`globals.css`. The shell module exports:

- `icons.tsx` — `<AIcon name=… size={…}/>` with a 46-glyph set (sparkle, cpu,
  server, chart, compass, mail, cart, db, nomad, speaker, mic, bell, alert,
  git, anchor, shield, stack, key, code, plus/close/check/copy/ext/refresh/
  play/pause/edit/trash/eye + chevrons).
- `primitives.tsx` — `SectionCard`, `Field`, `FieldGrid`, `TextInput`,
  `TextArea`, `Select`, `Toggle`, `Button` (primary|default|ghost|danger,
  sm|md|lg), `RefCode`, `StatusDot`, `StatusPill`
  (connected|configured|disconnected|error|neutral), `Empty`, `Note` (info|
  warning|neutral).
- `catalog.ts` — `PANEL_CATEGORIES` (10 groups: CORE, PERSONAL, CONNECTIONS,
  INFRASTRUCTURE, MEDIA & VOICE, NOTIFICATIONS, AUTOMATION, DEVELOPER,
  SECURITY, ADVANCED), `findPanel`, `mapStatus` (maps admin-store raw
  `ok|error|unconfigured` → design-system `PanelStatus`).
- `Sidebar.tsx` — categorized `<AdminSidebar>` with collapsible groups,
  live filter (`filter panels…`), per-panel status dot, active highlight.
- `PanelHeader.tsx` — panel chrome (crumb, icon tile, title, status pill,
  actions slot).

`FormFields.tsx` remains the import surface for panels (`FormInput`,
`FormToggle`, `FormDropdown`, `FormTextarea`, `FormSlider`, `FormRow`,
`Card`, `Note`, `ActionBar`, `StatusBadge`); its internals now delegate to
the shell primitives so restyling flows through every panel automatically.

`AdminPage.tsx` syncs `activePanel` to the `?panel=<id>` query param for
deep-linking. On mobile (<768px) the sidebar is hidden via `.admin-scope
.admin-sidebar-wrap { display: none }`.

### Chat Components (post-refresh 2026-04-18)

- `components/chat/AgentCards.tsx` — renders `MediaCard`, `SeasonBreakdownCard`, `HaDeviceCard`, `VideoCard`, `HandoffLine` (parses ` ```radbot:<kind> ` fenced blocks from message text). `<VideoCard />` is kidsvid's kid-video card with an ADD TO KIDEO direct-action button calling `/api/videos`.
- Terminal refresh: mascot, stats footer, notifications drawer — see commit `9ebfb9f`

### `data-test` attribute convention (for browser e2e)

Stable selectors for Playwright specs use `data-test="kebab-case-region-or-action"`. Naming pattern: `<page-or-feature>-<element>` (e.g. `admin-login-prompt`, `admin-token-input`, `admin-nav-google`, `chat-input`, `chat-send`, `message-assistant`). Prefer these over class/text selectors so frontend restyling doesn't break tests.

Currently seeded:
- `chat-input`, `chat-send` (`components/chat/ChatInput.tsx`)
- `message-assistant`, `message-user`, `message-system` + `data-agent` attribute (`components/chat/ChatMessage.tsx`)
- `admin-login-prompt`, `admin-login-error`, `admin-token-input`, `admin-token-submit`, `admin-dashboard`, `admin-sidebar`, `admin-group-<group>`, `admin-nav-<id>` + `data-status` (`pages/AdminPage.tsx`)

Add a new `data-test` attribute when writing the first spec that needs to assert on the element. Screenshot fixtures live alongside specs at `radbot/web/frontend/e2e/fixtures/screenshot.ts`. See `specs/testing.md` for the full e2e architecture.
