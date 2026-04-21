# Quality pipeline

PR gating workflow. Spec is in `specs/testing.md` § Quality pipeline. This doc covers operations: how it works, how to debug a failure, how to tune.

## When does the pipeline run?

Both conditions required:
1. `run-e2e` label applied to the PR.
2. PR is from same repo OR author is in inline allowlist (`["perrymanuk"]`).

Adding the label after a PR is opened: GH fires `pull_request.labeled`, the workflow re-evaluates against the current HEAD and starts.

## Gate definitions

| Gate | Job name | Score | Required | Notes |
|---|---|---:|:---:|---|
| Secret scan | `secret-scan` | — | yes | gitleaks + trufflehog. Failure caps total at 0. |
| Path guard | `path-guard` | — | yes (sets flag) | Blocks auto-merge for sensitive paths. |
| Upstream health | `upstream-health` | — | no | Pre-flight Gemini + Anthropic ping; cancels workflow on 5xx. |
| Lint | `lint` | 10 | no | `make lint` |
| Build | `build` | 10 | no | `npm run build` |
| Unit + integration | `unit-tests` | 30 | no | `make test-unit && make test-integration` (absorbed the retired coverage-delta slot per PT74) |
| Functional e2e | `functional-e2e` | 30 | no | Playwright against full Docker stack with real LLMs |
| Visual regression | `visual-regression` | 20 | no | Anthropic vision diff of `@screenshot` specs |

Total: 100. Pass floor: 70 (workflow fails below). Auto-merge floor: 90.

## Hard-block paths (auto-merge always disabled)

`path-guard` flips `auto_merge_blocked=true` for any of:
- `radbot/credentials/`, `radbot/web/api/admin.py`, `radbot/db/`, `radbot/config/config_loader.py`, `radbot/worker/`
- `.github/`, `Makefile`, `Dockerfile*`, `docker-compose.yml`
- `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`
- `scripts/seed_*`, any `*.sql` file

These PRs still get scored — auto-merge just won't fire.

## Auto-merge

Aggregate job calls `gh pr merge --auto --squash --delete-branch` when ALL hold:
- `auto-merge-eligible` label applied (separate from `run-e2e`)
- `score >= 90`
- `secret-scan.result == 'success'`
- `path-guard.outputs.auto_merge_blocked != 'true'`

The `--auto` flag enables GH's native auto-merge, which still respects branch protection — the workflow just *enables* it.

## Cost envelope (real-LLM-every-PR)

| Component | Per labelled PR |
|---|---|
| Runner-min | 12–20 |
| Anthropic spend (judge) | $0.01–0.05 |
| Anthropic spend (visual) | $0.05–0.30 |
| Gemini spend (chat) | minimal (model is `gemini-2.5-flash`) |
| Hard ceiling | `ANTHROPIC_BUDGET_USD: 2.0` per run + 30-min job timeout |

Monthly: ~$5–15 at moderate PR volume. Aggregate emits a `usage.json` artifact for tracking.

## Common failures

### `upstream-health` cancels the workflow
Gemini or Anthropic returned 5xx on the pre-flight ping. This is correct behavior — provider outage shouldn't block your PR. Wait, push a no-op commit, or remove and re-add the `run-e2e` label to retrigger.

### `functional-e2e` red, all other gates green
Almost always one of:
- Gemini rate-limited → check `artifacts/radbot.log` for 429s.
- LLM judge gave a low verdict → see `judge-verdict-<scenario>.json` in the bundle. Either the spec rubric is too strict or beto regressed.
- Stack didn't boot → `artifacts/compose-logs.txt` will show the cause (Postgres init race, Qdrant OOM, radbot startup error).

### `visual-regression` low score on a styling-only PR
Anthropic vision is reading the screenshots literally. Tighten the rubric in `scripts/visual_regression_compare.py` SYSTEM_PROMPT, or accept the deduction (visual regression is noisy by design — that's why it caps at 20 not 30).

### `secret-scan` fails
gitleaks/trufflehog detected a possible credential in your diff. **Stop**. Rotate the credential immediately even if it was a false positive (assume any string matching the pattern leaked). Use `git history` rewrite + force-push only with explicit user permission.

### `path-guard` blocks auto-merge but score is 95
This is correct. Sensitive paths require human merge regardless of score. The aggregate comment names the offending file(s).

## Tuning

To change weights or thresholds:
- Edit `.github/workflows/quality-pipeline.yml` aggregate job's score arithmetic.
- Edit `specs/testing.md` to match (mandatory — spec ↔ code map).

To change the hard-block list:
- Edit `path-guard` job's `BLOCK_PATTERNS`.
- Edit `specs/testing.md` to match.

To change the author allowlist:
- Edit `guard` job's `ALLOW_AUTHORS` JSON array.
- Edit `docs/implementation/ci-security.md` to match (cooldown procedure).

## Local equivalent

There isn't one for the aggregate score — devs run individual gates manually:
- `make lint` / `make test-unit` / `make build-frontend` / `make test-e2e-browser`
- The workflow is the pipeline definition; no duplication in shell scripts.

For pre-PR validation: `/ship` skill runs the cheap subset locally before pushing.
