# Deployment

## Production

- **Endpoint**: `https://radbot.demonsafe.com`
- **Nomad job**: `~/git/perrymanuk/hashi-homelab/nomad_jobs/ai-ml/radbot/nomad.job`
- **Docker image (main)**: `ghcr.io/perrymanuk/radbot` — auto-built by `.github/workflows/docker-build.yml` on push to `main`
- **Docker image (worker)**: `ghcr.io/perrymanuk/radbot-worker` — separate image, separate Dockerfile (`Dockerfile.worker`), separate build pipeline
- **Versioning**: Auto-incremented `v{MAJOR}.{BUILD}` tags (e.g. `v0.14`). Update the `image` tag in the Nomad job after pushing.
- **Reverse proxy**: Traefik via Consul service discovery. `ProxyHeadersMiddleware` handles `X-Forwarded-Proto`.

## Runtime Environment

- **Python**: 3.14-slim base image for both main app and worker (upgraded in `85a258e`)
- **Package manager**: `uv` — both containers use multi-stage builds with `uv` + GHA layer caching (`c20e8b2`, `c1cbdd8`)
- **ADK**: `google-adk>=2.0.0a3,<3.0.0` with V1 LlmAgent mode (V2 `_Mesh` is being removed upstream — see CLAUDE.md gotchas)
- **genai**: `google-genai>=1.68.0` (NOT the older `google-generativeai` package)
- **Code-exploration binaries** (EX9, runtime stage): `git`, `ripgrep`, `universal-ctags` via apt; `ast-grep` (and the `sg` alias) copied from a dedicated `ast-grep-bin` builder stage that fetches the prebuilt `app-x86_64-unknown-linux-gnu.zip` from the GitHub release pinned by the `AST_GREP_VERSION` build arg. `mkdir /data/repos` creates the in-image jail dir; the Nomad job mounts a persistent volume on top. Stack-graphs was the original choice but the project is archived/source-only — universal-ctags + ast-grep + rg replaces it. Consumed by `radbot/tools/repo_exploration.py` (Scout's read-only repo tools).
- **GitHub CLI** (PT79, runtime stage): `gh` binary copied from a dedicated `gh-cli-bin` builder stage that fetches the prebuilt `gh_${GH_CLI_VERSION}_linux_amd64.tar.gz` tarball (static, no apt repo). Installed at `/usr/local/bin/gh`. `ENV GH_PROMPT_DISABLED=1` prevents interactive prompts from hanging headless agent calls. Global git identity (`user.name=radbot`, `user.email=radbot@local`) is set in the same Dockerfile layer so container-originated commits are attributable. Auth: `/usr/local/bin/gh-token` (sourced from `scripts/gh_token.py`) shells into the in-container Python env, calls `radbot.tools.github.github_app_client.get_github_client()._get_installation_token()`, and prints a fresh GitHub App installation token — callers use `GH_TOKEN=$(gh-token) gh <cmd>`. No persistent gh auth state is stored in the image.

## Bootstrap Config

Nomad templates a minimal `config.yaml` with only `database:` section. All other config loaded from the DB credential store at startup.

| Env var | Purpose |
|---------|---------|
| `RADBOT_CREDENTIAL_KEY` | Fernet key for encrypted credentials in DB |
| `RADBOT_ADMIN_TOKEN` | Bearer token for `/admin/` API |
| `RADBOT_MCP_TOKEN` | Bootstrap bearer for MCP bridge (credential-store `mcp_token` wins when set) |
| `RADBOT_WIKI_PATH` | Wiki root inside the container (default `/mnt/ai-intel`, matches Nomad bind-mount) |
| `RADBOT_CONFIG_FILE` | Path to `config.yaml` (alias: `RADBOT_CONFIG`; Nomad uses the `_FILE` variant) |
| `RADBOT_ENV` | `dev` loads `config.dev.yaml` instead of `config.yaml` |
| `RADBOT_WORKER_IMAGE_TAG` | Overrides `config:agent.worker_image_tag` for newly-spawned workspace workers |

## Main Nomad Job

```
type = "service", count = 1
image: ghcr.io/perrymanuk/radbot:{tag}
port: 8000 (HTTP), host_network = "lan"
constraint: shared_mount = true
service: "radbot" (Traefik-enabled)
health: GET /health every 30s
resources: cpu=1000, memory=2048

volumes:
  - local/config.yaml:/app/config.yaml
  - ${var.shared_dir}ai-intel:/mnt/ai-intel   # ai-intel wiki for MCP bridge
```

### Reverse Proxy Gotchas

- FastAPI behind Traefik generates redirect URLs using the internal HTTP scheme. `ProxyHeadersMiddleware` in `web/app.py` trusts `X-Forwarded-Proto`.
- FastAPI router root paths (`@router.get("/")`) 307-redirect without trailing slash. On HTTPS this can produce `http://` redirects that browsers block as mixed content. **Always use trailing slashes** in frontend fetch calls that hit router root paths.

## Workspace/Terminal Workers (Remote Mode)

When `config:agent.session_mode = "remote"`, each terminal workspace runs as a persistent Nomad **service** job:

- `type = "service"` with `restart: attempts=1, mode=fail`
- Image: `ghcr.io/perrymanuk/radbot-worker:{tag}` (separate from main app)
- Each worker registers with Nomad service discovery (`radbot-workspace`) tagged `workspace_id=<UUID>`
- Bootstrap env templated from the main app's DB credential store (`RADBOT_CREDENTIAL_KEY`, `RADBOT_ADMIN_TOKEN`, `postgres_pass`)
- Pre-spawned on workspace *creation* for instant cold-start on first click (`3e93b63`)

Chat sessions always run in-process — `session_mode` no longer affects chat (`12e4901`).

See **`specs/workers.md`** for full architecture, worker protocol, and file inventory.

## CI/CD

- `.github/workflows/docker-build.yml` — builds main image on push to `main`, tags `v{MAJOR}.{BUILD}`, pushes to GHCR
- Separate worker image pipeline with BuildKit + GHA layer caching
- Image: `ghcr.io/perrymanuk/radbot` (main), `ghcr.io/perrymanuk/radbot-worker` (worker)
- Update the Nomad job's `image` tag after a new version pushes (manual step)
- `.github/workflows/quality-pipeline.yml` — PR gate; opt-in via `run-e2e` label. See `specs/testing.md` for the full gate model.

## CI Stack Bootstrap (`bootstrap-radbot-stack` composite action)

Canonical full-stack spin-up for any workflow that needs a running radbot. Lives at `.github/actions/bootstrap-radbot-stack/action.yml`. Steps in order:

1. **Tailscale connect** (optional, `with_tailscale: true` default) — `tailscale/github-action` with OAuth client id/secret + `tag:github-actions`. Required for in-network integrations (Overseerr, ntfy, Lidarr, Picnic).
2. **Generate `.env`** at repo root from action inputs (`RADBOT_ADMIN_TOKEN`, `RADBOT_CREDENTIAL_KEY`, `RADBOT_EXPOSED_PORT=8001`).
3. **`docker compose up -d --build --wait`** — same compose file as local dev.
4. **Seed credentials + config** — `scripts/seed_credentials_from_env.py` and `scripts/seed_config_from_env.py` read `scripts/e2e_seed_manifest.yml` and POST/PUT to the running stack's admin API at `:8001` using the seeded admin token.
5. **Restart `radbot` container** so it picks up the seeded config:credentials.
6. **`scripts/wait_for_health.py`** polls `/health` with timeout + retry budget — replaces brittle `sleep N`.
7. **Snapshot to job summary** — `/health` body + `docker compose ps`.

Required GH **secrets**: `RADBOT_ADMIN_TOKEN`, `RADBOT_CREDENTIAL_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_SECRET`, optional integration keys (`OVERSEERR_API_KEY`, …). All MUST live in the GH `e2e-secrets` deployment environment with required reviewers.

Required GH **variables** (non-secret URLs): `OVERSEERR_URL`, `NTFY_URL`. Format: `https://host[:port]` (full scheme, no trailing slash, no path — clients append `/api/v1/...`).

Manifest schema (`scripts/e2e_seed_manifest.yml`):
```yaml
credentials:
  - { name: gemini_api_key, env: GEMINI_API_KEY, required: true }
config_sections:
  - section: agent
    fields:
      main_model: { value: "gemini-2.5-flash" }   # literal
      sub_model: { value: "gemini-2.5-flash" }
  - section: integrations
    fields:
      overseerr.url: { env: OVERSEERR_URL, required: false }
```

`required: true` fails the workflow if the env var is absent. `required: false` skips silently and the spec must tolerate the integration being absent.

**CI vs prod credential key:** the same `RADBOT_CREDENTIAL_KEY` secret name is currently used in both — the security note in `docs/implementation/ci-security.md` documents the rotation procedure and the planned move to a CI-only Fernet key. Until that's done, treat any GH Actions compromise as equivalent to prod credential compromise.

## Environment Separation (Dev)

Setting `RADBOT_ENV=dev`:

- Loads `config.dev.yaml` before `config.yaml` in each search directory
- Recommended separate prod/dev: PostgreSQL DB (`radbot_dev`), Qdrant collection (`radbot_dev`)
- Startup banner in `app.py` logs env, config path, database, qdrant collection — check at startup to verify

See `docs/implementation/dev_environment_setup.md` for full procedure.
