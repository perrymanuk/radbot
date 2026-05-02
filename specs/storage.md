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
| `notifications` | `tools/notifications/db.py` | `notification_id` (UUID), `type` (`scheduled_task`/`reminder`/`alert`/`heartbeat`/`ntfy_outbound`/`ntfy_inbound`), `title`, `message`, `source_id`, `session_id`, `priority`, `read` (BOOLEAN), `metadata` (JSONB), `created_at`. Writers: scheduler + reminder + alertmanager + heartbeat paths go via `radbot/services/notifier.py` (`NotificationsTableSink`); `ntfy_inbound` rows still come from `ntfy_subscriber.py` (out of scope for the seam). The `ntfy_outbound` enum value is retained for legacy rows but has no live writer — `ntfy_client.publish()` no longer creates rows (the `skip_notification` leak was removed in EX41 PR3 / PT107). |
| `llm_usage_log` | `telemetry/db.py` | `id`, `created_at`, `agent_name`, `model`, `prompt_tokens`, `cached_tokens`, `output_tokens`, `cost_usd`, `cost_without_cache_usd`, `session_id` (nullable), `run_label` |
| `telemetry_events` | `tools/telemetry/db.py` | `event_id` (UUID), `event_type` (TEXT), `payload` (JSONB — integers/bools only, validated by strict Pydantic), `created_at` (TIMESTAMPTZ). Append-only baseline metrics for Dream + Context Injection (PT30 / EX7). No retention cron — payloads are tiny and kept indefinitely for longitudinal tracking. |
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

- `tools/schemas.py:init_all_schemas()` — fail-loud central registry, invoked once at FastAPI startup (`web/app.py:initialize_app_startup()`) and once per pytest session (autouse fixture in `tests/conftest.py`).
- `worker/__main__.py` — worker-side schema init (calls directly during bootstrap).

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

## Workspace worker table

`workspace_workers` is keyed by `workspace_id` and tracks terminal workspace workers. Each workspace opens a persistent Nomad service job, proxied by `WorkspaceProxy` in `web/api/terminal_proxy.py`. Operations: `upsert_workspace_worker`, `get_workspace_worker`, `update_workspace_worker_status`, `list_active_workspace_workers`, `count_active_workspace_workers`, `delete_workspace_worker`.

The earlier `session_workers` table (chat-session workers, keyed by `session_id`) was retired in EX40 — chat sessions always run in-process via `SessionRunner`. The table is dropped at startup by the EX40 migration in `radbot/tools/schemas.py:MIGRATIONS`.

## Schema Drift / Migrations

Two complementary mechanisms in `radbot/tools/schemas.py`:

- **`SCHEMA_INITS`** — `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Idempotent on every boot.
- **`MIGRATIONS`** — one-shot DDL run after schema inits (e.g. `DROP TABLE IF EXISTS`). Each entry must remain idempotent so re-runs no-op.

Schema changes should:

1. Update the table's `init_*_schema()` with `IF NOT EXISTS` clauses for new columns
2. Guard reads against missing columns during the migration window
3. For drops/renames, append to `MIGRATIONS` rather than removing the init line in the same release
4. Update this spec
