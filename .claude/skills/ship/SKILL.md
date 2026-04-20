---
name: ship
description: >
  Branch off main into an isolated worktree, run cheap local quality gates
  (lint, static type-check, unit tests, frontend build/e2e), open a PR with
  the run-e2e and auto-merge-eligible labels applied, watch the
  quality-pipeline workflow run, fix CI failures up to 3 times, and merge
  from the user's shell (so deploy workflows fire) when the score crosses 90.
  Use when the user says "ship this", "open a PR for this work", "merge when
  CI is green", or wants the full ship-it lifecycle for a non-trivial change.
  Does NOT decide merge authority — the workflow's own gates do; this skill
  just orchestrates the human-side loop.
---

# /ship — work in worktree → PR → quality-pipeline → auto-merge at 90

ARGUMENTS:
  - `--manual-merge` — apply only `run-e2e` label; user merges by hand after review
  - `--auto-yes` — skip the "Score is 94/100 — merge?" confirmation
  - `--slug <name>` — explicit branch slug (default derived from the diff)

Mirrors `~/git/hometogo/homies/.claude/skills/implement/SKILL.md`, minus Jira coupling and DIC validation. Smaller gate set, narrower local subset.

## Constants

```
REPO_ROOT=~/git/perrymanuk/radbot
WORKTREE_ROOT=/tmp
GITHUB_REPO=perrymanuk/radbot
DEFAULT_BRANCH=main
QUALITY_PIPELINE_WORKFLOW=quality-pipeline.yml
AUTO_MERGE_THRESHOLD=90
MAX_FIX_ATTEMPTS=3
WATCH_TIMEOUT_MIN=20
```

## Phase 1 — Pre-flight

1. `cd $REPO_ROOT`. `git status` to confirm there is a meaningful diff (working tree, staged, or already on a branch off main).
2. Read `CLAUDE.md` and any spec files referenced in the diff path map (Spec ↔ code map section).
3. If working tree is dirty AND user wants to ship work currently in `main` checkout, ask whether to (a) commit first, (b) stash, or (c) abort.
4. Derive `SLUG` from `--slug` arg or from the dominant changed-file directory (e.g. `radbot/web/api/admin.py` → `admin-api`). Lowercase, hyphenated, ≤ 30 chars.

## Phase 2 — Branch + worktree

### 2a. Pre-flight the main checkout

Before creating any worktree, audit `$REPO_ROOT` for *unrelated* dirty state:

```bash
cd $REPO_ROOT
git status --porcelain
```

Compare the dirty files against what the user actually wants to ship (ask the user to confirm the scope if ambiguous). If there are modified or untracked files that are NOT part of this ship (e.g. leftovers from a previous abandoned ship, or separate in-progress work), **stop and ask** — do not silently sweep them into the worktree and do not discard them. Typical resolutions:

- Stash the unrelated work under a named entry (`git stash push -u -m "<description>" -- <files>`)
- Move it to its own branch
- Commit it separately first

Only proceed once every dirty file in `$REPO_ROOT` is either (a) part of this ship or (b) explicitly acknowledged by the user as safe to leave behind.

### 2b. Create the worktree

```bash
cd $REPO_ROOT
git fetch origin $DEFAULT_BRANCH
git worktree add $WORKTREE_ROOT/radbot-ship-$SLUG -b ship/$SLUG origin/$DEFAULT_BRANCH
```

If `ship/$SLUG` already exists, ask whether to reuse (`-B` to reset) or create with a `-N` suffix.

### 2c. Hand off the work via stash (atomic — no leftovers)

This is the step where prior versions of /ship left a mess. The *only* supported hand-off is a named stash, which moves the work out of `$REPO_ROOT` atomically:

```bash
# Still in $REPO_ROOT. List the exact files to ship (never -A).
STASH_MSG="ship/$SLUG handoff"
git stash push -u -m "$STASH_MSG" -- <each-changed-file>

# Now $REPO_ROOT is clean. Apply the stash inside the worktree.
cd $WORKTREE_ROOT/radbot-ship-$SLUG
git stash show -p --include-untracked "stash@{0}" | git apply --index
# Drop the stash only after confirming the worktree tree looks right:
git stash drop "stash@{0}"
```

If work was already on a branch → skip this entire section and just `git push -u origin <branch>` from that branch instead of creating a ship/ branch.

**Invariants after 2c:**
- `cd $REPO_ROOT && git status --porcelain` → empty
- `cd $WORKTREE_ROOT/radbot-ship-$SLUG && git status --porcelain` → shows the handed-off changes

If either invariant fails, stop and ask.

From here, every command runs in the worktree.

## Phase 3 — Local gates (cheap subset)

**Hard gate**: every command below must exit 0 before Phase 5 (secret scan) / Phase 6 (push). CI runs the same checks — running them locally first is the cheap way to avoid a red pipeline + 4-minute wait.

### Python static + unit

```bash
make lint                   # flake8 + mypy over radbot/ and tests/
make test-unit              # pytest tests/unit
```

### Frontend static + build (only if `radbot/web/frontend/**` changed)

```bash
cd radbot/web/frontend
npm ci
npm run lint                # eslint .
npx tsc --noEmit            # TypeScript static type check
npm run build               # catches import / prop-type issues missed by lint
npm run test:e2e            # full Playwright suite (manual coverage-map was removed in EX25 / PT73)
cd ../../..
```

Check `git diff --name-only origin/main...HEAD` (or the working tree for pre-commit runs) to decide whether the frontend block applies. If the diff is Python-only, skip the frontend block entirely.

### Skip locally (CI covers these)

- `make test-integration` — slow, depends on services
- `make test-e2e-browser` full run — covered by functional-e2e
- Visual regression — requires real Anthropic spend
- Chat-quality grading — requires `ANTHROPIC_API_KEY`

### On failure

1. Show the user the failing output verbatim.
2. Fix only the failing thing — don't refactor, don't auto-format unrelated code.
3. Re-run **only** the gate that failed (not the whole suite).
4. Repeat until green or the user aborts.

Do not proceed to Phase 5 until every gate above is green. "I'll let CI catch it" is a failure mode — CI costs ~4 min and a GitHub Actions minute; `make lint` costs ~10 s.

## Phase 4 — Spec sync check

For every changed source file, look up `CLAUDE.md`'s Spec ↔ code map. If a row's source pattern matched and the corresponding `specs/*.md` is NOT in the diff, prompt the user to add it before proceeding. Hard requirement of CLAUDE.md.

## Phase 5 — Secret scan

Run a regex scan on staged + unstaged files:

```bash
patterns='(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9_]{36}|ghs_[A-Za-z0-9_]{36}|sk-ant-[A-Za-z0-9_-]{20,}|xox[bpras]-[A-Za-z0-9-]{10,}|-----BEGIN.*PRIVATE KEY)'
git diff --name-only HEAD | xargs -I{} grep -lnE "$patterns" "{}" 2>/dev/null
```

Hard stop if anything matches. Notify user, do NOT commit.

## Phase 6 — Commit + push

Stage explicitly (never `git add -A`):

```bash
git add <each-changed-file>
git commit -m "feat($SLUG): <one-line summary>

<body>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push -u origin ship/$SLUG
```

Use a HEREDOC for the commit message to preserve newlines (per CLAUDE.md commit style).

## Phase 7 — Open PR

```bash
gh pr create \
  --repo $GITHUB_REPO \
  --base $DEFAULT_BRANCH \
  --title "[$SLUG] <one-line summary>" \
  --body "$(cat <<'EOF'
## Summary

<2-3 sentence description of the change>

## Specs updated

<list of specs/*.md files this PR modifies, or "none needed because: …">

## Quality pipeline

Score: _pending_ — awaiting workflow run.

## Verification

- [x] Local lint, unit tests, build, affected e2e all green
- [ ] Quality pipeline (CI)
- [ ] Auto-merge at score ≥ 90
EOF
)"
```

Apply labels:
- Always: `run-e2e` (triggers the workflow)
- Default: also `auto-merge-eligible` (releases auto-merge once score ≥ 90)
- If `--manual-merge`: only `run-e2e`

```bash
gh pr edit <PR_NUMBER> --repo $GITHUB_REPO --add-label run-e2e
[ "$MANUAL_MERGE" != "true" ] && gh pr edit <PR_NUMBER> --add-label auto-merge-eligible
```

Capture the PR number for the next phases.

## Phase 8 — Watch the workflow

Use server-side streaming, not polling — cheaper and more reliable:

```bash
gh run watch --repo $GITHUB_REPO --exit-status \
  $(gh run list --repo $GITHUB_REPO --branch ship/$SLUG \
                --workflow $QUALITY_PIPELINE_WORKFLOW \
                --limit 1 --json databaseId --jq '.[0].databaseId')
```

If `gh run watch` exits non-zero or times out at $WATCH_TIMEOUT_MIN min, proceed to Phase 9 anyway — the score will still tell us what happened.

## Phase 9 — Read the score

The aggregate job posts a sticky comment AND sets a commit status. Trust the commit status (forgeable comments are a known footgun — see `docs/implementation/ci-security.md`):

```bash
gh api repos/$GITHUB_REPO/commits/$(git rev-parse HEAD)/statuses \
  --jq '.[] | select(.context == "quality-pipeline/score") | .description' \
  | head -1   # description is "NN / 100"
```

Display the per-gate breakdown by reading the sticky comment for context (do NOT use it as the merge signal):

```bash
gh api repos/$GITHUB_REPO/issues/$PR_NUMBER/comments \
  --jq '.[] | select(.body | contains("Quality Pipeline Results")) | .body' \
  | head -1
```

## Phase 10 — CI fix loop (max $MAX_FIX_ATTEMPTS)

If `score < $AUTO_MERGE_THRESHOLD`:

1. Identify failing gates from the sticky comment.
2. For functional-e2e or visual-regression failure → download the artifact (`gh run download <run-id>`), inspect logs/screenshots locally.
3. Fix only what failed.
4. Commit `"fix($SLUG): address quality-pipeline feedback (attempt N/3)"`, push.
5. Loop back to Phase 8.

Cap at $MAX_FIX_ATTEMPTS. Past that, hand control to the user with a summary.

## Phase 11 — Merge (user-authenticated, so deploys trigger)

If `score ≥ $AUTO_MERGE_THRESHOLD`:

1. Confirm once with the user: `Score is NN/100 — merge now?` Skip if `--auto-yes` was passed.
2. Verify the pipeline actually cleared the gates the skill cannot see:

```bash
gh pr view $PR_NUMBER --repo $GITHUB_REPO \
  --json labels,statusCheckRollup \
  --jq '{labels: [.labels[].name], aggregate_conclusion: ([.statusCheckRollup[] | select(.name=="aggregate") | .conclusion] | last)}'
```

   - `auto-merge-eligible` must be in `labels` (otherwise the user chose `--manual-merge`; stop and hand off).
   - `aggregate_conclusion` must be `SUCCESS`.

3. Merge from the user's shell — **never from inside the workflow**. A merge authored by the workflow's `GITHUB_TOKEN` does not fire downstream `push` workflows (including `Build and Push Docker Image`), so merging from CI silently skips deploys ([GitHub docs](https://docs.github.com/en/actions/security-for-github-actions/security-guides/automatic-token-authentication#using-the-github_token-in-a-workflow)). `gh` uses the user's PAT, so the resulting push to `main` triggers the docker-build workflow as expected.

```bash
gh pr merge $PR_NUMBER --repo $GITHUB_REPO --squash --delete-branch
```

4. After merge, confirm the deploy fired:

```bash
sleep 10
gh run list --repo $GITHUB_REPO --workflow "Build and Push Docker Image" --branch main --limit 1
```

   Tell the user the run ID so they can watch it. If no run appears within ~30 s, the user should push an empty commit from their shell to force a fresh `push` event.

5. If `auto-merge-eligible` is missing or `aggregate_conclusion` is not `SUCCESS`, tell the user why and stop — do not attempt the merge.

The skill has NO authority to bypass branch protection or path-guard — it only orchestrates.

## Phase 12 — Cleanup

Cleanup has two halves. **Both** must run after a successful merge or the main checkout drifts out of sync with `origin/main` and the next /ship invocation sees phantom "leftover" changes.

### 12a. Remove the worktree

Remind the user the worktree is at `$WORKTREE_ROOT/radbot-ship-$SLUG` and offer to remove on confirmation:

```bash
cd $REPO_ROOT
git worktree remove $WORKTREE_ROOT/radbot-ship-$SLUG
```

Don't auto-clean — the user may want to inspect.

### 12b. Fast-forward the main checkout (only if the PR was merged)

If Phase 11 merged the PR, sync `$REPO_ROOT` to the new `origin/main` so the next session starts from a clean, current tree:

```bash
cd $REPO_ROOT
# Sanity check: main checkout should be clean. If it isn't, something leaked —
# stop and ask rather than pulling over dirty state.
test -z "$(git status --porcelain)" || { echo "WARN: $REPO_ROOT is dirty — skipping pull, investigate"; exit 0; }
git switch $DEFAULT_BRANCH 2>/dev/null || true
git fetch origin $DEFAULT_BRANCH
git pull --ff-only origin $DEFAULT_BRANCH
```

Skip 12b entirely on `--manual-merge` or if Phase 11 did not merge (score < threshold, user aborted, etc.) — the user owns the main checkout state in those cases.

---

## Error handling

- If any phase fails, surface the specific error and ask how to proceed.
- If `gh` isn't authenticated → tell the user to run `gh auth login`.
- If the workflow doesn't trigger after push (e.g. `run-e2e` label not applied yet) → re-run the labeling step.
- If upstream-health pre-flight cancels the workflow → wait, retry, or skip.
- Screenshot/visual-regression fetch failures are non-blocking — proceed with the score we have.

## What this skill does NOT do

- Decide merge authority (workflow + branch protection do).
- Bypass `path-guard` for sensitive paths.
- Run visual regression locally (cost + complexity; CI handles it).
- Modify spec files for the user (it asks).
