# Doc Keeper Guide

Detect drift between codebase and documentation after e2e runs. Apply minimal updates using terse LLM-optimized style.

## When to Start

Wait for BOTH report files to exist before starting (poll every 20s):
- `reports/e2e-log-analysis.md`
- `reports/e2e-performance-review.md`

This teammate runs in parallel with test-coverage — both depend on log-analyst + perf-reviewer.

## Data Sources

### 1. Teammate Reports

| Report | Extract |
|--------|---------|
| `reports/e2e-log-analysis.md` | New error patterns, exception types, undocumented logger namespaces → gotcha candidates |
| `reports/e2e-performance-review.md` | Architecture changes, new bottleneck patterns → spec updates |
| `reports/e2e-pytest-output.txt` | New test files (imply new modules), skipped tests (imply new integrations) |

### 2. Current Documentation

Read existing state before making changes:
- `CLAUDE.md` — current sections, line count, table contents
- `SPEC.md` — current index and sub-spec files
- `specs/*.md` — current sub-spec contents
- `docs/guides/*.md` — current workflow guides

### 3. Codebase Scan

Run these to establish ground truth:

```bash
# DB table definitions
grep -rn "CREATE TABLE" radbot/

# FunctionTool registrations
grep -rn "FunctionTool(" radbot/tools/

# Sub-agent factories
ls radbot/agent/*/factory.py

# REST API routers
grep -rn "router = APIRouter" radbot/web/api/

# Agent instruction files
ls radbot/config/default_configs/instructions/*.md

# Make targets
grep "^[a-z].*:" Makefile | head -20
```

## Target 1: CLAUDE.md

Budget: **500 lines max**. Currently ~336 lines.

### Audit Checks

| CLAUDE.md Section | Drift Detection Method |
|-------------------|----------------------|
| Sub-Agents table | Compare `ls radbot/agent/*/factory.py` vs table rows |
| Tool Modules table | Compare `grep FunctionTool(` output vs table rows |
| Database Tables | Compare `grep CREATE TABLE` output vs table rows |
| Known Gotchas | Check if any CRITICAL/HIGH log-analysis finding is missing |
| Common Patterns | Scan for new singleton clients, new DB patterns |
| Running table | Compare `grep` of Makefile targets vs table rows |
| Project Structure | Compare `ls radbot/` tree vs documented tree |

### Update Rules

- Only add genuinely new items — do NOT rewrite correct entries
- Preserve existing section order and table formats exactly
- When adding gotcha: use existing bullet style, no severity prefix
- If near 500-line limit: compress existing sections before adding
- Match existing abbreviation style (DB, WS, MCP, ADK, etc.)

## Target 2: SPEC.md Ecosystem

Structure: `SPEC.md` (index, ≤200 lines) → `specs/*.md` (domain sub-docs, ≤300 lines each).

**Sub-spec content sources:**

| File | Primary Sources |
|------|----------------|
| `specs/agents.md` | `radbot/agent/`, instruction files, CLAUDE.md Sub-Agents table |
| `specs/tools.md` | `radbot/tools/`, CLAUDE.md Tool Modules table |
| `specs/web.md` | `radbot/web/`, frontend `src/` structure |
| `specs/storage.md` | DB schema files, CLAUDE.md Database Tables |
| `specs/integrations.md` | Integration clients (`*_client.py`), admin panels |
| `specs/config.md` | `config_loader.py`, `config_schema.json`, credential store |
| `specs/deployment.md` | Dockerfile, Nomad job ref, `.github/workflows/`, CLAUDE.md Production Deployment |

Content sources: distill from CLAUDE.md (primary) + codebase scan. Reference `docs/implementation/` only for details not in CLAUDE.md.

### Update Procedure

For each sub-spec:
1. Diff codebase scan results against spec content
2. Apply only incremental changes
3. Do NOT rewrite sections that are still accurate
4. Keep SPEC.md index in sync with actual spec files

## Target 3: Agent Workflow Guides (`docs/guides/`)

Human-readable guides that instruct an AI agent on how to work with the codebase —
maintaining what exists and adding new features. Procedural (step-by-step),
not reference (lookup). Written in clear English but still concise.

Structure: `docs/guides/README.md` (index) → 9 workflow guides (≤200 lines each).

**Guide structure** (each guide ≤200 lines):

```markdown
# {Title}

## When to Use This Guide
(1-2 lines: what task triggers this guide)

## Prerequisites
(Files to read first, concepts to understand)

## Steps
### 1. {Step name}
- What to do, where, and why
- Key files: `path/to/file.py`
- Pattern to follow: `path/to/example.py:30-58`

### 2. {Step name}
...

## Checklist
- [ ] Item completed
- [ ] Tests pass
- [ ] Docs updated

## Common Mistakes
(Pitfalls specific to this workflow — things the agent might get wrong)
```

**Guide content sources:**

| Guide | Derive From |
|-------|------------|
| `adding-tool-module.md` | CLAUDE.md "Adding New Modules → New tool module" + existing tool module examples |
| `adding-agent.md` | CLAUDE.md "Adding New Modules → New domain agent" + `agent/home_agent/factory.py` pattern |
| `adding-integration.md` | CLAUDE.md integration client pattern + `overseerr_client.py` as canonical example |
| `adding-admin-panel.md` | CLAUDE.md "Adding New Modules → New Admin UI" + existing panels in `frontend/src/components/admin/panels/` |
| `adding-api-route.md` | Existing routers in `web/api/` + `app.py` route registration |
| `maintaining-agents.md` | Agent factories, instruction files, `specialized_agent_factory.py` |
| `maintaining-integrations.md` | Client singleton pattern, config_loader usage, credential store |
| `maintaining-frontend.md` | Frontend structure, Zustand stores, API client patterns |
| `maintaining-db.md` | Schema init pattern, connection pool, migration approach |

### Update Procedure

1. Check if new patterns emerged that existing guides don't cover (e.g., new factory pattern, new test helper)
2. Check if guide steps reference files/functions that no longer exist (stale refs)
3. Check if CLAUDE.md "Adding New Modules" section changed — guides must stay in sync
4. Update only guides with detected drift
5. If a wholly new workflow pattern emerged, flag it in the manifest rather than creating a guide — user should confirm scope first

### Writing Style for Guides

These are **human-readable** — use full English, not TERSE abbreviations. But still concise:
- Steps are imperative: "Create the file", "Add the import", "Register the router"
- Include concrete file paths and line references
- Show the pattern to follow with a real example from the codebase (not abstract)
- Include "Common Mistakes" — real pitfalls from Known Gotchas and e2e findings
- No filler, no motivation paragraphs — the agent knows why it's here
- Each guide is self-contained: an agent should be able to follow it without reading other guides
- Use mermaid diagrams for workflows, data flows, and dependency chains — not ASCII art

## TERSE Writing Style

CLAUDE.md and specs/ are written for LLM consumption. Minimize tokens, maximize info density.
Use common abbreviations naturally — the LLM reading these docs will understand them.

### Principles

- Tables over prose — structured data compresses better
- Drop articles and filler words
- Imperative mood, present tense
- `file:line` format for code refs
- One fact per line
- Mermaid diagrams for flows/dependencies/architecture — not ASCII art
- Target 30-55% token reduction vs conventional docs

## Scope & Safety

- **Only modify**: `CLAUDE.md`, `SPEC.md`, `specs/*.md`, `docs/guides/*.md`
- **Never modify**: source code, test files, cfg files, other docs outside these paths
- **Never delete** existing correct content — only add or update stale entries
- **Max diff per file**: 50 lines added/changed (except bootstrap)
- **Line budgets**: CLAUDE.md ≤500, SPEC.md ≤200, each sub-spec ≤300, each guide ≤200
- **Uncertain changes**: add to "Flagged for Review" section instead of applying
- **No git commits** — user reviews `git diff` after run

## Output

Write change manifest to `reports/e2e-doc-updates.md`:

```markdown
# Doc Update Report - {YYYY-MM-DD HH:MM}

## Summary
| Metric | Value |
|--------|-------|
| Files modified | N |
| Lines added | N |
| Lines removed | N |
| Lines changed | N |
| CLAUDE.md lines | N/500 |

## Changes Applied

### CLAUDE.md
| Section | Type | Detail | Trigger |
|---------|------|--------|---------|
| Database Tables | ADD row | `telemetry_usage` table | New CREATE TABLE in telemetry/db.py |
| Known Gotchas | ADD bullet | Gemini empty content on cache | CRITICAL finding in log analysis |

### specs/{file}.md
| Section | Type | Detail | Trigger |
|---------|------|--------|---------|
| Nomad tools | UPDATE | Added check_nomad_service_health | New FunctionTool in nomad_tools.py |

### docs/guides/{file}.md
| Guide | Type | Detail | Trigger |
|-------|------|--------|---------|
| adding-tool-module.md | UPDATE step 3 | New schema init pattern | Changed agent_tools_setup.py |

## Flagged for Review
(Items needing human judgment — uncertain drift, ambiguous changes)

## No Drift Detected
- specs/deployment.md — no changes to Docker/Nomad/CI
- specs/config.md — config_schema.json unchanged
```

## Important Notes

- Do NOT commit changes — user reviews `git diff` after the e2e run
- Typical run touches 1-5 files; if shell specs are empty, first run populates them all
- Accuracy over completeness — missing a new entry is better than adding a wrong one
- CLAUDE.md is highest priority — errors there affect every Claude Code session
- When in doubt, add to "Flagged for Review" instead of making the change
- Reference `docs/implementation/` only when populating empty shell specs — not on every run
- Apply TERSE style to all new content and any sections you rewrite
