# MCP Bridge — exposing radbot to external MCP clients

## Purpose

Let Claude Code (or any MCP client) running on any of the user's machines
read from and write to radbot's state — Telos, todo, wiki, memory —
without needing radbot to be local. Complements the existing
`radbot/tools/mcp/` module, which is the *consumer* side (radbot calling
external MCP servers). This module is the *server* side.

Primary consumer: Claude Code with a SessionStart hook that auto-injects
project context on `cd` into a registered repo. Secondary consumer: any
future mobile / phone client that wants to reach radbot over HTTPS.

## Directory layout

```
radbot/mcp_server/
├── __init__.py
├── __main__.py          # stdio entrypoint — `uv run python -m radbot.mcp_server`
├── server.py            # MCP Server factory + list_tools / call_tool handlers
├── auth.py              # credential-store + env bearer-token validation
├── http_transport.py    # mounts /mcp/sse and /mcp/messages/ on FastAPI
└── tools/
    ├── __init__.py      # module registry — aggregates all tools() / dispatches call()
    ├── telos.py         # telos_get_full, telos_get_section, telos_get_entry, telos_search_journal
    ├── wiki.py          # wiki_read, wiki_list, wiki_search, wiki_write
    ├── projects.py      # project_match, project_list, project_register, project_get_context
    ├── tasks.py         # list_tasks, list_reminders, list_scheduled_tasks
    └── memory.py        # search_memory
```

## Transports

- **stdio**: `uv run python -m radbot.mcp_server`. For local dev, MCP
  Inspector, or subprocess-style Claude Code config. No auth — the trust
  boundary is the OS user.
- **HTTP/SSE**: `mount_mcp_on_app(app)` attaches `GET /mcp/sse` (event
  stream) and `POST /mcp/messages/` (client→server) to the existing
  FastAPI app. Bearer auth via `RADBOT_MCP_TOKEN` or credential store.

Both transports serve the same `Server` instance produced by
`create_server()`. Tool registration happens once.

## Tool surface

| Tool | Return shape | Notes |
|---|---|---|
| `telos_get_full` | markdown | Canonical Telos render |
| `telos_get_section(section, include_inactive?)` | markdown | Bullets per entry |
| `telos_get_entry(section, ref_code)` | markdown | Header + content + metadata |
| `telos_search_journal(query, limit?)` | markdown | Newest matches first |
| `wiki_read(path)` | markdown | File contents verbatim |
| `wiki_list(glob?)` | markdown | Grouped by dir; 500-entry cap |
| `wiki_search(query, glob?, limit?)` | markdown | `path:line — text` bullets |
| `wiki_write(path, content)` | plain confirmation | Atomic via `.tmp` rename |
| `project_match(cwd)` | plain string (ref_code) | Used by SessionStart hook; empty on miss |
| `project_list()` | markdown table | ref · name · patterns · wiki_path (active Telos projects only) |
| `project_set_path_patterns(ref_code, path_patterns, wiki_path?)` | plain confirmation | Updates `metadata` on an existing Telos project via `metadata_merge` |
| `project_get_context(ref_or_name)` | markdown | Telos content + recent journal entries with matching `related_refs`. PR 2 replaces with full hierarchy render (milestones/tasks/explorations) |
| `list_tasks(status?, project?)` | markdown | Grouped by status |
| `list_reminders(status?)` | markdown | Relative-time phrasing |
| `list_scheduled_tasks()` | markdown table | name · cron · enabled · prompt |
| `search_memory(query, agent_scope?, limit?)` | markdown | Default scope `beto`; `all` to widen |

**Convention:** all tool returns are `TextContent` blocks. Markdown when
there's anything structured; plain single-line text for primitives
(`project_match`) and confirmations (`wiki_write`). Never raw JSON — this
is LLM-facing. JSON consumers use REST at `/api/*`.

## Auth

Lookup order for the HTTP token:

1. Credential store entry `mcp_token` (managed via admin UI)
2. `RADBOT_MCP_TOKEN` env var (bootstrap value from Nomad)

This matches radbot's general config-priority rule: credential store beats
env var. That means rotation from the admin UI takes effect immediately
without redeploying the Nomad job. The env var is the "first-boot" value;
after first rotate it's effectively unused.

If both are unset, `/mcp/sse` returns **503 MCP bridge disabled** and
`/mcp/messages/` rejects all requests. Fail-closed by design.

Rotation: `POST /api/mcp/token/rotate` generates a 32-byte URL-safe token
(`secrets.token_urlsafe`), writes it to the credential store, and returns
it **once**. The admin UI shows it in a one-time reveal modal with a copy
button and a warning that existing clients will 401 until re-provisioned.

## Wiki root

Configured via `RADBOT_WIKI_PATH` env var (default `/mnt/ai-intel` in the
Nomad container). The `wiki_*` tools sanitize every input path:

1. Absolute paths are rejected outright.
2. Relative paths are joined with the root, normalized, then `realpath`'d.
3. The resolved absolute path must start with `<root>/` or equal `<root>`.
4. Symlinks pointing outside the root fail step 3 because `realpath`
   follows them.

Tests cover: parent traversal (`../../../etc/passwd`), absolute paths,
symlinks leading out of root. All return `**Error:** ...` markdown.

## Project registry (Telos-backed)

Projects are the entries in `telos_entries` where `section='projects'` —
the same source of truth beto uses for goal/project context injection.
Each project's `metadata` JSONB carries two optional MCP-bridge fields:

| metadata key | Type | Purpose |
|---|---|---|
| `path_patterns` | list[str] | `cwd` substrings that identify this project. `project_match(cwd)` returns the project whose longest matching pattern wins. |
| `wiki_path` | string | Optional path (relative to wiki root) to the project's wiki page. Consumed by `project_get_context` as a "further reading" link today; PR 2 replaces `project_get_context` with a live hierarchy render and this field becomes purely informational. |

`project_match(cwd)` is the critical read — called by Claude Code's
SessionStart hook on every session start. Returns the project's
**ref_code** (e.g. `P1`) for URL-safe pass-through. Empty result means
"no Telos project claims this cwd" and the hook stays silent.

`project_set_path_patterns(ref_code, path_patterns, wiki_path?)`
attaches MCP-bridge metadata to an existing Telos project via
`metadata_merge`. It does **not** create Telos projects — that path
remains through beto's confirm-required `telos_add_project`, so every
project entry still passes through the regular Telos provenance.

### Deprecated: todo.projects

PR-1 briefly added `wiki_path` + `path_patterns` columns to the
`tools/todo/db/schema.py` `projects` table (a lightweight todo-list
registry, not identity-level projects). Those columns are unused after
this PR; the migration was removed from `init_schema`. Existing DBs keep
the columns harmlessly; new installs don't get them.

### Admin UI

The "MCP Bridge" panel lists the active Telos projects and lets you
inline-edit their `path_patterns` + `wiki_path` by calling
`PUT /api/telos/entry/projects/{ref}` with `metadata_merge`. No
create/delete buttons — those belong in the Telos panel.

## REST endpoints

Two routers under different auth:

**Admin-token-gated** (`/api/mcp/*`) — owned by the React admin panel:

| Method + Path | Purpose |
|---|---|
| `GET /api/mcp/status` | Auth configured, token source, wiki mount check, SSE + setup URLs |
| `GET /api/mcp/token/reveal` | Explicit reveal — returns cleartext token |
| `POST /api/mcp/token/rotate` | Generates + stores + returns new token |

**MCP-token-gated** (`/api/projects/*`) — called by the SessionStart
hook; mirrors the MCP tools so shell scripts can consume them without
an MCP client:

| Method + Path | Purpose |
|---|---|
| `GET /api/projects/match?cwd=<path>` | Returns `{"project": "<ref_code>"}` or `{"project": null}` |
| `GET /api/projects/{ref_or_name}/context.md` | Renders the project context markdown |

Project *listing* and *editing* use the existing `/api/telos/*` routes
(`GET /api/telos/section/projects`, `PUT /api/telos/entry/projects/{ref}`
with `metadata_merge`). Having two write paths for one resource would
guarantee drift.

Plus the MCP-transport endpoints (not under `/api/`, different auth):

| Path | Purpose |
|---|---|
| `GET /mcp/sse` | SSE event stream (bearer → MCP session) |
| `POST /mcp/messages/` | Client → server message posts |
| `GET /setup/claude-code.md` | Unauth'd markdown bootstrap guide (templated base_url) |

## Setup endpoint

`GET /setup/claude-code.md` returns a templated markdown guide that
Claude Code on any new machine can follow to configure itself. Public,
unauth'd (the user hasn't been given a token yet on a fresh machine).
Template variable: `{base_url}`, filled from `request.base_url`.

Flow for the user on a new device:

1. Point Claude Code at the URL: "configure radbot from
   `https://radbot.demonsafe.com/setup/claude-code.md`"
2. Claude walks the 6-step wizard: get token from admin UI → add to
   `~/.claude/settings.json` → install SessionStart hook → (optional)
   mount wiki → install `/park` and `/resume` skills → verify
3. Done in ~60 seconds, no files committed to any repo

## SessionStart hook (Claude Code side)

Minimal shell script at `~/.claude/hooks/radbot-project-context.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${RADBOT_URL:=https://radbot.demonsafe.com}"
[ -z "${RADBOT_MCP_TOKEN:-}" ] && exit 0

project=$(curl -sf -H "Authorization: Bearer $RADBOT_MCP_TOKEN" \
  "$RADBOT_URL/api/projects/match?cwd=$PWD" \
  | jq -r '.project // empty' 2>/dev/null) || exit 0
[ -z "$project" ] && exit 0

curl -sf -H "Authorization: Bearer $RADBOT_MCP_TOKEN" \
  "$RADBOT_URL/api/projects/$project/context.md"
```

Output goes to stdout → Claude Code loads it as session context. Silent
on unknown paths, so it's safe to leave enabled on every machine. Lives
in `~/.claude/settings.json` under `hooks.SessionStart` — **user-level,
never committed to any repo**, so work-repo privacy is preserved.

> Note: `GET /api/projects/match?cwd=...` and
> `GET /api/projects/{name}/context.md` are companion REST endpoints to
> the MCP tools of the same names. They're thin wrappers around the MCP
> tool logic so shell scripts can consume them. Added in this PR's
> admin router (`radbot/web/api/mcp.py`).

## Nomad changes

```hcl
config {
  volumes = [
    "local/config.yaml:/app/config.yaml",
    "${var.shared_dir}ai-intel:/mnt/ai-intel",   # new
  ]
}

env {
  RADBOT_CREDENTIAL_KEY = var.radbot_credential_key
  RADBOT_ADMIN_TOKEN    = var.radbot_admin_token
  RADBOT_MCP_TOKEN      = var.radbot_mcp_token   # new — bootstrap
  RADBOT_WIKI_PATH      = "/mnt/ai-intel"        # new
  RADBOT_CONFIG_FILE    = "/app/config.yaml"
}

variable "radbot_mcp_token" { type = string }
variable "shared_dir"       { type = string }
```

Lives in `~/git/perrymanuk/hashi-homelab/nomad_jobs/ai-ml/radbot/nomad.job`.
Deployed via a separate PR in that repo.

## Testing

Unit tests cover the high-risk paths:

- `tests/unit/test_mcp_server_auth.py` — token lookup priority, 401/503 flows
- `tests/unit/test_mcp_wiki_sanitization.py` — absolute paths, `..`
  traversal, symlinks leading outside root, read/write atomicity
- `tests/unit/test_mcp_setup_endpoint.py` — 200, content-type,
  base_url templating, unauth access

## Deferred to later PRs

- **PR 2 — TELOS hierarchy**: new `milestones`/`explorations`/`project_tasks`
  sections + `telos_render_project(name)`. Replaces the current
  `project_get_context` (reads static wiki file) with the live render.
- **PR 3 — `/park` + `/resume`**: `parked_sessions` table + MCP tools +
  Claude Code skills for cross-device session continuity.
