# Config

## Priority (highest → lowest)

1. DB config (`config:<section>` entries merged by `config_loader.load_db_config()`)
2. File config (`config.yaml` / `config.dev.yaml`)
3. Credential store (encrypted values by name)
4. Environment variables (`RADBOT_MAIN_MODEL`, `OVERSEERR_URL`, etc.)

## config.yaml (bootstrap only)

```yaml
database:          # PostgreSQL connection (host, port, user, password, db_name)
credential_key:    # Fernet encryption key for credential store
admin_token:       # Admin API bearer token
```

**Do NOT add integration config to `config.yaml`.** Everything else goes in the DB credential store, managed via Admin UI at `/admin/`.

## DB Config Sections

Stored as `config:<section>` entries in `radbot_credentials` table.

| Section | Keys | Purpose |
|---------|------|---------|
| `config:agent` | `main_model`, `sub_model`, `session_mode`, `max_session_workers`, `worker_image_tag` | Agent model selection + session worker config |
| `config:integrations` | `overseerr.*`, `picnic.*`, `nomad.*`, `ntfy.*`, `github.*` | Integration endpoints and flags |
| `config:scheduler` | `enabled` | Scheduler engine toggle |
| `config:webhooks` | `enabled` | Webhook engine toggle |
| `config:tts` | `enabled`, `voice`, `language_code` | TTS settings |
| `config:stt` | `enabled`, `language_code` | STT settings |

## Session Mode Config

| Key | Values | Default | Effect |
|-----|--------|---------|--------|
| `session_mode` | `local`, `remote` | `local` | `local` = in-process SessionRunner; `remote` = Nomad batch job workers |
| `max_session_workers` | integer | `10` | Max concurrent remote workers |
| `worker_image_tag` | string | `latest` | Docker tag for worker containers |

## Integration Client Pattern

Follow `radbot/tools/overseerr/overseerr_client.py:30-58`:

```python
def _get_config() -> dict:
    from radbot.config.config_loader import config_loader
    cfg = config_loader.get_integrations_config().get("service", {})
    url = cfg.get("url") or os.environ.get("SERVICE_URL")
    api_key = cfg.get("api_key") or os.environ.get("SERVICE_API_KEY")
    if not api_key:
        from radbot.credentials.store import get_credential_store
        api_key = get_credential_store().get("service_api_key")
    return {"url": url, "api_key": api_key, "enabled": cfg.get("enabled", True)}
```

## Hot-Reload

Admin UI → `PUT /api/config/{section}` → `config_loader.load_db_config()` → client `reset_*_client()` singleton reset → next tool call picks up new config.

## Key Files

| File | Purpose |
|------|---------|
| `config/config_loader.py` | ConfigLoader with DB merge, `get_integrations_config()` |
| `config/schema/config_schema.json` | JSON schema for validation |
| `credentials/store.py` | Encrypted credential store (PostgreSQL-backed) |
| `web/api/admin.py` | Admin API: save/test/status endpoints |
