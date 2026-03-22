# RadBot Spec

## Quick Ref
- Stack: Google ADK 1.27.2 | FastAPI | React 18 | PostgreSQL | Qdrant | MCP | A2A
- Entry: `python -m radbot.web` (web) | `python -m radbot` (CLI) | `python -m radbot.worker` (session worker)
- Pkg: uv — always `uv run`
- Main agent: beto (90s SoCal personality, pure orchestrator)

## Specs
| Domain | File | Covers |
|--------|------|--------|
| Agents | specs/agents.md | beto routing, sub-agents, tool assignments, memory scoping |
| Tools | specs/tools.md | FunctionTool modules, MCP, tool patterns |
| Web | specs/web.md | FastAPI, React SPA, API routes, WS protocol, session modes |
| Storage | specs/storage.md | PostgreSQL tables, Qdrant, credential store |
| Integrations | specs/integrations.md | HA, Overseerr, Picnic, Jira, Gmail, ntfy, Ollama, GitHub |
| Config | specs/config.md | cfg system, priority chain, session mode, admin UI, hot-reload |
| Deployment | specs/deployment.md | Docker, Nomad, CI/CD, session workers, env vars |

## Cross-Cutting

- **Session persistence**: Two modes — `local` (in-process, state lost on restart) and `remote` (Nomad batch jobs, state survives restarts). See `specs/deployment.md` and `specs/web.md`.
- **Config priority**: DB config > file config > credential store > env vars. See `specs/config.md`.
- **Error pattern**: Agent tools return `{"status": "success/error", ...}` dicts.
- **Logging**: Structured JSON via `radbot/logging_config.py`. One INFO per operation, DEBUG for hot loops.
