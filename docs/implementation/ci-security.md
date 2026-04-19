# CI security

`perrymanuk/radbot` is a public repo. The quality-pipeline workflow uses high-impact secrets (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `RADBOT_ADMIN_TOKEN`, `RADBOT_CREDENTIAL_KEY`, `TAILSCALE_OAUTH_*`). This doc enumerates the controls that prevent a hostile fork PR from exfiltrating them, and the procedures for managing the trust surface.

## Threat model

Adversary categories we defend against:
1. **Drive-by fork PR** — outside contributor opens a PR with malicious code in `package.json` postinstall, npm dep typosquat, modified workflow file, etc., hoping CI will run with secrets in scope.
2. **Compromised allowlisted account** — author allowlist is bypassed via stolen credentials.
3. **Supply-chain compromise** — a transitive dep we depend on starts shipping malicious code that runs in CI.
4. **Workflow misconfiguration** — a future PR accidentally exposes secrets to a step it shouldn't.
5. **Sticky-comment forgery** — anyone with PR comment access posts a fake `quality-pipeline/score=99` comment to trick the `/ship` skill.

Adversary categories we DO NOT defend against (out of scope for v1):
- Compromised maintainer machine (anyone who can `git push --force` to `main`).
- Compromised GitHub Actions runners themselves (we trust GH's hosted infra).
- Compromised Anthropic / Google APIs (out of our control).

## Controls

### 1. Opt-in label gate

Workflow only runs when the PR carries the `run-e2e` label AND the author is in the inline allowlist (`["perrymanuk"]`) OR the PR is from the same repo. Both conditions required.

This is enforced in `quality-pipeline.yml`'s `guard` job — every other job depends on `guard.outputs.run == 'true'`.

For outside contributors: a maintainer reviews the diff for anything suspicious (modified workflows, weird dep changes, suspicious-looking JS) before applying the `run-e2e` label.

### 2. GH `e2e-secrets` deployment environment

All workflow secrets MUST live in the GH environment named `e2e-secrets`, NOT at repo level. Configure the environment with **Required reviewers** set to the maintainer.

Result: every job that declares `environment: e2e-secrets` pauses for manual approval before secrets become readable. This is the GH-native "are you sure?" — a second human checkpoint independent of the label.

To configure: GH repo → Settings → Environments → New environment `e2e-secrets` → check "Required reviewers" → add yourself → "Save protection rules" → move all sensitive secrets from repo-level to this environment.

### 3. `pull_request` event (NOT `pull_request_target`)

The workflow uses `pull_request`. Fork PRs cannot read secrets under `pull_request` — GH redacts them by default.

`pull_request_target` runs in base-repo context with secrets, but immediately after `actions/checkout` of the PR head, you've handed secrets to attacker-controlled code. We avoid this entire class of vulnerability by not using it.

### 4. Repo Actions setting

GH repo → Settings → Actions → General → "Require approval for all outside collaborators" — enabled. Independent of our workflow logic; catches misconfiguration.

### 5. Path-based hard-block

`path-guard` job scans the PR diff against a hardcoded blocklist (`radbot/credentials/`, `.github/`, `pyproject.toml`, `uv.lock`, `*.sql`, …). When matched, sets `auto_merge_blocked=true`. The aggregate job then refuses to call `gh pr merge --auto` regardless of score.

This catches the case where a hostile PR puts malicious code in a high-impact file but otherwise passes all tests — auto-merge will not fire, human review is required.

Full list in `specs/testing.md` § Hard-block paths and in `quality-pipeline.yml` `path-guard` job.

### 6. Secret scanner pre-test

`secret-scan` runs gitleaks + trufflehog on the diff. It runs as a required job (binary pass/fail, not weighted) and caps total score at 0 on failure. Catches the most common project-ending mistake (committing a key).

### 7. SHA-pinned third-party actions

Pin `tailscale/github-action`, `peter-evans/create-or-update-comment`, `actions/checkout`, etc. to full commit SHAs (not tags) — defeats tag-mutation supply-chain attacks. Use Dependabot to bump them safely on a separate `dependencies` PR (which itself goes through the gate).

Currently:
- `tailscale/github-action` — pinned in `bootstrap-radbot-stack/action.yml`. **TODO**: confirm SHA matches the v3.4.0 release.
- Other actions: TODO — switch from `@v4` style to `@<sha>` once stable.

### 8. Sticky-comment forgery defense

`/ship` skill reads the commit status `quality-pipeline/score` (set by aggregate job via `gh api .../statuses`), NOT the sticky PR comment text. Anyone with comment access can forge a comment, but only the workflow itself can set commit statuses.

## Secret inventory

| Secret | Used in | Rotation |
|---|---|---|
| `RADBOT_ADMIN_TOKEN` | Stack admin auth + Playwright auth | When suspected leak; coordinate with prod |
| `RADBOT_CREDENTIAL_KEY` | Fernet decrypt of credentials in DB | **TODO** — see Open issues below |
| `GEMINI_API_KEY` | Beto's LLM calls in CI | Quarterly + on suspected leak |
| `ANTHROPIC_API_KEY` | Judge + visual-regression | Quarterly + on suspected leak |
| `TAILSCALE_OAUTH_CLIENT_ID` | Runner Tailscale auth | When org member rotates |
| `TAILSCALE_OAUTH_SECRET` | Runner Tailscale auth | Same |
| `OVERSEERR_API_KEY` (optional) | Overseerr integration spec | Annual + on suspected leak |

## Author allowlist procedure

To add an author to the allowlist:

1. Open a PR modifying `quality-pipeline.yml`'s `guard` job's `ALLOW_AUTHORS` JSON.
2. Maintainer review (since `.github/` is on the hard-block list, this PR will not auto-merge — that's the point).
3. **7-day cooldown** before merging — gives time to notice if the requested author is showing other suspicious activity.
4. Update this doc.

## Open issues / TODO

- **CI/prod credential key isolation**: currently the same `RADBOT_CREDENTIAL_KEY` secret is used in both prod and CI. A compromise of any GH Action with `e2e-secrets` access can decrypt every prod credential. The fix is a separate `CI_RADBOT_CREDENTIAL_KEY` encrypting a CI-only credential set; the prod key never enters GH Actions. Plan: implement as a follow-up PR; track in TASK ledger.
- **Tailscale tag ACL audit**: `tag:github-actions` ACL must be reviewed quarterly to confirm the runner can only reach the services we intend (Overseerr, ntfy, etc. — NOT Postgres, NOT Nomad, NOT internal admin endpoints).
- **Action SHA pinning**: complete the migration from `@v4` tags to commit SHAs.
- **Audit log to PR comment**: aggregate job should append a "Resolved approver: @username (via label / via env approval)" line to the sticky comment for forensic trail.

## Incident response

If you suspect any secret leaked:

1. **Rotate immediately.** Don't wait for confirmation. The cost of an unnecessary rotation is minutes; the cost of an unrotated leak is hours-to-days of damage.
2. Update the GH `e2e-secrets` environment with the new value.
3. Update the prod equivalent (Nomad job, deploy config).
4. Audit recent workflow runs (`gh run list --limit 50 --json conclusion,databaseId,event`) for anything that could have exfiltrated.
5. If `RADBOT_CREDENTIAL_KEY` rotated: re-encrypt the credential store with the new key (`scripts/migrate_credential_key.py` — TODO, doesn't exist yet, would need to be written).
6. Open a post-mortem issue in this repo with timeline.
