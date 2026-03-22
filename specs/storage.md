# Storage

## PostgreSQL

Shared pool from `radbot/tools/todo/db/connection.py` (`get_db_pool()`, `get_db_cursor()`).

### Main DB Tables

| Table | Module | Key columns |
|-------|--------|-------------|
| `tasks` | `tools/todo/db/schema.py` | `task_id` (UUID), `project_id`, `title`, `status` (backlog/inprogress/done), `related_info` (JSONB) |
| `projects` | `tools/todo/db/schema.py` | `project_id` (UUID), `name` (UNIQUE) |
| `scheduled_tasks` | `tools/scheduler/db.py` | `task_id` (UUID), `name`, `cron_expression`, `prompt`, `enabled`, `metadata` (JSONB) |
| `reminders` | `tools/reminders/db.py` | `reminder_id` (UUID), `message`, `remind_at` (TIMESTAMPTZ), `status`, `delivered` |
| `webhook_definitions` | `tools/webhooks/db.py` | `webhook_id` (UUID), `name` (UNIQUE), `path_suffix` (UNIQUE), `prompt_template`, `secret` |
| `scheduler_pending_results` | `tools/scheduler/db.py` | `result_id` (UUID), `task_name`, `prompt`, `response`, `session_id`, `delivered` |
| `radbot_credentials` | `credentials/store.py` | `name` (PK), `encrypted_value`, `salt`, `credential_type` |
| `coder_workspaces` | `tools/claude_code/db.py` | `workspace_id` (UUID), `owner`, `repo`, `branch`, `local_path`, `status`, `last_session_id`, `name`, `description` |
| `alert_events` | `tools/alertmanager/db.py` | `alert_id` (UUID), `fingerprint`, `alertname`, `status`, `severity`, `instance`, `raw_payload` (JSONB) |
| `alert_remediation_policies` | `tools/alertmanager/db.py` | `policy_id` (UUID), `alertname_pattern`, `action`, `max_auto_remediations`, `window_minutes`, `enabled` |
| `session_workers` | `worker/db.py` | `session_id` (UUID PK), `nomad_job_id`, `worker_url`, `status` (starting/healthy/stopped), `image_tag` |

### Chat History DB (separate pool)

Uses `radbot_chathistory` schema with its own pool in `web/db/connection.py`.

| Table | Module | Key columns |
|-------|--------|-------------|
| `chat_sessions` | `web/db/chat_operations.py` | `session_id` (UUID), `name`, `description`, `user_id`, `preview`, `is_active` |
| `chat_messages` | `web/db/chat_operations.py` | `message_id` (UUID), `session_id`, `role`, `content`, `agent_name`, `metadata` (JSONB) |

### Schema Init

All schemas idempotent via `init_*_schema()` with `CREATE TABLE IF NOT EXISTS`. Called from:
- `agent_tools_setup.py:setup_before_agent_call()` — agent-side tables
- `web/app.py:initialize_app_startup()` — web-side tables

## Qdrant

Semantic memory via `radbot/memory/enhanced_memory/`.

- **Collection**: `radbot` (or `radbot_dev` when `RADBOT_ENV=dev`)
- **Embedding model**: `gemini-embedding-001` with `output_dimensionality=768`
- **Scoping**: Per-agent memory via `source_agent` tag (see `create_agent_memory_tools()`)
- **User ID**: Fixed `"web_user"` across all sessions

## Credential Store

`radbot/credentials/store.py` — Fernet-encrypted values in `radbot_credentials` table.

- Key: `RADBOT_CREDENTIAL_KEY` env var
- Access: `get_credential_store().get("key_name")`
- Admin UI: `/admin/` manages credentials
