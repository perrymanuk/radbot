# Dev/Production Environment Separation

RadBot supports separate development and production environments sharing the same
homelab infrastructure (PostgreSQL, Qdrant) but using **different databases and
collections** so that dev work never touches production data.

## How It Works

### `RADBOT_ENV` environment variable

Set `RADBOT_ENV=dev` (or any value) to activate an environment-specific config
file. The config loader searches for `config.{env}.yaml` **before** `config.yaml`
in each lookup directory:

1. Explicit path / `RADBOT_CONFIG` / `RADBOT_CONFIG_FILE` env var
2. Current working directory → `config.dev.yaml` then `config.yaml`
3. `~/.config/radbot/` → same pattern
4. Project root → same pattern

If no env-specific file is found, it falls back to `config.yaml` as before.

### Config file alias

Both `RADBOT_CONFIG` and `RADBOT_CONFIG_FILE` are supported as environment
variables pointing to an explicit config file path. This fixes a mismatch where
Nomad sets `RADBOT_CONFIG_FILE` but the code previously only read `RADBOT_CONFIG`.

## Data Separation

| Data store | Production | Development |
|---|---|---|
| PostgreSQL DB | `radbot_todos` | `radbot_dev` |
| Chat history schema | `radbot_chathistory` (in `radbot_todos`) | `radbot_chathistory` (in `radbot_dev`) |
| Qdrant collection | `radbot_memories` | `radbot_dev` |
| Credential key | Production Fernet key | Separate dev Fernet key |
| Integrations (HA, Jira, etc.) | Same external services | Same external services |

## One-Time Setup

### 1. Create the dev database

```sql
CREATE DATABASE radbot_dev;
GRANT ALL PRIVILEGES ON DATABASE radbot_dev TO postgres;
```

### 2. Create `config.dev.yaml`

Copy from the example:

```bash
cp examples/config.dev.yaml.example config.dev.yaml
```

Edit it to fill in your PostgreSQL password (or use `${POSTGRES_PASSWORD}` with
`.env`).

### 3. Migrate credentials from production

The migration script copies all credentials from the prod DB, decrypts them with
the prod key, re-encrypts with a new dev key, and writes them to the dev DB:

```bash
uv run python scripts/migrate_credentials_to_dev.py \
    --prod-db radbot_todos --dev-db radbot_dev \
    --prod-key '<prod_credential_key>'
```

The script generates a new dev credential key and prints it. Put it in
`config.dev.yaml` as `credential_key:` or in `.env` as `RADBOT_CREDENTIAL_KEY`.

### 4. Set the environment

Add to `.env`:

```bash
RADBOT_ENV=dev
```

### 5. Start RadBot

```bash
uv run python -m radbot.web
```

Remaining tables (tasks, scheduled_tasks, chat_sessions, etc.) are auto-created
by the schema init on startup. The Qdrant `radbot_dev` collection is also
auto-created.

## Verification

1. **Startup logs** show the environment banner:
   ```
   ConfigLoader: env=dev, config=/path/to/config.dev.yaml
   RadBot starting  env=dev
     config : /path/to/config.dev.yaml
     database: radbot_dev
     qdrant  : radbot_dev
   ```

2. **Admin UI** — integration configs are present (migrated from prod).

3. **Create a task** in dev — verify it's in `radbot_dev`, not `radbot_todos`.

4. **Without `RADBOT_ENV`** — falls back to `config.yaml` (production).

5. **Nomad deployment** — unaffected (uses `RADBOT_CONFIG_FILE`, no `RADBOT_ENV`).
