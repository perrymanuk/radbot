# RadBot Spec

## Quick Ref
- Stack: Google ADK 2.0.0a3 (V1 LlmAgent mode) | FastAPI | React 18 | PostgreSQL | Qdrant | MCP | A2A
- Runtime: Python 3.14-slim, `google-adk>=2.0.0a3,<3.0.0`, `google-genai>=1.68.0`
- Entry: `python -m radbot.web` (web) | `python -m radbot` (CLI) | `python -m radbot.worker --workspace-id <UUID>` (terminal worker)
- Pkg: uv — always `uv run`
- Main agent: beto (90s SoCal personality, pure orchestrator)
- Sub-agents: casa, planner, comms, axel, kidsvid, scout + search_agent + code_execution_agent

## Specs
| Domain | File | Covers |
|--------|------|--------|
| Agents | specs/agents.md | beto routing, sub-agents (including kidsvid), tool assignments, memory scoping, per-turn context scoping callback, structured UI cards, handoff chips |
| Tools | specs/tools.md | FunctionTool modules, MCP consumer + bridge server, tool patterns, card protocol, direct-action REST |
| Web | specs/web.md | FastAPI, React SPA, API routes, WS protocol, session modes, admin panels, notifications, token stats, MCP bridge transport |
| Storage | specs/storage.md | PostgreSQL tables (incl. `notifications`, `llm_usage_log`, `workspace_workers`, `projects.wiki_path`/`path_patterns`), Qdrant, credential store (`mcp_token`) |
| Integrations | specs/integrations.md | HA, Overseerr, Lidarr, Picnic, Jira, Gmail, ntfy, Ollama, GitHub, YouTube/CuriosityStream/Kideo |
| Config | specs/config.md | cfg system, priority chain, DB sections, session mode, admin UI, hot-reload, `RADBOT_MCP_TOKEN` + `RADBOT_WIKI_PATH` env vars |
| Workers | specs/workers.md | Workspace/terminal workers, PTY server, Nomad jobs, proxy, legacy session-worker notes |
| Deployment | specs/deployment.md | Docker (main + worker), Nomad, CI/CD, env vars, ai-intel wiki volume mount, `bootstrap-radbot-stack` composite action |
| Testing | specs/testing.md | Playwright e2e suite, selective-affected runner, LLM judge, screenshot fixtures, quality-pipeline workflow + 6 weighted gates, auto-merge at score ≥ 90, CI security model |

## Cross-Cutting

- **Chat session flow**: Always in-process `SessionRunner` with `InMemorySessionService` (last 15 messages replayed from DB on cold start). `session_mode` config now only affects terminal/workspace workers.
- **Terminal workers**: When `session_mode = "remote"`, each cloned workspace gets a persistent Nomad service job running a lean PTY server (`python -m radbot.worker`). Workers survive main-app restarts; state is restored via saved Claude Code session ID.
- **Per-turn context scoping**: Every sub-agent runs `scope_sub_agent_context_callback` before its LLM call — trims prompt to current user turn only. Prevents cross-domain context bleed; keeps token usage flat.
- **UI cards**: Agents (Casa) emit ``` ```radbot:<kind> ``` fenced JSON blocks for `media` / `seasons` / `ha-device` cards. `handoff` blocks are server-injected by `session_runner.py` on every `agent_transfer`. Frontend (`AgentCards.tsx`) parses and renders.
- **Direct-action endpoints**: `/api/media/*` and `/api/ha/*` let the frontend trigger Overseerr + HA actions directly from cards — no LLM roundtrip.
- **Token + cost telemetry**: `telemetry_after_model_callback` writes to `llm_usage_log` with `session_id` threaded through. `GET /api/sessions/{id}/stats` exposes per-session totals + rolling today/month cost.
- **Unified notifications**: `notifications` table aggregates scheduled-task results, reminders, alerts, ntfy inbound. `/api/notifications/*` and `pages/NotificationsPage.tsx` drive the feed + drawer.
- **Telos (persistent user context)**: beto owns a structured persona / context store in `telos_entries`. Sections include identity, mission, problems, goals, **projects + milestones + project_tasks + explorations** (hierarchical project graph, all linked via `metadata.parent_project`), challenges, wisdom, predictions, taste, journal. `inject_telos_context` (on beto only — sub-agents don't get it) appends a ~300B anchor to `system_instruction` every turn and a ~2KB full block on the first turn of each session. One-time onboarding via `uv run python -m radbot.tools.telos.cli onboard`. Beto keeps the file alive via silent tools (journal, predictions, wisdom, taste, complete_task, complete_milestone) and confirm-required tools (goals, mission, problems, add_task, add_milestone, add_exploration). The old `tools/todo` module + tracker sub-agent were removed — project/task management now lives entirely in Telos. See `docs/implementation/telos.md`.
- **MCP bridge** (`radbot.mcp_server`): exposes radbot to external MCP clients (primarily Claude Code on laptop/desktop) over stdio or HTTP/SSE. Tools cover Telos read (incl. projects + project_tasks), wiki read/write (at `$RADBOT_WIKI_PATH`), project registry with path-pattern cwd matching, project-task listings (Telos-backed), scheduler/reminder listings, Qdrant memory search. All tool returns are markdown `TextContent`. HTTP auth: bearer token from credential store (`mcp_token` key, rotatable from admin UI) or `RADBOT_MCP_TOKEN` env var. `GET /setup/claude-code.md` is an unauth'd markdown bootstrap for new-machine config. See `docs/implementation/mcp_bridge.md`.
- **Config priority**: DB config > file config > credential store > env vars. See `specs/config.md`.
- **Error pattern**: Agent tools return `{"status": "success/error", ...}` dicts.
- **Logging**: Structured JSON via `radbot/logging_config.py`. One INFO per operation, DEBUG for hot loops.
- **Quality pipeline**: PRs labelled `run-e2e` trigger `.github/workflows/quality-pipeline.yml` — six weighted gates (functional-e2e 30, visual-regression 20, unit-tests 20, lint 10, build 10, coverage-delta 10) plus required `secret-scan` (gitleaks + trufflehog) and `path-guard`. Aggregate posts a sticky PR comment + commit status `quality-pipeline/score`. PRs labelled `auto-merge-eligible` with score ≥ 90, secret-scan green, and no hard-block paths touched call `gh pr merge --auto --squash`. Hard-block paths (always require human merge): `radbot/credentials/`, `radbot/web/api/admin.py`, `radbot/db/`, `radbot/config/config_loader.py`, `radbot/worker/`, `.github/`, `Makefile`, `Dockerfile*`, `pyproject.toml`, `uv.lock`, `*.sql`. Local fast-loop: `make test-e2e-browser-affected`. CI security: GH `e2e-secrets` environment with required reviewers; `tag:github-actions` Tailscale join for in-network integrations; CI uses a separate Fernet credential key from prod (NEVER share `RADBOT_CREDENTIAL_KEY`). See `specs/testing.md` and `docs/implementation/ci-security.md`.

## Keeping Specs Up To Date

**These specs are the system of record for cross-cutting architecture.** Treat them like schema: every PR that changes shape should update the matching spec in the same commit. See `CLAUDE.md` § Spec Maintenance for the full rule.
