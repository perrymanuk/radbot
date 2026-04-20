# `/ship` skill

Claude Code skill that orchestrates the full lifecycle: branch → push → CI → auto-merge. Lives at `.claude/skills/ship/SKILL.md`.

## When to use it

- Routine PRs you want auto-merged when quality-pipeline passes.
- Multi-step changes where you want CI feedback before merging.
- After a hand-off where the agent did the work and you want to ship without micro-managing the merge process.

Skip it for:
- One-line typo fixes — just commit + push to `main` if you have permission.
- Changes touching hard-block paths (credentials, admin API, CI, deps, schemas) — the workflow won't auto-merge, so the orchestration overhead doesn't pay off. Use `gh pr create` directly.
- Large refactors you want human review on regardless of score.

## How to invoke

In a Claude Code session inside the radbot repo:

```
/ship
```

Optional arguments:
- `--manual-merge` — apply only `run-e2e`; you merge by hand after review.
- `--auto-yes` — skip the "Score is NN/100 — merge?" confirmation.
- `--slug my-feature` — explicit branch slug (default derived from diff).

## What happens

1. **Pre-flight** — confirm clean working tree, derive slug.
2. **Worktree** — `git worktree add /tmp/radbot-ship-<slug> -b ship/<slug> origin/main`.
3. **Local gates (cheap subset, hard gate)** — `make lint` (flake8 + mypy), `make test-unit`. When frontend changed: `npm run lint`, `npx tsc --noEmit`, `npm run build`, `npm run test:e2e:affected`. Every gate must be green before push — skipping a local gate to "let CI catch it" wastes ~4 min of pipeline time. Skips visual regression and chat-quality (CI handles them).
4. **Spec sync check** — for every changed source file, verify the corresponding `specs/*.md` is in the diff (per `CLAUDE.md` Spec ↔ code map).
5. **Secret scan** — regex on staged + unstaged files (`AKIA…`, `ghp_…`, `sk-ant-…`, etc.). Hard stop on match.
6. **Commit + push** — conventional-commit message, push to `ship/<slug>`.
7. **Open PR** — `gh pr create` with `run-e2e` and `auto-merge-eligible` labels.
8. **Watch workflow** — `gh run watch` (server-side stream, not polling).
9. **Read score** — from commit status `quality-pipeline/score` (NOT the sticky comment, which is forgeable — see `docs/implementation/ci-security.md`).
10. **CI fix loop** — up to 3 attempts to address pipeline feedback.
11. **Merge (user-authenticated)** — confirms once with you (unless `--auto-yes`), verifies `auto-merge-eligible` label + `aggregate` SUCCESS + score ≥ 90, then runs `gh pr merge --squash --delete-branch` from your shell. Not performed inside CI — a merge authored by `GITHUB_TOKEN` does not trigger the `Build and Push Docker Image` workflow (GitHub's recursion guard), so running the merge locally is what makes deploys fire.
12. **Cleanup** — reminds you the worktree exists; offers to remove on confirmation.

## Recovery from common failures

### "Score is 87/100, not auto-merging"
The sticky PR comment lists per-gate scores. Identify which gate cost you the points:
- Lint failed? Fix the lint error, push.
- Visual regression at 12/20? Either the change is intentional (accept lower score, merge by hand) or you broke a layout (fix CSS, push).
- Functional e2e failed? Download the artifact, see `docs/implementation/quality_pipeline.md` § Common failures.

### "path-guard blocked auto-merge"
You touched a sensitive path (admin.py, credentials/, deps, …). This is correct — these always require human merge. The skill posts the offending paths in its summary; review the PR by hand and merge with `gh pr merge <num> --squash`.

### "Score ≥ 90 but docker-build didn't fire after the merge"
Pre–2026-04-20 behavior: the workflow's aggregate job called `gh pr merge --auto` itself, and `GITHUB_TOKEN`-authored merges don't trigger downstream `push` workflows. The skill now merges from your shell to avoid this. If you're seeing this on a new PR, check that Phase 11 actually ran (the skill should have invoked `gh pr merge` locally) — if the PR merged without your shell running the command, something else merged it and you'll need to push an empty commit to `main` to trigger the deploy.

### "CI fix loop hit max attempts"
The skill stops after 3 failed CI attempts and hands control back to you. Inspect the artifacts, fix manually, push. Re-run `/ship` if you want it to take over again from the watch step.

### "Skill couldn't find `gh` / not authenticated"
`gh auth login` first.

### "Workflow didn't trigger"
Check that the `run-e2e` label was applied (`gh pr view <num> --json labels`). Re-add it if missing — the `pull_request.labeled` event will fire and the workflow will start.

### "I want to abort mid-ship"
Kill the Claude Code session. The worktree at `/tmp/radbot-ship-<slug>` is yours to clean up:
```bash
cd ~/git/perrymanuk/radbot
git worktree remove /tmp/radbot-ship-<slug>
git branch -D ship/<slug>      # if you don't want to keep the branch
```

## Limitations

- The skill has NO authority to bypass branch protection or path-guard. It only orchestrates the human-side loop.
- Visual regression doesn't run locally (cost + complexity; CI handles it). You won't see screenshot diffs until CI runs.
- The skill does not modify spec files for you. If the spec sync check finds a missing update, it asks you to add it before continuing.
- The skill assumes `make`, `npm`, `gh`, and `uv` are on `PATH`. Pre-reqs not negotiated.
