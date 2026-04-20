# Storage

## PostgreSQL

Shared pool from `radbot/tools/todo/db/connection.py` (`get_db_pool()`, `get_db_cursor()`, `get_db_connection()`).

### Main DB Tables

| Table | Module | Key columns |
|-------|--------|-------------|
| `tasks` | `tools/todo/db/schema.py` | `task_id` (UUID), `project_id`, `title`, `status` (backlog/inprogress/done), `related_info` (JSONB) |
| `projects` | `tools/todo/db/schema.py` | `project_id` (UUID), `name` (UNIQUE), `wiki_path` (TEXT, nullable — relative path under `$RADBOT_WIKI_PATH`), `path_patterns` (TEXT[], cwd substrings used by MCP `project_match`) |
| `scheduled_tasks` | `tools/scheduler/db.py` | `task_id` (UUID), `name`, `cron_expression`, `prompt`, `agent_name` (TEXT NOT NULL DEFAULT 'beto' — pins cron to a root agent; engine fires through `scheduler-offline-<agent_name>` session), `enabled`, `metadata` (JSONB) |
| `scheduler_pending_results` | `tools/scheduler/db.py` | `result_id` (UUID), `task_name`, `prompt`, `response`, `session_id`, `delivered` |
| `reminders` | `tools/reminders/db.py` | `reminder_id` (UUID), `message`, `remind_at` (TIMESTAMPTZ), `status`, `delivered` |
| `telos_entries` | `tools/telos/db.py` | `entry_id` (UUID), `section` (identity/mission/problems/goals/projects/challenges/wisdom/predictions/journal/…), `ref_code` (e.g. `G1`, `P2`, `ME`), `content`, `metadata` (JSONB — section-specific fields), `status` (active/completed/archived/superseded), `sort_order`, UNIQUE (section, ref_code) |
| `webhook_definitions` | `tools/webhooks/db.py` | `webhook_id` (UUID), `name` (UNIQUE), `path_suffix` (UNIQUE), `prompt_template`, `secret` |
| `radbot_credentials` | `credentials/store.py` | `name` (PK), `encrypted_value`, `salt`, `credential_type` |
| `coder_workspaces` | `tools/claude_code/db.py` | `workspace_id` (UUID), `owner`, `repo`, `branch`, `local_path`, `status`, `last_session_id`, `name`, `description` |
| `alert_events` | `tools/alertmanager/db.py` | `alert_id` (UUID), `fingerprint`, `alertname`, `status`, `severity`, `instance`, `raw_payload` (JSONB), `remediation_action`, `remediation_result` |
| `alert_remediation_policies` | `tools/alertmanager/db.py` | `policy_id` (UUID), `alertname_pattern`, `action`, `max_auto_remediations`, `window_minutes`, `enabled` |
| `notifications` | `tools/notifications/db.py` | `notification_id` (UUID), `type` (`scheduled_task`/`reminder`/`alert`/`ntfy_outbound`/`ntfy_inbound`), `title`, `message`, `source_id`, `session_id`, `priority`, `read` (BOOLEAN), `metadata` (JSONB), `created_at` |
| `llm_usage_log` | `telemetry/db.py` | `id`, `created_at`, `agent_name`, `model`, `prompt_tokens`, `cached_tokens`, `output_tokens`, `cost_usd`, `cost_without_cache_usd`, `session_id` (nullable), `run_label` |
| `telemetry_events` | `tools/telemetry/db.py` | `event_id` (UUID), `event_type` (TEXT), `payload` (JSONB — integers/bools only, validated by strict Pydantic), `created_at` (TIMESTAMPTZ). Append-only baseline metrics for Dream + Context Injection (PT30 / EX7). No retention cron — payloads are tiny and kept indefinitely for longitudinal tracking. |
| `session_workers` | `worker/db.py` | `session_id` (UUID PK), `nomad_job_id`, `worker_url`, `status` (starting/healthy/stopped), `image_tag` |
| `workspace_workers` | `worker/db.py` | `workspace_id` (UUID PK), `nomad_job_id`, `worker_url`, `status` (starting/healthy/stopped), `image_tag` |

### Chat History DB (separate pool)

Uses the `radbot_chathistory` database with its own pool in `web/db/connection.py`.

| Table | Module | Key columns |
|-------|--------|-------------|
| `chat_sessions` | `web/db/chat_operations.py` | `session_id` (UUID), `name`, `description`, `user_id`, `preview`, `is_active`, `agent_name` (TEXT NOT NULL DEFAULT 'beto' — root agent for the session; immutable after creation, partitions the ADK session-service) |
| `chat_messages` | `web/db/chat_operations.py` | `message_id` (UUID), `session_id`, `role`, `content`, `agent_name`, `metadata` (JSONB) |

### Indexes Worth Knowing

| Table | Index | Purpose |
|-------|-------|---------|
| `notifications` | `idx_notifications_type`, `idx_notifications_unread` (partial on `read=FALSE`), `idx_notifications_created (DESC)` | Feed filtering |
| `llm_usage_log` | `idx_llm_usage_log_created (created_at DESC)`, `idx_llm_usage_log_label` | Rolling cost queries + session filters |
| `telos_entries` | `idx_telos_section_status`, `idx_telos_active` (partial on `status='active'`), `idx_telos_journal_recent (created_at DESC)` (partial on `section='journal'`) | Loader (always-loaded section queries) + journal recency |

### Schema Init

All schemas idempotent via `init_*_schema()` with `CREATE TABLE IF NOT EXISTS` (or the `init_table_schema()` helper in `tools/shared/db_schema.py`). Called from:

- `agent_tools_setup.py:setup_before_agent_call()` — beto-side schema init (todo, scheduler, webhook, reminder, telos, telemetry, notifications, llm_usage_log, alerts)
- `web/app.py:initialize_app_startup()` — web-side schema init (session workers, workspace workers, chat history)
- `worker/__main__.py` — worker-side schema init (calls directly, not via ADK callback)

## Qdrant

Semantic memory via `radbot/memory/enhanced_memory/`.

- **Collection**: `radbot_memories` (prod) / `radbot_dev` (when `RADBOT_ENV=dev`)
- **Embedding model**: `gemini-embedding-001` with `output_dimensionality=768`
- **Scoping**: Per-agent memory via `source_agent` tag (see `create_agent_memory_tools()`)
- **User ID**: Fixed `"web_user"` across all sessions (single-user system)
- **Indexed payload fields**: `user_id`, `timestamp`, `memory_type`, `source_agent`, `memory_class` (all KEYWORD except `timestamp` which is DATETIME)

### Memory type taxonomy (EX4)

Each Qdrant point carries two orthogonal tags:

- `memory_type` — content category (`conversation_turn`, `user_query`, `important_fact`, `user_preference`, `general`, …). Used by existing filters.
- `memory_class` — trust/decay taxonomy: `episodic` (things that happened; default), `implicit` (inferred, agent-written), `explicit` (user-stated, durable).

Default at write time: `_create_memory_point` stamps `memory_class="episodic"` when metadata omits it. `store_important_information` / `store_agent_memory` default to `"explicit"` since they're user-authorized writes. Points written before EX4 have no `memory_class` in payload; `search_memory` treats them as `episodic` on read, so no migration is required.

`search_memory` accepts `filter_conditions["memory_class"]` as either a single string (MatchValue) or a list (MatchAny). Agent-facing search tools (`search_past_conversations`, `search_agent_memory`) accept a `memory_class` parameter (str or list, `"all"` disables the filter).

## Credential Store

`radbot/credentials/store.py` — Fernet-encrypted values in `radbot_credentials` table.

- Key: `RADBOT_CREDENTIAL_KEY` env var
- Access: `get_credential_store().get("key_name")`
- Admin UI: `/admin/` manages credentials + `config:<section>` entries

Notable keys:

- `mcp_token` — bearer token for the MCP bridge HTTP transport. Rotatable from admin UI (`POST /api/mcp/token/rotate`); generated via `secrets.token_urlsafe(32)`. Store value wins over `RADBOT_MCP_TOKEN` env var.
- Integration keys (`overseerr_api_key`, `lidarr_api_key`, etc.) — see `specs/integrations.md`.

### Known Credential Keys (non-exhaustive)

| Key | Used by |
|-----|---------|
| `overseerr_api_key`, `lidarr_api_key` | Casa integrations |
| `ha_token` | Home Assistant |
| `picnic_username`, `picnic_password`, `picnic_country_code`, `picnic_auth_token` | Picnic |
| `jira_api_token`, `jira_email` | Jira |
| `gmail_token_<account>`, `calendar_token` | Google OAuth tokens (JSON) |
| `ntfy_token`, `ntfy_topic` | ntfy.sh |
| `github_app_private_key` | GitHub App |
| `nomad_token` | Nomad ACL |
| `claude_code_oauth_token` | Claude Code CLI |
| `youtube_api_key`, `curiositystream_api_key`, `kideo_*` | kidsvid integrations |
| `postgres_pass` | Bootstrap-templated to worker jobs |

## Two Worker Tables (2026-03-22/23)

Commits `4719880` + `f988aca` introduced two distinct worker kinds:

- **`session_workers`** — chat-session workers (keyed by `session_id`). Not used for routing chat anymore (see `specs/web.md`), but schema retained for historical/backward-compat.
- **`workspace_workers`** — terminal workspace workers (keyed by `workspace_id`). Used when a user opens a terminal session for a cloned workspace. Each workspace gets a persistent Nomad service job, proxied by `WorkspaceProxy` in `web/api/terminal_proxy.py`.

Operations on both tables: `upsert_worker`, `get_worker`, `update_worker_status`, `touch_worker`, `list_active_workers`, `count_active_workers`, `delete_worker`.

## Schema Drift / Migrations

No formal migration tool — all schemas use `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idempotently on startup. Schema changes should:

1. Update the table's `init_*_schema()` with `IF NOT EXISTS` clauses for new columns
2. Guard reads against missing columns during the migration window
3. Update this spec
