# Testing

Authoritative spec for radbot's automated test suite, the Playwright browser e2e layer, and the GitHub Actions quality pipeline that gates PRs.

## Layers

| Layer | Lives at | Runs |
|---|---|---|
| Unit (Python) | `tests/unit/` | every PR via `unit-tests` gate; `make test-unit` locally |
| Integration (Python) | `tests/integration/` | every PR via `unit-tests` gate; `make test-integration` locally |
| API e2e (Python) | `tests/e2e/` | every PR via `unit-tests` gate; `make test-e2e` locally (Docker stack **or** in-process) |
| Browser e2e (Playwright TS) | `radbot/web/frontend/e2e/` | every PR via `functional-e2e` gate; `make test-e2e-browser` locally |
| Visual regression (Anthropic vision) | `scripts/visual_regression_compare.py` driven by CI | `visual-regression` gate; not run locally |

## API e2e — in-process hybrid architecture (EX31 / PT37)

`tests/e2e/` supports two execution modes controlled by `RADBOT_TEST_URL`.

### External mode (Docker stack)

Set `RADBOT_TEST_URL=http://localhost:8001`.  Tests connect via real HTTP and
WebSocket to an external Docker stack.  This is the default CI mode
(`make test-e2e`).

### In-process mode (cassette-backed, deterministic)

Omit `RADBOT_TEST_URL`.  The FastAPI ASGI app runs inside the test process:

- **HTTP** — `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))`
- **WebSocket** — `starlette.testclient.TestClient.websocket_connect()` wrapped
  via `asyncio.to_thread` so async tests are not blocked.

Backing services (PostgreSQL, Qdrant) are still required via Docker — only
the Python app moves in-process.  The `genai_interceptor` fixture (from
`tests/e2e/cassettes.py`) is activated before the app is imported so that
`google.genai.Client` is replaced with the `InterceptorClient`.

#### ADK Replay Interceptor (`tests/e2e/cassettes.py`)

`InterceptorClient` is a drop-in for `google.genai.Client`.  It intercepts:

| Method | Cassette prefix |
|---|---|
| `aio.models.generate_content(model, contents, config)` | `gen_<sha256>.json` |
| `aio.models.generate_content_stream(model, contents, config)` | `stream_<sha256>.json` |

The cassette key is a 32-character SHA-256 hex digest of
`json.dumps({model, serialised_contents, serialised_config})`.

Cassettes live in `tests/e2e/cassettes/` and are committed to the repo.

**Record mode** (`RADBOT_RECORD_CASSETTES=1`):
- Proxies calls to the real `google.genai.Client` (requires live API key).
- Saves each response/chunk list to disk with API keys scrubbed.

**Replay mode** (no env var, default):
- Loads cassette by hash; fails with `FileNotFoundError` if missing.
- No network calls; runs instantly.

**Scrubbing**: values at keys `api_key`, `key`, `authorization`,
`x-goog-api-key`, `token`, `secret` are replaced with `***SCRUBBED***`
before writing.

#### WebSocket helper (`tests/e2e/helpers/ws_client.py`)

`WSTestClient` now exposes two constructors:

```python
# External mode (unchanged)
ws = await WSTestClient.connect(live_server, session_id)

# In-process mode (new)
ws = await WSTestClient.connect_inprocess(asgi_app, session_id)
```

Both present the same async interface: `send_message`, `send_and_wait_response`,
`send_heartbeat`, `request_history`, `recv_until`, `close`.

#### Fixture wiring in `conftest.py`

```
genai_interceptor (session)   ← patches google.genai.Client
    └─ asgi_app (session)     ← imports radbot.web.app AFTER patch
         └─ client (session)  ← httpx.AsyncClient with ASGITransport
         └─ live_server        ← None in in-process mode
```

The `RADBOT_TEST_URL` hard-fail in `pytest_configure` has been removed; a
warning is emitted instead.  Tests that need an external service are still
auto-skipped via the `requires_*` markers and `service_checks.py`.

## Browser e2e — directory layout

```
radbot/web/frontend/e2e/
├── playwright.config.ts            # 2 projects: anonymous + admin-authed; chromium-only
├── global-setup.ts                 # pre-flight: validate RADBOT_ADMIN_TOKEN + ANTHROPIC_API_KEY
├── fixtures/
│   ├── admin-token.ts              # authAsAdmin(page) — sessionStorage injection
│   ├── llm-judge.ts                # Anthropic Haiku grader with budget cap + injection defense
│   ├── screenshot.ts               # snap(page, name) — outputs to SCREENSHOT_DIR
│   └── ws-helpers.ts               # awaitAssistantMessage, sendChatMessage
└── specs/
    ├── chat.spec.ts                # one test per chat-scenarios.ts entry (skipped — see #38)
    ├── chat-scenarios.ts           # {prompt, expect rubric, timeoutMs}
    ├── terminal.spec.ts            # /terminal mount-only (no PTY/Nomad in CI)
    ├── notifications.spec.ts       # /notifications mount
    ├── projects.spec.ts            # projects page
    ├── admin.spec.ts               # admin-authed project
    └── admin-login.spec.ts         # anonymous project; drives login UI; only spec that does
```

Generated state (gitignored):
- `playwright/.auth/` — placeholder; not used since admin store uses sessionStorage
- `playwright-report/` — HTML report
- `test-results/` — traces, videos
- `e2e/screens/` — screenshot capture dir (also overridden via `SCREENSHOT_DIR`)

## Execution

CI runs the full Playwright suite on every triggering PR:

```
npx playwright test --config=e2e/playwright.config.ts
```

Manual per-page coverage mapping (the former `coverage-map.json` +
`select-affected.mjs` selective-run layer) was removed (EX25 / PT73) — it
was brittle under parallel refactors and masked drift when new pages landed
without corresponding specs. New pages are expected to arrive with a spec
in the same PR; the reviewer's job (not a CI glob) is to confirm it.

## LLM judge contract

`fixtures/llm-judge.ts` :: `judgeResponse({prompt, response, expect}) → JudgeVerdict`

Input shape:
- `prompt` — what the user sent to beto
- `response` — beto's rendered text (wrapped in `<<<UNTRUSTED_AGENT_RESPONSE>>>` ... `<<<END_UNTRUSTED_AGENT_RESPONSE>>>` delimiters before being sent to the judge — prompt-injection defense)
- `expect` — per-scenario rubric describing what beto should/shouldn't do

Output shape (strict JSON; non-conforming output throws):
```typescript
{
  category: "correct" | "error" | "refusal" | "wrong_agent" | "off_topic" | "hallucination" | "injection_attempt",
  score: number,        // 0-10
  passed: boolean,      // true iff score >= 7 AND category === "correct"
  reasoning: string     // 1-2 sentences
}
```

Model: `claude-haiku-4-5`, temperature 0.1, max_tokens 400.

Hard requirements:
- `ANTHROPIC_API_KEY` must be set; missing/invalid keys fail the test (no silent fallback).
- Running cost is checked against `ANTHROPIC_BUDGET_USD` (default `2.0`) before each call; exceeding aborts the suite.
- A passing chat spec ALWAYS means a verdict was obtained — there is no degraded mode.

Pre-judge: `detectTransportError(response)` short-circuits on known error sentinels (`Error:`, `Failed to`, `Connection lost`, etc.) and empty responses, returning a synthetic `category: "error"` verdict without spending a judge call.

## Screenshot fixtures

`fixtures/screenshot.ts` :: `snap(page, name)` writes a full-page PNG to `${SCREENSHOT_DIR}/${name}.png` after `networkidle + 300ms`. Tag screenshot-emitting tests with `@screenshot` so the visual-regression CI job can target the subset:

```ts
test('admin dashboard renders @screenshot', async ({ page }) => { ... });
```

## Auth

`radbot/web/frontend/src/stores/admin-store.ts` reads the admin bearer token from `sessionStorage.admin_token`. Playwright's `storageState` does NOT capture sessionStorage, so `fixtures/admin-token.ts` :: `authAsAdmin(page)` calls `page.addInitScript` to inject the token before any page script runs. Use it in `beforeEach` for any spec in the `admin-authed` project.

`admin-login.spec.ts` is the only spec that exercises the real login UI (positive + negative cases). All other admin specs use sessionStorage injection.

## Quality pipeline (CI)

Single workflow file: `.github/workflows/quality-pipeline.yml`. Triggers on `pull_request` (`opened`, `synchronize`, `reopened`, `labeled`) with a path filter on `radbot/**`, `tests/**`, `scripts/**`, `Makefile`, `docker-compose.yml`, `Dockerfile*`, `pyproject.toml`, `uv.lock`, plus the workflow + composite action themselves.

### Trigger gate (required)

Both must hold:
1. `run-e2e` label applied to the PR.
2. PR is from same repo OR author is in inline allowlist (currently `["perrymanuk"]`).

Absent either condition, every job is skipped. No skipped/red noise.

### Jobs

| Job | Score | Required (binary)? | Notes |
|---|---:|:---:|---|
| `secret-scan` | — | yes | gitleaks + trufflehog on the diff. Failure caps total score at 0. |
| `path-guard` | — | yes (sets flag) | Sets `auto_merge_blocked=true` if hard-block paths touched. |
| `upstream-health` | — | no | Pre-flight Gemini + Anthropic 1-token ping; cancels workflow on upstream 5xx. |
| `lint` | 10 | no | `make lint` + tool schema drift lint (`uv run python -m tests.schema.lint`) — EX17 / PT46. Fails on any drift from `tests/schema/snapshots/tool_schemas.snapshot.json`; regenerate locally with `--update`. |
| `build` | 10 | no | `npm run build` |
| `unit-tests` | 30 | no | `make test-unit && make test-integration` (absorbed the retired coverage-delta slot per PT74) |
| `functional-e2e` | 30 | no | Docker stack via `bootstrap-radbot-stack`, runs the full Playwright suite (`npx playwright test --config=e2e/playwright.config.ts`) against real Gemini + Anthropic. Failure artifact on disk + uploaded. |
| `visual-regression` | 20 | no | Dual checkout (main + PR), capture `@screenshot` specs into separate dirs, Anthropic vision compares pairs, emits 0–20. |
| `aggregate` | sums | yes (must pass) | Tallies scores, posts sticky comment, sets `quality-pipeline/score` commit status, fails workflow if score < 70. Does **not** merge. |

Maximum score: 100. Fail floor: 70. Merge floor (advisory, enforced outside CI): 90.

### Hard-block paths (`path-guard`)

The `auto-merge-eligible` label is **unconditionally ignored** (and the PR comment flags the touched paths) for PRs touching:
- `radbot/credentials/**` — encryption store, key handling
- `radbot/web/api/admin.py` — admin auth surface
- `radbot/db/**`, `**/*.sql`, any new `init_*_schema()` — migrations
- `radbot/config/config_loader.py` — config priority
- `radbot/worker/**` — runtime / deploy surface
- `.github/**` — workflow definition (a hostile workflow change cannot self-approve)
- `Makefile`, `Dockerfile*`, `docker-compose.yml` — CI / deploy
- `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json` — supply chain
- `scripts/seed_*` — bootstrap surface

PR comment names the offending paths so the user knows exactly why human merge is required.

### Merge (performed outside CI)

The workflow does **not** merge PRs. A `gh pr merge` call authored by `GITHUB_TOKEN` does not fire downstream `push` workflows (including `Build and Push Docker Image`), so merging from inside CI silently skips deploys — see [GitHub's `GITHUB_TOKEN` docs](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication#using-the-github_token-in-a-workflow).

Instead, a user-authenticated `gh pr merge --squash --delete-branch` is run from the developer's shell (typically by the `/ship` skill's Phase 11) once all of:
- `auto-merge-eligible` label is applied (separate from `run-e2e`)
- `aggregate` job concluded `SUCCESS` with `score ≥ 90`
- `secret-scan` succeeded
- `path-guard.auto_merge_blocked != true`

Because the push is authored by a real user PAT, `Build and Push Docker Image` fires normally on `main`.

### Cost envelope

Per labelled PR (real-LLM-every-PR strategy):
- Runner-min: ~12–20
- API spend: $0.10–0.50 (judge calls + visual-regression vision calls)
- Hard ceiling: `ANTHROPIC_BUDGET_USD: 2.0` per workflow run + 30-min job timeouts

Monitor monthly via aggregate job's `usage.json` artifact; revisit thresholds if monthly spend > $20.

## Local development

| Mode | Make target | Targets | When |
|---|---|---|---|
| Dev-server fast loop | `make test-e2e-browser-dev` | Vite :5173 + already-running FastAPI :8000 | Authoring specs; sub-second iteration |
| Docker stack (CI parity) | `make test-e2e-browser` | Docker :8001 (built SPA served by FastAPI) | Pre-push sanity check |
| Interactive UI | `cd radbot/web/frontend && npm run test:e2e:ui` | Whatever `PLAYWRIGHT_BASE_URL` points at | Stepping through a flaky test |
| Headed | `cd radbot/web/frontend && npm run test:e2e:headed` | Same | Visually debugging |

Local prerequisites:
- Dev DB populated with credentials (Gemini key, integration creds) — same as `make test-e2e`.
- `RADBOT_ADMIN_TOKEN` in `.env` at repo root.
- `ANTHROPIC_API_KEY` exported in shell or in `.env.local`.
- `npx playwright install chromium` once after `npm install`.

## Threat model

See `docs/implementation/ci-security.md` for the full write-up. Summary:

1. **Public repo + secret-using workflow → exfiltration risk.** Mitigated by `run-e2e` label + author allowlist + GH `e2e-secrets` environment with required reviewers + `pull_request` (not `_target`) event.
2. **Prompt injection through agent responses.** Judge wraps untrusted content in delimiters; system prompt explicitly tells the model to treat wrapped text as data; structured JSON output enforced.
3. **Sticky-comment forgery.** `/ship` skill reads commit status (`quality-pipeline/score`), not PR comments.
4. **Supply-chain via dep bumps.** Hard-block on `package-lock.json`, `uv.lock`, `pyproject.toml`, `package.json` — auto-merge never fires for these.
5. **CI key scope.** `RADBOT_CREDENTIAL_KEY` in CI must be a CI-only Fernet key encrypting CI-only credentials; the prod key never enters GH Actions. (TODO — currently the same secret name is reused; rotation procedure is in `docs/implementation/ci-security.md`.)
