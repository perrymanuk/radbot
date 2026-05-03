# EX (draft): Cross-family council loop polish — wire mm-council into the Scout/Telos/`/ship` lifecycle

**Status:** **Item 0 + Item 1.a SHIPPED** in [PR #113](https://github.com/perrymanuk/radbot/pull/113), merged 2026-05-03 as commit `f0e6e37` on `main`. CI quality-pipeline scored 100/100 (lint 10/10, build 10/10, unit+integration 30/30, functional e2e 30/30, visual regression 20/20). 67 new unit tests; 681/681 unit suite passes; specs `tools.md` + `storage.md` + `CLAUDE.md` updated in the same PR. Backward-compat audits documented in the PR description: zero return-text consumers outside the producer; 19 `db.list_section` callers all preserved exactly under sentinel back-compat semantics with one intentional migration (`_render_section` → `ACTIVE_EQUIVALENT` default per spec Item 0.c).

**Item 1.b + 1.c SHIPPED** in [PR #114](https://github.com/perrymanuk/radbot/pull/114), merged 2026-05-03 as commit `a0c42a2` on `main`. CI quality-pipeline scored 100/100 (lint 10/10, build 10/10, unit+integration 30/30, functional e2e 30/30, visual regression 20/20 — all 7 pages pixel-identical). Pure docs PR; pinned the From → To / Actor / Trigger transition table (spec Item 1.c) verbatim into `CLAUDE.md` § Telos lifecycle status state machine, `specs/agents.md` § Scout / Telos exploration lifecycle, `radbot/config/default_configs/instructions/scout.md` (status="proposed" entry-point note), and `.claude/skills/ship/SKILL.md` (Phase 11 step 5 flips linked EX `executing → completed` post-merge — single ownership; end-of-skill `/postmortem-ex <PR#>` pointer). Encoded the v1 concurrency invariant (single user, single active session per EX; no CAS/lock) and `metadata.superseded_by: "EX<N>"` shape pin.

**Item 3 SHIPPED** in [PR #115](https://github.com/perrymanuk/radbot/pull/115), merged 2026-05-03 as commit `5fb4138` on `main`. CI quality-pipeline scored 100/100 (lint 10/10, build 10/10, unit+integration 30/30, functional e2e 30/30, visual regression 20/20 — Anthropic LLM grader explicitly noted "the scout postmortem-processing instruction change has no frontend impact"). Pure docs PR; added section 7 "Process pending postmortems (user-driven, never autonomous)" to `radbot/config/default_configs/instructions/scout.md` (160 lines) covering the three-rule contract: (1) `metadata_filter` query for unprocessed postmortems, (2) parse `## Followups` markdown into `task`/`exploration`/`journal_insight` triples, derive deterministic `sha256(f"{jr_ref}|{role}|{ordinal}").hexdigest()[:16]` dedup key, dedup-query first then atomic `*_add` with `metadata_merge` in the SAME call (no add-then-update race), (3) `journal_update` with `followup_refs` as the UNION of dedup-hits and newly-created refs, only after every followup for that postmortem succeeded. Spec sync: extended `specs/agents.md` § Scout / Telos exploration lifecycle with a one-paragraph "Postmortem processing flow" pointer pinning the dedup-key derivation + `## Followups` markdown contract. Persona-paragraph edit to `main_agent.md` deferred to Item 6's PR per the implementation order's soft gate.

**Item 6 SHIPPED** in [PR #116](https://github.com/perrymanuk/radbot/pull/116), merged 2026-05-03 as commit `a86f08a` on `main`. CI quality-pipeline scored 100/100 across all five gates; path-guard auto_merge_blocked flagged because the diff touched `Makefile` (sensitive path) — merged via human-authenticated `gh pr merge` (Perry's PAT). First code-bearing PR in the council-loop sequence. **Beto retired** `inject_telos_context` from his `before_model_callback` (one-line drop in `assembly.py:317` plus the now-unused import) — token savings: ~75 tokens/turn anchor + ~500 tokens first-turn full block per beto session, pure waste on chitchat/routing turns. **Compensating persona paragraph** added to `main_agent.md` § Telos giving beto a static baseline awareness of his user (Perry/Austin/builds-AI-agents/values-terse-technical) plus on-demand `telos_get_section/entry/full` tool surface (27 TELOS_TOOLS retained). **Scout-as-root** continues to receive `inject_telos_context` (registered at `research_agent/factory.py:217-242`) — sole consumer post-Item-6. **AC #4 (b) automated baseline-snapshot test** at `tests/integration/test_item6_telos_read_regression.py` + `tests/fixtures/item6_regression_baseline.json` — patches `telos_db` with fixed Entry fixture, runs agent-side Telos read tools, parses markdown via existing `parse_telos_markdown` AST helper, compares structurally; `make regen-item6-baseline` re-writes baseline. AC #4 (a) routing + (c) chitchat documented as PR-checklist manual smoke (CI has no LLM client — non-deterministic gates can't run there). AC #1 producer-marker pinning anchored to actual `loader.py` markers (`TELOS ANCHOR` / `USER CONTEXT (Telos)` / `IDENTITY:` / `MISSION:`) per user direction — the spec's hypothetical `"## Mission"` / `"## Identity"` / `"ME:"` literals never existed in code (spec drift; meta-note line 22 warned about this). AC #5 smoke test deferred per Risks #5 (acknowledged-weak by spec). `specs/agents.md` updated at all four sites: line 54 callback list, line 57 (renamed `(beto only)` → `(scout-as-root only)` + Item-6-retirement note), line 139 (sole-consumer language + `factory.py:217-242` cite), line 325 (Callback Inventory `(scout-as-root only)` + retirement note). `grep -n "inject_telos_context" specs/agents.md` shows every match consistent — spec coherence AC met. 684/684 unit tests pass; new test_item6 integration test passes against baseline.

**What landed (concrete summary against the Implementation order section):**
- Item 0.a — `journal_add` / `journal_update` MCP tools at `radbot/mcp_server/tools/journal.py` (registered in `_MODULES`); direct wrappers around `telos_db.add_entry`/`update_entry` for `Section.JOURNAL`.
- Item 0.b — structured-success envelope `{status, ref_code, entry_id, section}` on `task_add`/`exploration_add`/`milestone_add`/`journal_add`; matching JSON `_err` envelope on all eight write-tool error paths; `metadata_merge` on `task_add`/`exploration_add`/`milestone_add`/`task_update`/`exploration_update` with whitelist-wins-silently precedence; optional `status` on `exploration_add`/`exploration_update` validated against extended `STATUS_VALUES`; `content`/`description` optional-or-whitespace-rejected trifecta on `*_update`. `_text_err`/`_json_err` split helpers in `project_tasks.py` keep terminal `*_complete`/`*_archive` returning human-readable text.
- Item 0.c — `format=json|markdown` + `metadata_filter` on `telos_get_section` and `format=json|markdown` on `telos_get_entry`; `_iso_default` enforces literal `Z` UTC suffix and handles `uuid.UUID`; `_entry_to_json_dict` is the single shape-of-truth helper. `db.list_section` refactored to the `_OMITTED` sentinel pattern with `ACTIVE_EQUIVALENT` default + `metadata_filter` JSONB containment kwarg. GIN index on `telos_entries.metadata` via `_apply_metadata_gin_index()` running as a sibling step inside `init_telos_schema()` (so it lands on existing deployments, not just freshly-created tables).
- Item 1.a — `STATUS_VALUES` now `{active, completed, archived, superseded, proposed, in_review, approved, executing}`; `ACTIVE_EQUIVALENT = frozenset({"active", "proposed", "in_review", "approved", "executing"})`. `_apply_status_check_constraint()` runs every startup: preflight aborts if any row violates the new set, then DEFINITION-aware semantic comparison via `_extract_constraint_status_set` (parsed allowed-set vs `STATUS_VALUES`) decides whether to DROP+ADD — closes Round 3 brittleness blocker against `pg_get_constraintdef` byte-string equality.
- Item 3 (defense-in-depth piece) — `db.add_entry` postmortem invariant covers MCP `journal_add` + agent-side `telos_add_journal` + direct callers; `telos_add_journal` normalizes `event_type="postmortem"` → set `metadata.type="postmortem"` AND default `metadata.processed_at=None`.

**Release-note pinned (operational):** code rollback to a pre-Item-1.a build is unsafe once any row holds a new lifecycle status (`proposed/in_review/approved/executing`). Recovery procedure: `UPDATE telos_entries SET status='active' WHERE status IN ('proposed','in_review','approved','executing');` → `ALTER TABLE telos_entries DROP CONSTRAINT IF EXISTS telos_entries_status_check;` → deploy older build. See Item 1.a Rollback below.

**Still open (per Implementation order — see end of doc):** Item 2 (`/review-ex` skill — sibling commit in `~/git/perrymanuk/claude-skills`, NOT radbot — next up); Item 4 (`/postmortem-ex` sibling skill, also in `~/git/perrymanuk/claude-skills`); Item 5 (followup conventions formalization — paperwork once Item 4 lands). All radbot-side work is now SHIPPED (Items 0/1.a/1.b/1.c/3/6 across PRs #113/#114/#115/#116). The remaining items live in the personal claude-skills marketplace, not this repo. The lifecycle ref-code flip from `EX_DRAFT_*` to a Telos `EX<N>` is still deferred — the spec body is 105KB, would dominate any PR diff, and on-disk markdown remains useful for git-diff-ing shipping status updates. Will be its own small operation when there's a clean reason to do it.

---

**Pre-merge status (preserved for context):** **APPROVED FOR IMPLEMENTATION (frozen 2026-05-03)** after THREE rounds of `/mm-council:evaluate` cross-family review (Opus + Gemini 3.1 Pro + GPT-5.5, three sub-rounds each, personaless synthesis). Round 1 found 2 architectural blockers (MCP write surface absent + Scout autonomous trigger) — resolved. Round 2 found 3 semi-architectural blockers (chain race, step ordering, dedup-key determinism) — resolved. Round 3 found 5 implementation-detail blockers (`list_section` sentinel, UUID JSON serialization, `db.add_entry` defensive normalization + agent-side `event_type` bypass, CHECK constraint definition equality brittleness, `--supersede`/`--force-new` ordering) — **all five resolved in this final pre-implementation pass** with concrete code snippets pinned in Items 0.c, 1.a, 3, and 4. Council convergence verdict (3-of-3, high confidence): the architectural design space is empirically exhausted; remaining majors are normal PR-iteration territory. **No fourth council pass.** Open Item 0+1.a as the foundational PR; treat further sibling issues as PR-review feedback.

**Round 3 majors (~14, deferred to PR-review)** — listed here as a punch-list for the implementation PR description; resolve in the PR or as immediate follow-ups: per-tool `metadata_merge` whitelist enumeration (Item 0.b.iii); JSON `_err` envelope global-vs-per-tool decision (Item 0.b.iv — recommend `_json_err`/`_text_err` split helpers in `project_tasks.py`); `init_telos_schema()` wrapper refactor + `SCHEMA_INITS` registry update (Item 0.c); GIN-index definition-aware migration (Item 0.c); `## Followups` markdown grammar pin + `_None_` sentinel + re-ordinalization footgun documentation (Item 3 + Item 4); deterministic `parent_project` derivation chain (Item 3); pre-strip marker-balance validator (Item 2 + Item 4); `/postmortem-ex` step-7 partial-failure recovery (link existing JR if EX block missing) (Item 4); per-tool `_err` envelope coverage table (Item 0.b.iv); content optional-vs-empty handler branch (Item 0.b.i); `_iso_default` sub-second precision (Item 0.c); Item 6 ordering note rewrite (Implementation order); backward-compat audit grep syntax fix (Item 0.b.iv).
**Author:** Claude Code (chat session, 2026-05-02 → 2026-05-03), in collaboration with Perry.
**Method:** ad-hoc design conversation grounded in radbot's current architecture, the new `mm-council` plugin (already shipped to `perrymanuk/claude-skills`), and AI Intel wiki research on plan-execute-handoff + multi-model-agents. Stress-tested by THREE rounds of Opus + Gemini 3.1 Pro + GPT-5.5 cross-family council (3 sub-rounds each, personaless synthesis); revisions below address all blocker/major findings from all three reviews. Each council round: (a) evaluated the prior revision against grounded code evidence, (b) surfaced sibling issues the prior revision introduced, (c) the spec author folded in fixes and re-ran the council. Pattern recognized after pass 2: each spec edit risks introducing a sibling issue when worked from memory rather than re-grounded against code; Round 3 revision was preceded by re-reading every cited code path before editing.

## Why

Scout's existing same-family plan council (3-round, four Gemini personas — Archie, Sentry, Impl, Echo — see `radbot/tools/council/critics.py:33-49` for `_council_model` + `_run_critic` and lines `138-196` for the four FunctionTool wrappers; also `specs/agents.md` "Scout Plan Council") catches the obvious before plans are persisted. But all four critics share Gemini's blind spots — the largest single quality lever per `[[multi-model-agents]]` (Microsoft 365 Researcher made cross-family the default; GitHub Copilot CLI's "Rubber Duck" closed 74.7% of the Sonnet→Opus SWE-Bench gap with a single cross-family review seat).

The new `mm-council` skill (Opus + Gemini + GPT-5, direct provider APIs, three-round protocol with personaless synthesis) is now live in the personal marketplace and can run from this Claude Code session. The plugin already does the hard part. What's missing is the **wiring** that turns it into a coherent loop:

1. A way to invoke it against an `EX<N>` without manual copy-paste each time
2. A documented status state-machine so two Claude Code sessions don't race the same plan
3. A way for `/ship` to feed a postmortem back to Scout after the merge
4. A way for Scout to **process** that postmortem (mark read, generate followups) and for the human to review what Scout decided
5. A trim of `inject_telos_context` so the Telos full block isn't wasted on beto's chitchat path

Radbot needs a **small, contained MCP surface expansion** before the rest of the plan is implementable. The current MCP write surface is `task_add/update/complete/archive`, `exploration_add/update/archive`, `milestone_add/complete` (all in `radbot/mcp_server/tools/project_tasks.py`); read-only `telos_*` tools are in `radbot/mcp_server/tools/telos.py`. There is no journal-write MCP tool and no generic update-by-section tool today — the agent-side `telos_add_journal` and `telos_update_entry` exist but are **not exposed via MCP**. Item 0 below adds the minimal MCP wrappers needed; Items 1–6 then become mostly conventions, instruction-file edits, and one orchestration skill.

## Findings from codebase review (2026-05-02)

### Existing council path (stays as-is — tier 1 of two-tier review)

- `radbot/tools/council/critics.py:33-43` — `_council_model()` resolves to scout's configured model (Gemini 3.1 Pro). Cross-family was tracked as PRJ1/PT18 ("blocked on LiteLLM infra in hashi-homelab"). With mm-council at the human gate, **PT18 is no longer on the critical path** for council quality — the cross-family review now happens out-of-process at the Claude Code session.
- The Round 1 / Round 2 / Round 3 protocol (`personas.py`, `triggers.py`) and the persistence contract on `EX<N>.content` (`## Council Review` section) all stay verbatim.

### MCP server surface today (corrected after grounded review)

`radbot/mcp_server/tools/__init__.py:19-21` registers six modules: `telos`, `wiki`, `projects`, `project_tasks`, `tasks`, `memory`. Verified write-tool surface:

- `project_tasks` (`radbot/mcp_server/tools/project_tasks.py`): `milestone_add`, `milestone_complete`, `task_add`, `task_update`, `task_complete`, `task_archive`, `exploration_add`, `exploration_update`, `exploration_archive`.
- `telos` (`radbot/mcp_server/tools/telos.py`): **read-only** — `telos_get_full`, `telos_get_section`, `telos_get_entry`, `telos_search_journal`.
- `wiki` / `projects` / `tasks` / `memory`: orthogonal to this plan.

**Three capability gaps the original draft missed (each becomes a blocker for Items 2–5 unless resolved):**

1. **No journal-write MCP tool.** Agent-side `telos_add_journal` exists (`radbot/tools/telos/telos_tools.py:207-233`) but is **not exposed over MCP**. Its signature accepts only `entry: str`, `event_type: str = ""`, `related_refs: list[str] | None` — no arbitrary `metadata` kwarg. The plan needs a richer journal-write path AND a journal-update path (for the postmortem `processed_at` flag).
2. **No generic update-by-section MCP tool.** Agent-side `telos_update_entry` exists (`telos_tools.py:489-525`) and supports `content`, `metadata_merge`, `status` — but it is not exposed over MCP. It also validates `status` against a closed `STATUS_VALUES` set in `telos_tools.py`, so introducing the lifecycle states `proposed / in_review / approved / executing / completed` requires extending that set AND any matching DB CHECK constraint in `radbot/tools/telos/db.py`.
3. **`telos_get_section` cannot filter by metadata and returns rendered markdown, not structured JSON.** `radbot/mcp_server/tools/telos.py:145-166` calls `telos_db.list_section(sec, status=status_filter, order_by=order)` then renders entries to a markdown blob. Items 3 and 5 require querying journal entries by `metadata.type` and `metadata.processed_at` — neither possible via the current MCP surface. Client-side post-filter against rendered markdown was rejected by all three council panelists as too fragile (re-parsing markdown to extract metadata).

### `inject_telos_context` registration

- Implementation: `radbot/tools/telos/callback.py:33-69`. Two-tier:
  - **Anchor** (~300B, capped 500): every turn, into `system_instruction`
  - **Full block** (~2KB, capped 2048: mission + problems + goals + projects + challenges + wisdom + last 5 journal entries): first turn of session only, gated by `state["telos_bootstrapped"]`
- Registered for **beto** at `radbot/agent/assembly.py:317` (verified — `_build_beto`'s `before_model_callback` list).
- For **scout-as-root**: callback line is in `radbot/agent/research_agent/factory.py:217-242` (the `if as_root:` block), NOT in `assembly.py`'s manifest branch as the original draft asserted. The `as_root=True` flag itself is wired by the manifest path (`assembly.py` → `AgentDef(role="root")` → `_resolve_assembly`) and the `chat_sessions.agent_name` selector. Item 6 verification must cover **both** locations: `factory.py:217-242` (the actual callback registration) and `assembly.py` (the gate that decides whether scout is built `as_root`).
- Sub-agents do **not** get this callback per `_attach_subagent_callbacks` design (verified — `assembly.py:273-294`, `_SUBAGENT_BEFORE_CBS` excludes `inject_telos_context`).

### `/ship` skill termination point (corrected)

`.claude/skills/ship/SKILL.md` actual phase numbering: **Phase 11** (line 297) is the user-authenticated merge; **Phase 12** (line 349) is cleanup. The original draft's "phase 12 is the user-authenticated merge / new phase 13" was off-by-one. The new postmortem step is a sibling Claude Code skill `/postmortem-ex` invoked by the user after `/ship` returns — recommendation in Item 4. If integrated into `/ship` directly it would land as Phase 12 (cleanup shifts to 13), but a sibling skill is preferred (see Item 4 rationale).

### Existing draft-plans convention

`docs/plans/EX_DRAFT_*.md` is the on-disk staging area for plans before they land in Telos as `EX<N>` entries. This file follows that convention.

## Plan

### Item 0 — MCP work-items (prerequisite for Items 2–5)

Four small additions to `radbot/mcp_server/tools/`. Each one is a thin MCP wrapper over an existing agent-side function or a parameter extension to an existing tool. Combined with Item 1.a, the PR is ~150 LoC + tests + one migration (header estimate ~120 covers Item 0 alone; see Implementation order).

**0.a — Add `journal_add` and `journal_update` MCP tools** (new file: `radbot/mcp_server/tools/journal.py`, register in `mcp_server/tools/__init__.py`'s `_MODULES`).

The MCP `journal_add` is a **direct wrapper around `telos_db.add_entry(Section.JOURNAL, ...)`** — it does NOT go through agent-side `telos_add_journal` (which has a narrower signature and no return-shape contract). Extending agent-side `telos_add_journal` to accept arbitrary metadata is a separate consistency improvement (deferred — not a prerequisite for this MCP tool).

```python
# journal_add — accepts arbitrary metadata dict; return shape per Item 0.b.iv contract.
inputSchema = {
    "type": "object",
    "properties": {
        "entry":    {"type": "string"},
        "metadata": {"type": "object", "additionalProperties": True},
    },
    "required": ["entry"],
    "additionalProperties": False,
}
# Implementation: call telos_db.add_entry(Section.JOURNAL, entry, metadata=metadata or {}).
# Returns: per the structured contract pinned in Item 0.b.iv (success: {status, ref_code, entry_id, section};
#          error: {status: "error", message: ...}).

# journal_update — supports metadata_merge + status; pinned to journal section.
# status param is restricted to journal-meaningful values (lifecycle states like
# proposed/in_review/approved/executing are nonsense for journal rows).
inputSchema = {
    "type": "object",
    "properties": {
        "ref_code":       {"type": "string"},
        "metadata_merge": {"type": "object", "additionalProperties": True},
        "status":         {"type": "string", "enum": ["active", "completed", "archived", "superseded"]},
    },
    "required": ["ref_code"],
    "additionalProperties": False,
}
# Returns: per the structured _err envelope in Item 0.b.iv (success path can be a simple OK dict
#          since callers already know the ref_code; error path is the JSON {status:"error",message:...}).
```

**0.b — Extend the project_tasks/exploration MCP write surface.** Six additive changes to `radbot/mcp_server/tools/project_tasks.py`:

- **0.b.i — `exploration_update`: add optional `status` param AND make `content` optional.** Currently the schema (`project_tasks.py:164-184`) takes `ref_code, content (required), parent_project, parent_milestone`. Two changes: (1) add `status: string` validated against `STATUS_VALUES` after Item 1.a's extension lands; (2) **drop `content` from `required`** — handler treats **absent** `content` key as "leave body unchanged" (mirrors agent-side `telos_update_entry`'s `if content:` check at `telos_tools.py:514-515`); a **present empty/whitespace** `content` value remains an error (`_err("content must not be whitespace if supplied; omit the key to leave body unchanged")` — the existing handler at `project_tasks.py:497-499` rejects that case today and the new schema must preserve the rejection rather than silently degrading). Without (2), every status-only transition in Item 1.c's table (`approved → executing`, `executing → completed`, recovery flips) would be forced to fetch and round-trip the full body, widening the data-loss window under any race. Apply the same `content`-optional change to `task_update` for consistency (its `description` field already uses the same "leave unchanged if absent" semantics in the handler). **Test all three cases for both tools:** absent → unchanged; non-empty → replaces; empty/whitespace → error.
- **0.b.ii — `exploration_add` AND `task_add`: add optional `status` (exploration only) AND `metadata_merge` (both, **blocker fix**).** Currently `exploration_add` has only `parent_project, topic, notes` (required: `parent_project, topic`); `task_add` has `parent_project, description, parent_milestone, title, category, task_status` (required: `parent_project, description`). Two changes:
  1. Add optional `status: string` (validated against `STATUS_VALUES`) to `exploration_add` only — without this, every Scout-created exploration inherits the table default `'active'` and needs an immediate second `exploration_update` call to flip to `'proposed'`.
  2. **Add `metadata_merge: {"type": "object", "additionalProperties": True}` to BOTH `task_add` AND `exploration_add` input schemas** so callers can attach arbitrary metadata (e.g. `source_postmortem`, `postmortem_followup_role`, `postmortem_followup_key`) atomically at creation. **This closes the chain-race blocker from Round 2 council:** without it, Scout's `task_add → task_update(metadata_merge={...})` and `exploration_add → exploration_update(metadata_merge={...})` chains have a window where a crash between calls leaves an untagged followup that the dedup query cannot find. With this change, Scout sets all dedup metadata in the SAME `*_add` call (one DB write, no race).
- **0.b.iii — Add `metadata_merge: object` to `task_update` AND `exploration_update` (extends 0.b.ii to update tools).** The current `_do_task_update` (`project_tasks.py:390-438`) builds a `meta` dict from the four whitelisted keys (`title, category, task_status, parent_milestone`) and passes it as `metadata_merge=meta or None`; the inputSchema declares `additionalProperties: False`, so passing arbitrary extra fields is rejected at JSON-schema validation. Add `metadata_merge: {"type": "object", "additionalProperties": True}` to both `*_update` schemas (mirroring 0.b.ii). **Merge precedence (load-bearing — same rule for all four tools — `task_add`, `exploration_add`, `task_update`, `exploration_update`):** the handler shall start with `caller_meta = arguments.get("metadata_merge", {}).copy()`, then overlay the whitelist-derived dict so **whitelist keys WIN on collision** (the dedicated schema fields are authoritative for `title/category/task_status/parent_milestone/parent_project`; `metadata_merge` is the typed escape hatch for everything else). The collision is **silent** (3-of-3 council consensus to keep silent rather than error — LLM tool-call ergonomics over strict bug detection). Add unit tests covering (a) no-collision merge (caller's `source_postmortem` survives unchanged); (b) collision (caller's `task_status` is silently overridden by the dedicated field, no error raised, both for `*_update` AND `*_add`).
- **0.b.iv — Structured return contract for ALL `*_add` MCP tools (consolidated single source of truth).** Today every MCP write returns `mcp_types.TextContent` with a human-readable string (see `_do_task_add` at `project_tasks.py:380-387` returning `"Added task \`{ref_code}\` ..."` and `_do_exploration_add` at `project_tasks.py:483-489`). Items 3 and 4 chain `task_add → ...`, `exploration_add → ...`, `milestone_add → ...`, and `journal_add → ...` using the auto-assigned ref code — Scout needs to learn the ref_code without re-querying. **Change every `*_add` handler** (`_do_task_add`, `_do_exploration_add`, `_do_milestone_add`, plus the new `_do_journal_add` from 0.a) to return:

  ```python
  mcp_types.TextContent(type="text", text=json.dumps({
      "status": "success",
      "ref_code": "<NEW>",   # PT<N> | EX<N> | MS<N> | JR<N>
      "entry_id": "<uuid>",
      "section":  "<section_name>",
  }))
  ```

  **Error envelope (load-bearing — closes the 3-of-3 council finding):** all four `*_add` handlers' `_err()` returns must ALSO be JSON: `TextContent(text=json.dumps({"status": "error", "message": "<reason>"}))`. Callers branch on `payload["status"]` after `json.loads(response.text)` — both success and error parse uniformly, no try/except + heuristic-detection footgun. Apply the same `_err` JSON envelope to the four `*_update` handlers and `journal_update` since chained callers may want to error-handle uniformly. The other write tools (`task_complete`, `task_archive`, `exploration_archive`, `milestone_complete`) keep their human-readable text returns — they're terminal operations whose callers already know the ref_code (documented intentional inconsistency; if a future EX needs structured returns from those, migrate then).

  **`milestone_add` rationale for inclusion:** uniformity across the creation surface; even if no current chain needs `MS<N>`, future Scout patterns shouldn't have to special-case which `*_add` returns JSON. Cost: one handler change.

  **Backward-compat audit (mandatory implementation step):** before the Item 0+1.a PR merges, grep the repo + personal claude-skills for prose-substring consumers of the old return text:
  ```bash
  grep -rn "Added task \`" tests/ radbot/ ~/.claude/  || true
  grep -rn "Added exploration \`" tests/ radbot/ ~/.claude/  || true
  grep -rn "Added milestone \`" tests/ radbot/ ~/.claude/  || true
  grep -rn "Added journal" tests/ radbot/ ~/.claude/  || true
  ```
  Any hits get migrated to `json.loads(response.text)["ref_code"]` IN THE SAME PR. List affected files in the PR description.

- **0.b.v — `_do_*` handlers must combine `metadata_merge` correctly.** For both `_add` and `_update` handlers: `combined = {**arguments.get("metadata_merge", {}), **whitelist_meta}` (Python dict order — second overlays first, so whitelist wins per 0.b.iii rule). Pass through to `telos_db.add_entry(metadata=combined)` (for `_add`) or `telos_db.update_entry(metadata_merge=combined)` (for `_update`). Note the agent-side `telos_db.add_entry` and `telos_db.update_entry` both accept the resulting dict — no DB-layer changes needed.

**0.c — Extend `telos_get_section` AND `telos_get_entry`; redefine the default active-equivalent set; add a GIN index.**

`telos_get_section` schema:

```python
inputSchema = {
    "type": "object",
    "properties": {
        "section":          {"type": "string"},
        "include_inactive": {"type": "boolean"},  # default false
        "metadata_filter":  {"type": "object", "additionalProperties": True},  # NEW — matched as JSONB @> in telos_db
        "format":           {"type": "string", "enum": ["markdown", "json"]},  # NEW — default "markdown" for backwards compat
    },
    "required": ["section"],
    "additionalProperties": False,
}
```

`telos_get_entry` schema (load-bearing for Item 2 / Item 4 idempotency — current `_render_entry` at `radbot/mcp_server/tools/telos.py:169-198` returns markdown wrapped in `### section: ref_code`, `**Status:**`, body, `**Metadata:**` blocks; reading and writing it back via `exploration_update` would compound markdown framing every re-run):

```python
inputSchema = {
    "type": "object",
    "properties": {
        "section":  {"type": "string"},
        "ref_code": {"type": "string"},
        "format":   {"type": "string", "enum": ["markdown", "json"]},  # NEW — "markdown" preserves today's behavior; "json" returns the full Entry shape
    },
    "required": ["section", "ref_code"],
    "additionalProperties": False,
}
```

When `metadata_filter` is non-empty on `telos_get_section`, `radbot/tools/telos/db.py:list_section` adds a JSONB `WHERE metadata @> %s::jsonb` clause.

**JSON transport contract (load-bearing).** When `format="json"`, the MCP handler shall return:

```python
mcp_types.TextContent(type="text", text=json.dumps(payload, default=_iso_default))
```

where `_iso_default` is pinned (load-bearing — closes the council findings on `Z`-suffix drift AND `uuid.UUID` crash):

```python
def _iso_default(obj):
    """JSON serializer for datetime → ISO 8601 with literal Z suffix; UUID → str.

    psycopg2 returns timezone-aware datetimes whose .isoformat() emits '+00:00',
    not the literal 'Z' that consumers parse against. Force UTC + literal Z.
    psycopg2 also returns uuid.UUID for UUID columns; json.dumps would crash
    without explicit handling — entry_id is in every payload shape.
    """
    import uuid
    from datetime import datetime, timezone
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
```

**Required helper — `_entry_to_json_dict`** (closes Round 3 GPT-5 finding on `Section` enum + UUID rendering): every JSON-shaped MCP response goes through this single helper so all conversions are explicit and consistent.

```python
def _entry_to_json_dict(entry: "Entry") -> dict:
    """Convert a telos_db.Entry to a JSON-native dict for MCP transport.

    Explicitly converts UUIDs and Section enums; leaves datetimes for _iso_default
    to handle at json.dumps time. Used by both telos_get_entry and telos_get_section
    to guarantee identical payload shape across the JSON contract.
    """
    return {
        "ref_code":   entry.ref_code,
        "entry_id":   str(entry.entry_id),
        "section":    entry.section.value,
        "status":     entry.status,
        "content":    entry.content,
        "metadata":   entry.metadata or {},
        "created_at": entry.created_at,   # serialized by _iso_default at json.dumps time
        "updated_at": entry.updated_at,
    }
```

with payload shapes:

- `telos_get_entry` → `{"entry": {"ref_code": "EX1", "entry_id": "<uuid>", "section": "explorations", "status": "proposed", "content": "<raw body>", "metadata": {...decoded JSONB dict...}, "created_at": "2026-05-03T12:00:00Z", "updated_at": "2026-05-03T12:00:00Z"}}`
- `telos_get_section` → `{"entries": [<entry>, <entry>, ...]}`

Timestamps are ISO 8601 with literal `Z` suffix (UTC), per `_iso_default`; `metadata` is the decoded JSONB dict (not stringified); `null` ref_code rows render as `"ref_code": null`. Callers use `json.loads(response.text)` to parse. This is the single source of truth for the JSON envelope; every consumer (`/review-ex`, `/postmortem-ex`, Scout's instructions) shall parse against this exact shape. Unit test: assert every timestamp in the rendered payload matches `r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"` (literal Z, not `+00:00`).

**Active-equivalent default redefinition (resolves the lifecycle-states-hidden bug).** `telos_get_section`'s current default filters to `status='active'` (`telos.py:145` — note: the prior revision cited `:155`, off by 10; corrected here). After Item 1.a accepts `proposed/in_review/approved/executing` as valid statuses, the default would silently omit all in-flight EXes from Scout's first-message poll, `/review-ex` pre-flight reads, and ad-hoc listings. **Fix (closes 3-of-3 council finding that the previous revision plumbed `ACTIVE_EQUIVALENT` only at the MCP layer, leaving `db.list_section` callers exposed):**

1. Define `ACTIVE_EQUIVALENT = frozenset({"active", "proposed", "in_review", "approved", "executing"})` in `radbot/tools/telos/models.py` next to `STATUS_VALUES`.
2. **Change `radbot/tools/telos/db.py:list_section`'s default to `ACTIVE_EQUIVALENT` via a SENTINEL pattern (load-bearing — closes Round 3 3-of-3 blocker on default-arg back-compat collision).** Naive `status_in: Optional[Iterable[str]] = ACTIVE_EQUIVALENT, status: Optional[str] = None` defaults break two ways: (i) any legacy caller passing `status="active"` triggers the mutual-exclusion `ValueError` because the implicit `status_in=ACTIVE_EQUIVALENT` default collides with the explicit `status`; (ii) any legacy caller passing `status=None` (which used to mean "all statuses") silently changes meaning to `ACTIVE_EQUIVALENT`. Use a private sentinel to distinguish "argument omitted" from "argument explicitly None":

   ```python
   _OMITTED = object()  # module-level sentinel

   def list_section(
       section: Section,
       *,
       status: Any = _OMITTED,        # _OMITTED = use status_in; None = all statuses; "active"/etc = single
       status_in: Any = _OMITTED,     # _OMITTED + status _OMITTED → ACTIVE_EQUIVALENT; None = all
       limit: Optional[int] = None,
       order_by: str = "sort_order_asc",
   ) -> List[Entry]:
       # Resolve the filter
       if status is not _OMITTED and status_in is not _OMITTED:
           raise ValueError("status and status_in are mutually exclusive")
       if status is _OMITTED and status_in is _OMITTED:
           status_in = ACTIVE_EQUIVALENT          # default new behavior
       if status_in is None or status is None:
           where_filter = None                    # all statuses
       elif status is not _OMITTED:
           where_filter = ("status = %s", [status])
       else:
           # Materialize iterable to list — psycopg2 doesn't reliably adapt frozensets/sets for ANY()
           where_filter = ("status = ANY(%s)", [list(status_in)])
       # ... build WHERE/SQL, execute ...
   ```

   Backward-compat semantics:
   - Caller passes nothing → `ACTIVE_EQUIVALENT` set is used (covers `proposed/in_review/approved/executing` plus legacy `active`).
   - Caller passes `status="active"` → legacy single-status filter (back-compat for any caller that explicitly wants legacy-active-only).
   - Caller passes `status=None` (or `status_in=None`) → returns all statuses (back-compat for the old `status=None` "all" semantics).
   - Caller passes `status_in=[...]` → explicit set filter; iterable is `list()`-materialized for psycopg adapter compatibility.
   - WHERE clause when `status_in` is the active filter: `status = ANY(%s)`. **No Python post-filter** — default listing must scale.

   **Mandatory grep audit (load-bearing AC, in same PR):** `grep -nE 'list_section\([^)]*status=' radbot/` shall be executed; every hit reviewed and migrated if needed (a hit passing `status="active"` is correct under back-compat semantics; a hit passing `status=None` is correct under back-compat semantics; any hit passing both — none expected — must be rewritten). The PR description shall list the audited files.
3. The MCP `_render_section` accepts the existing `include_inactive: bool` param and translates: `include_inactive=False` (default) → `status_in=ACTIVE_EQUIVALENT`; `include_inactive=True` → `status_in=None` (all statuses).
4. `completed`, `archived`, `superseded` are the inactive set — opt-in via `include_inactive=True`.

Integration tests (mandatory ACs):
- Create a `proposed` EX, call `telos_get_section({section: "explorations"})` with no `include_inactive` — assert the EX appears.
- Call agent-side `telos_db.list_section(Section.EXPLORATIONS)` with no kwargs — assert the same `proposed` EX appears (proves `db.list_section` default propagated).
- Call `telos_db.list_section(Section.EXPLORATIONS, status="active")` — assert ONLY the `active` rows appear (proves back-compat path).
- Call `telos_db.list_section(Section.EXPLORATIONS, status="active", status_in=ACTIVE_EQUIVALENT)` — assert raises `ValueError`.

**GIN index migration (`radbot/tools/telos/db.py`) — sibling step, NOT via `create_index_sqls`.** The previous revision proposed adding `idx_telos_metadata` to `init_table_schema()`'s `create_index_sqls` list; council Round 2 caught (3-of-3) that `init_table_schema` (`radbot/tools/shared/db_schema.py:11-45`) only executes index SQLs when the table is freshly created. On every existing deployment (which is every real deployment), the index would silently never land, breaking Item 5's sub-second-on-5000-rows AC. **Fix:** add `_apply_metadata_gin_index()` as a sibling step inside `init_telos_schema()`, running unconditionally on every startup:

```python
def _apply_metadata_gin_index() -> None:
    """Ensure the GIN index on telos_entries.metadata exists. Idempotent."""
    from radbot.db.connection import get_db_connection, get_db_cursor

    with get_db_connection() as conn:
        with get_db_cursor(conn, commit=True) as cursor:
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_telos_metadata "
                "ON telos_entries USING GIN (metadata);"
            )

def init_telos_schema() -> None:
    init_table_schema(...)            # existing
    _apply_metadata_gin_index()        # NEW — runs every startup, cheap when index exists
    _apply_status_check_constraint()   # NEW — see Item 1.a
```

`CREATE INDEX IF NOT EXISTS` is fully idempotent; cost on subsequent startups is one metadata-table query when the index exists. Test: drop the index, restart, assert it re-appears via `\d telos_entries`.

**Acceptance criteria (EARS):**
- The MCP server shall expose `journal_add` and `journal_update` tools backed directly by `telos_db.add_entry`/`telos_db.update_entry` for `Section.JOURNAL` (not via agent-side `telos_add_journal`).
- When `journal_add` is called with `metadata={...}`, the resulting entry shall persist the full metadata dict in the JSONB `metadata` column.
- **Structured-return contract (Item 0.b.iv).** When `task_add`, `exploration_add`, `milestone_add`, or `journal_add` returns success, the response `TextContent.text` shall be parseable via `json.loads(...)` and shall contain `{"status": "success", "ref_code": "<assigned>", "entry_id": "<uuid>", "section": "<section>"}`. When any of the same tools return an error (validation, missing parent, etc.), the response `TextContent.text` shall ALSO be parseable via `json.loads(...)` and shall contain `{"status": "error", "message": "<reason>"}`. **Test:** (a) chained `task_add → task_update(ref_code=parsed["ref_code"], metadata_merge={...})` succeeds without any intervening read; (b) `json.loads(error_response.text)["status"] == "error"` succeeds (no plain-text fallback).
- **Backward-compat audit (Item 0.b.iv).** Before merge, `grep -rn "Added (task|exploration|milestone|journal)" tests/ radbot/ ~/.claude/` shall be run; any prose-substring consumer shall be migrated to `json.loads(response.text)["ref_code"]` IN THE SAME PR. List of migrated files shall appear in the PR description.
- **Atomic followup metadata (Item 0.b.ii — closes the chain-race blocker).** When `task_add` or `exploration_add` is called with `metadata_merge={k: v, ...}`, the supplied keys shall be JSONB-merged into the new entry's `metadata` column at creation time (one DB write, no race window). **Test:** simulate Scout's `task_add({metadata_merge: {source_postmortem: "JR42"}})` followed by an immediate process kill; restart Scout's processing; assert the previously-created PT is found by the `metadata_filter: {source_postmortem: "JR42"}` query and dedup correctly skips it.
- When `exploration_update` or `task_update` is called with `metadata_merge={k: v, ...}`, the supplied keys shall be shallow-merged into the entry's `metadata` column **with whitelist-derived keys (`title`/`category`/`task_status`/`parent_milestone`/`parent_project`) silently winning on collision** (same precedence rule applies to `*_add` per 0.b.iii). Empty `metadata_merge` (or absent) shall be a no-op on metadata. **Test:** (a) caller's `source_postmortem` survives; (b) caller's `task_status="done"` is silently overridden when the dedicated `task_status` field is also supplied (no error raised — 3-of-3 council consensus to keep silent).
- When `exploration_update` is called WITHOUT the `content` key, the entry's body shall remain unchanged. When called WITH a non-empty `content`, the body shall be replaced. When called WITH an empty/whitespace `content`, the call shall fail with `_err("content must not be whitespace if supplied; omit the key to leave body unchanged")`. Same three-case behavior for `task_update`'s `description` field.
- When `exploration_add` is called with `status="<allowed>"`, the new entry shall be created with that status; absent → defaults to `'active'` for back-compat (Scout's instructions explicitly pass `status="proposed"` per Item 3).
- When `exploration_update` is called with `status="<allowed>"`, the entry shall transition to that status; invalid values shall fail with the JSON `_err` envelope citing the allowed set.
- When `journal_update` is called with a `status` value, that value shall be one of `{active, completed, archived, superseded}` (lifecycle states are not valid for journal rows; the `enum` constraint enforces this at JSON-schema time).
- When `telos_get_section` is called with `metadata_filter={k: v, ...}`, the result shall include only entries whose `metadata` JSONB `@>` the supplied object.
- When `telos_get_section` or `telos_get_entry` is called with `format="json"`, the response shall be `TextContent` whose `.text` is the JSON-encoded payload defined above (not rendered markdown). Every timestamp string shall match `r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"` (literal `Z`, not `+00:00`); `metadata` shall be the decoded JSONB dict.
- **Default-active redefinition (Item 0.c — single source of truth).** When `telos_get_section` is called with default `include_inactive=False`, the result shall include entries whose status is in `ACTIVE_EQUIVALENT = {active, proposed, in_review, approved, executing}` and shall exclude `completed/archived/superseded`. The same default shall apply to `radbot/tools/telos/db.py:list_section` when called with no `status`/`status_in` kwarg. **Integration tests:** (a) a freshly-created `proposed` exploration appears in the default MCP `explorations` listing; (b) the same `proposed` exploration appears in the default agent-side `db.list_section(Section.EXPLORATIONS)` call; (c) `db.list_section(Section.EXPLORATIONS, status="active")` returns only legacy-active rows (back-compat); (d) `db.list_section(Section.EXPLORATIONS, status="active", status_in=ACTIVE_EQUIVALENT)` raises `ValueError`.
- `radbot/tools/telos/db.py:list_section` signature shall be `(section, *, status_in: Optional[Iterable[str]] = ACTIVE_EQUIVALENT, status: Optional[str] = None, limit, order_by)`; `status` and `status_in` shall be mutually exclusive.
- The `idx_telos_metadata` GIN index shall exist on `telos_entries.metadata` after `init_telos_schema()` runs, regardless of whether the `telos_entries` table existed before this migration. **Test:** drop the index manually, restart the web service, assert the index re-appears.

**Spec to update:** `specs/tools.md` (telos MCP tool table + `*_add` return contract), `specs/storage.md` (the new GIN index + JSONB query path + `status_in` on `list_section`), `CLAUDE.md` (`ACTIVE_EQUIVALENT` constant + new return-contract pattern).

---

### Item 1 — Status state-machine convention on `telos_entries.status`

The column exists. Three concrete sub-tasks beyond pure docs:

**1.a — Extend `STATUS_VALUES` and ADD a DB CHECK constraint.** The closed `STATUS_VALUES` set is defined in `radbot/tools/telos/models.py:122` (the AC originally said `telos_tools.py` — corrected to `models.py`). The set is imported and enforced at **four sites** that all need to be re-verified after the extension:

1. `radbot/tools/telos/telos_tools.py:519-523` — agent-side `telos_update_entry`
2. `radbot/tools/telos/db.py:101` — `db.add_entry` (raises `ValueError` if status not in set; both `db.add_entry` and `db.update_entry` import the same `STATUS_VALUES`)
3. `radbot/tools/telos/db.py:146` — `db.update_entry`
4. New MCP `_do_exploration_update` and `_do_exploration_add` handlers (Item 0.b.i/0.b.ii) — must validate `status` against the same set

Today the set is `{"active", "completed", "archived", "superseded"}`. Add `proposed`, `in_review`, `approved`, `executing` to that set. Because all four sites import the same `STATUS_VALUES`, a single edit propagates — but the unit-test surface needs to cover ALL four (a single edit could regress if a future contributor inlines a literal set somewhere).

For the database side: `radbot/tools/telos/db.py:25-50` currently declares the column as `status TEXT NOT NULL DEFAULT 'active'` with **no CHECK constraint** (validation is application-level only). Add a forward migration that creates a CHECK constraint matching the extended set. **The migration must be (1) preflight-checked, (2) DEFINITION-aware (not name-aware), and (3) generate the SQL allowed-list from `STATUS_VALUES` to avoid drift** — `ALTER TABLE ADD CONSTRAINT` is not idempotent in vanilla Postgres, and a name-only `IF NOT EXISTS` guard accepts a stale same-named constraint with the legacy 4-status set, silently no-op'ing while the DB rejects new lifecycle states at runtime (3-of-3 council finding).

**Python implementation** in `radbot/tools/telos/db.py` — **definition match uses SEMANTIC set comparison** (closes Round 3 blocker on `pg_get_constraintdef` string-equality brittleness; PostgreSQL normalizes CHECK definitions with type casts like `'active'::text` and may reorder ARRAY elements depending on PG version, so byte-string compare would trigger DROP+ADD on every web startup — wasteful and risky on large tables since `ALTER TABLE` takes an `ACCESS EXCLUSIVE` lock):

```python
import re

_STATUS_CHECK_NAME = "telos_entries_status_check"

def _extract_constraint_status_set(constraint_def: str) -> set[str]:
    """Parse pg_get_constraintdef output and return the allowed status set.

    Robust against PG normalization variations:
      - "CHECK ((status = ANY (ARRAY['active'::text, 'completed'::text, ...])))"
      - "CHECK (status IN ('active', 'completed', ...))"
      - "CHECK ((status)::text = ANY ((ARRAY['active'::text, ...])::text[]))"
    All forms have the allowed values as single-quoted string literals; extract them.
    """
    return set(re.findall(r"'([^']+)'", constraint_def))

def _apply_status_check_constraint() -> None:
    """Ensure telos_entries.status CHECK constraint matches STATUS_VALUES.

    Idempotent + SEMANTICALLY definition-aware: replaces stale constraints
    whose allowed-status set doesn't match STATUS_VALUES. Compare by parsed
    SET (not by raw string) so PG normalization differences don't trigger
    spurious DROP+ADD cycles on every startup.
    """
    from radbot.tools.telos.models import STATUS_VALUES
    from radbot.db.connection import get_db_connection, get_db_cursor

    with get_db_connection() as conn:
        with get_db_cursor(conn, commit=True) as cursor:
            # Step 1 — preflight: abort if any row violates the new set.
            # Use parameterized != ALL(%s) instead of f-string IN to keep
            # quoting/injection safe if STATUS_VALUES ever contains exotic chars.
            cursor.execute(
                "SELECT COUNT(*), COALESCE(string_agg(DISTINCT status, ', '), '') "
                "FROM telos_entries WHERE status != ALL(%s);",
                (list(STATUS_VALUES),),
            )
            bad_count, bad_values = cursor.fetchone()
            if bad_count > 0:
                raise RuntimeError(
                    f"telos_entries has {bad_count} rows with statuses outside "
                    f"the new set: {bad_values}. Fix data before applying CHECK."
                )

            # Step 2 — inspect existing constraint definition.
            cursor.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = %s AND conrelid = 'telos_entries'::regclass;",
                (_STATUS_CHECK_NAME,),
            )
            row = cursor.fetchone()
            existing_def = row[0] if row else None

            # Step 3 — fast path: no constraint, just add.
            if existing_def is None:
                _add_status_check(cursor, STATUS_VALUES)
                logger.info("Added telos_entries CHECK constraint")
                return

            # Step 4 — SEMANTIC set comparison: parse the existing definition
            # for its allowed values and compare against STATUS_VALUES.
            existing_set = _extract_constraint_status_set(existing_def)
            if existing_set == set(STATUS_VALUES):
                return  # idempotent no-op — set matches regardless of PG normalization

            # Step 5 — set mismatch → DROP + re-ADD with INFO log.
            logger.info(
                "telos_entries CHECK constraint set mismatch; expected %s, got %s — replacing.",
                sorted(STATUS_VALUES), sorted(existing_set),
            )
            cursor.execute(
                f"ALTER TABLE telos_entries DROP CONSTRAINT {_STATUS_CHECK_NAME};"
            )
            _add_status_check(cursor, STATUS_VALUES)
            logger.info("Replaced telos_entries CHECK constraint with current STATUS_VALUES")

def _add_status_check(cursor, status_values: set[str]) -> None:
    """Helper: emit ALTER TABLE ADD CONSTRAINT with parameterized values.

    Uses Postgres ARRAY constructor with %s expansion so we never f-string
    user-controllable strings into raw SQL.
    """
    quoted_csv = ", ".join(f"'{s}'" for s in sorted(status_values))
    # Note: ALTER TABLE doesn't accept parameterized constraint definitions;
    # the quoted_csv interpolation is safe here because STATUS_VALUES is a
    # closed set defined in models.py — never user input.
    cursor.execute(
        f"ALTER TABLE telos_entries ADD CONSTRAINT "
        f"{_STATUS_CHECK_NAME} CHECK (status IN ({quoted_csv}));"
    )
```

The semantic comparison reduces re-deployment risk: even if a contributor uses an older PG version that normalizes the constraint differently, or rewrites the constraint via a manual `psql` session in a way that re-orders elements, the migration only fires when the actual allowed-set differs.

**Migration mechanism:** `_apply_status_check_constraint()` is called as a sibling step inside `init_telos_schema()` (not inside `init_table_schema`, which only runs on table creation). It runs on every web startup; cost is two metadata-table queries when the constraint already matches. Same shape as the GIN index migration in Item 0.c.

**Tests:**
- Unit test: drop the constraint manually, restart, assert it re-appears with the correct definition.
- Unit test: seed a stale constraint with only the legacy 4 statuses (simulating an upgrade from a stale on-disk schema), restart, assert the constraint is replaced and contains all 8 statuses.
- Unit test: insert a row with `status = 'bogus'` directly via raw SQL (bypassing `db.add_entry`'s validation), restart, assert the migration aborts with the preflight error.
- Unit test: assert `_expected_status_check_clause()` output stays in sync with `STATUS_VALUES` after a future widening (add a new state to `STATUS_VALUES` in a fixture, assert the generated SQL contains it).

**Rollback (operational note — load-bearing per council Round 2 disagreement resolution):**
- **DB rollback** (additive change is safe to drop): `ALTER TABLE telos_entries DROP CONSTRAINT IF EXISTS telos_entries_status_check;` followed by re-running the new migration after fixing any data.
- **Code rollback** (UNSAFE once any row holds a new status): if the production DB has any row with `status` ∈ `{proposed, in_review, approved, executing}` and the application code is rolled back to a build whose `STATUS_VALUES` only contains the legacy 4 states, `db.add_entry` and `db.update_entry` validation will reject new writes that touch those rows with a cryptic `ValueError`. **Rollback procedure if needed:** (i) run `UPDATE telos_entries SET status='active' WHERE status IN ('proposed','in_review','approved','executing');` to normalize statuses (loses lifecycle state but preserves rows), THEN (ii) drop the CHECK constraint, THEN (iii) deploy the older build. Document this in the release notes for the Item 0+1.a PR.

This whole change is additive forward — nothing to drop in v1. **Ship Item 1.a in the same PR as Item 0.b** so the new status param and the extended `STATUS_VALUES` land atomically; otherwise Item 0.b would briefly accept only the legacy four states, breaking `/review-ex` for any session that runs between the two PRs.

**1.b — Documented convention** — written into:
- `specs/agents.md` § Scout / lifecycle
- `config/default_configs/instructions/scout.md`
- `.claude/skills/ship/SKILL.md` (Phase 11 hook for `completed`, postmortem step)
- `CLAUDE.md` § Telos lifecycle (new sub-section)

**1.c — Pin every transition to an actor.**

| From → To | Actor | Trigger |
|---|---|---|
| (new) → `proposed` | Scout | `exploration_add` from her instruction file when persisting a plan post-tier-1-council |
| `proposed` → `in_review` | `/review-ex` skill | First step before `/mm-council:evaluate` fires |
| `in_review` → `approved` | Claude Code session (this loop) | After capturing the council synthesis, on user confirmation |
| `in_review` → `in_review` (stays) | n/a | If council verdict is `revise` or `reject` — the EX remains in review until the human edits and re-runs `/review-ex`. Does NOT roll back to `proposed`; rolling back would hide that review happened and that there are blockers to address. |
| `approved` → `executing` | `/ship` skill | Phase 1 (pre-flight) when the branch matches the EX-linkage convention (Risks #2) |
| `executing` → `completed` | `/ship` skill | Phase 11 immediately post-merge, before cleanup |
| `executing` → `approved` | Manual / `/ship --abort` | If the user kills `/ship` before merge — recovery path |
| `completed` → `archived` | Manual (user via `mcp__radbot__exploration_update`) | When the EX is no longer a useful reference (e.g. supplanted by a follow-up EX). `completed` is **terminal** otherwise — the postmortem step does NOT auto-archive and **does NOT mutate status** (see `/postmortem-ex` § Item 4 — `/ship` is the sole owner of `executing → completed`). |
| (any non-terminal) → `superseded` | Manual (user via `mcp__radbot__exploration_update`) | When a newer EX replaces this one before it ever shipped. Document the replacement EX ref in `metadata.superseded_by` (string ref code, e.g. `"EX42"`, must point to an existing EX in the same `explorations` section — convention only, no DB-level FK). The new EX MAY symmetrically set `metadata.supersedes: "EX<N>"` pointing back; not required. |

**Single ownership of `executing → completed` (resolves Round 2 council finding):** `/ship` Phase 11 is the **sole owner** of this transition. `/postmortem-ex` MUST NOT mutate status — it only writes EX content (the `## Postmortem` block) and creates the journal entry. AC: `/postmortem-ex` calls to `mcp__radbot__exploration_update` shall NOT include the `status` field.

**Concurrency invariant (resolved):** Single user, single active session per EX. **Item 3's Scout postmortem-processing trigger is changed to user-driven** (see Item 3) so it cannot fire in the background while the user is running `/review-ex` on the same EX in another session. Combined with the dedup-by-`source_postmortem` guard in Item 3 rule 2, this preserves the single-user invariant honestly without needing optimistic concurrency control on `update_entry`. **Stuck-state recovery:** if an EX sits in `in_review` or `executing` for >24h, the user can manually flip it back via `mcp__radbot__exploration_update` (with the new `status` param from Item 0.b.i and `content` left absent). **Telemetry follow-up:** track as a sibling project task PT (`telemetry_concurrent_telos_update_writes_alert`) — file under PRJ1 alongside Item 1.b's docs pass. ACs and the OCC decision get re-evaluated only if that telemetry ever fires.

**Acceptance criteria (EARS):**
- The `STATUS_VALUES` set in **`radbot/tools/telos/models.py`** (the source-of-truth location) shall include `{proposed, in_review, approved, executing, completed, active, archived, superseded}`. All four enforcement sites listed in 1.a shall use this same imported set (verified by `grep -rn "STATUS_VALUES" radbot/`).
- The `telos_entries.status` CHECK constraint shall match `STATUS_VALUES` after migration.
- The migration shall be idempotent: re-running `init_telos_schema()` on a database that already has the constraint shall be a no-op (no error).
- The migration shall preflight-check existing rows: if any row carries a status outside the new set, the migration shall raise an exception with the offending values (rather than silently failing the constraint add).
- A unit test shall assert `db.add_entry(section, content, status="proposed")` (and the same for `in_review`, `approved`, `executing`) succeeds with each new lifecycle state.
- When Scout persists a new exploration via `mcp__radbot__exploration_add({..., status: "proposed"})`, the resulting entry shall have `status = "proposed"`. Scout's instruction file (Item 3 compensating edit) shall pass `status="proposed"` explicitly on creation.
- When `/review-ex <N>` runs, it shall update the exploration's status to `in_review` before invoking mm-council.
- When `/ship` merges a PR linked to `EX<N>`, it shall update the exploration's status to `completed` post-merge before cleanup.
- The system shall NOT add concurrency control (CAS or locks) for v1; the single-user invariant is preserved by Item 3's user-driven trigger + dedup-by-`source_postmortem` guard. The invariant is documented in `CLAUDE.md` and Scout's instruction file.

### Item 2 — `/review-ex <N>` orchestration skill

A new Claude Code command in the personal marketplace (recommended location: `~/git/perrymanuk/claude-skills/plugins/radbot/commands/review-ex.md` since it's radbot-specific). Steps using the **real** MCP surface (post-Item-0):

```
1.  mcp__radbot__telos_get_entry({section: "explorations", ref_code: "EX<N>", format: "json"})
    — uses the new `format="json"` parameter from Item 0.c. Returns
      TextContent whose .text is JSON: {"entry": {ref_code, entry_id,
      section, status, content, metadata, created_at, updated_at}}.
      Parse via json.loads(response.text)["entry"]. The `content` field
      is the raw body, no markdown framing. The default
      `format="markdown"` is NOT used because round-tripping the rendered
      `### explorations: EX<N>` / `**Status:**` / `**Metadata:**` wrapping
      back through `exploration_update(content=...)` would compound the
      framing every re-run.
2.  Strip any prior cross-family block from the raw content using the
    regex below (idempotency — see marker convention). **Marker validation
    runs both BEFORE and AFTER the strip** — closes the Round 2 council
    finding that "no change after sub" alone misses cases like one valid
    block PLUS an extra unmatched marker.

    Strip:
        cleaned = re.sub(
            r"\n*<!-- cross-family -->.*?<!-- /cross-family -->\n*",
            "\n",
            content,
            flags=re.DOTALL,
        )

    Then validate: count remaining occurrences of BOTH markers in `cleaned`:
        n_open  = cleaned.count("<!-- cross-family -->")
        n_close = cleaned.count("<!-- /cross-family -->")
    If either > 0, ABORT with a clear error: "Malformed cross-family
    marker pair in EX<N> (n_open=<X>, n_close=<Y>); manually clean the
    EX body before re-running /review-ex." Do NOT mutate status or
    content. Write `cleaned` to /tmp/EX_<N>.md for inlining.

3.  mcp__radbot__exploration_update({ref_code: "EX<N>", status: "in_review"})
    — uses the new status param from Item 0.b.i. `content` is omitted
      (Item 0.b.i makes it optional — the body is left unchanged). Pure
      status flip, minimal blast radius.
4.  /mm-council:evaluate /tmp/EX_<N>.md
    — fires 3-round debate + synthesis. Returns markdown to stdout AND a
      machine-readable verdict line (see contract below).
5.  Parse the COUNCIL_VERDICT line, then read the file at
    synthesis_markdown_path. If the file is missing, unreadable, has a
    relative path, or is not a regular file, log a warning, leave status
    at `in_review`, do NOT mutate content, and prompt the user manually.
6.  mcp__radbot__exploration_update({
        ref_code: "EX<N>",
        content: <stripped raw from step 2> +
                 "\n\n<!-- cross-family -->\n" +
                 "## Council Review (Cross-Family) — <iso8601>\n" +
                 <synthesis> +
                 "\n<!-- /cross-family -->\n"
    })
    — the cross-family block is **always normalized to the end of the
      body** (not preserved at its prior position). The HTML-comment
      delimiters are the idempotency markers consumed by step 2 on re-run.
7.  Branch on verdict:
    - verdict in {proceed, proceed_with_changes}: ask the user whether to
      flip status to `approved` (single confirmation prompt; on yes →
      `mcp__radbot__exploration_update({ref_code, status: "approved"})`,
      content omitted).
    - verdict in {revise, reject}: do NOT auto-flip; print the synthesis
      blockers section verbatim, leave status at `in_review` so the user
      knows the EX needs work.
```

**mm-council output contract** — `/mm-council:evaluate` must emit, as its **last** stdout line, a machine-readable JSON record so `/review-ex` can branch deterministically:

```
COUNCIL_VERDICT: {"verdict": "proceed"|"proceed_with_changes"|"revise"|"reject", "confidence": "high"|"medium"|"low", "panelist_count": <int>, "synthesis_markdown_path": "<absolute path>"}
```

**`synthesis_markdown_path` file contract (load-bearing — closes Round 2 council finding on lifecycle/uniqueness):**

- **Location:** `${XDG_RUNTIME_DIR:-/tmp}/mm-council/<EX_or_uuid>-<iso8601-utc-Z>.md`. The directory is created with mode `0700` if missing.
- **Filename uniqueness:** the `<EX_or_uuid>` segment is the EX ref (e.g. `EX42`) when `/review-ex` invoked `/mm-council:evaluate`, OR a fresh UUID4 when run on an arbitrary file path. The `<iso8601-utc-Z>` segment uses the same `_iso_default` format as Item 0.c (literal `Z` suffix). Two parallel `/review-ex` runs against different EXes by the same user — explicitly allowed by the concurrency invariant — never collide.
- **Ownership:** `/mm-council:evaluate` creates and owns the file. The caller (`/review-ex`) is responsible for deleting it after a successful read at step 6. On caller failure (e.g. step 6's `exploration_update` errors), the file remains for debugging — `/mm-council:evaluate` does NOT clean up. A separate `mm-council` housekeeping pass MAY garbage-collect files older than 7 days; not required for v1.
- **Path absoluteness:** the `synthesis_markdown_path` value in `COUNCIL_VERDICT` is always absolute. If `/review-ex` parses the line and finds the path missing, unreadable, relative, or not a regular file, behavior follows the AC below (leave status at `in_review`, no mutation, prompt user).

If the COUNCIL_VERDICT line is absent or unparseable, `/review-ex` shall log a warning, leave status at `in_review`, and prompt the user manually. The `synthesis_markdown_path` is what step 5 reads to populate step 6's content. **Specs to update:** `~/git/perrymanuk/claude-skills/plugins/mm-council/skills/evaluate/SKILL.md` § Step 5 (emit the contract line at end of synthesis AND honor the file-location convention above).

**Acceptance criteria (Given/When/Then):**
- **Given** an `EX<N>` with `status="proposed"`, **when** `/review-ex N` runs, **then** the EX content shall gain exactly one `## Council Review (Cross-Family)` section delimited by `<!-- cross-family -->` ... `<!-- /cross-family -->` HTML comments, placed at the end of the body, leaving all other sections byte-identical.
- **Given** an `EX<N>` already containing a `<!-- cross-family --> ... <!-- /cross-family -->` block, **when** `/review-ex N` re-runs, **then** the prior block shall be removed and the new block shall be appended at the end of the body (always normalized to end — not preserved at its prior position) — the EX content shall NOT accumulate duplicate cross-family sections across re-runs.
- **Given** an `EX<N>` whose content contains `<!-- cross-family -->` but no matching `<!-- /cross-family -->` (malformed marker pair), **when** `/review-ex N` runs step 2, **then** the skill shall abort with a clear error message and shall NOT mutate the EX status or content. Test: seed a malformed EX, invoke `/review-ex`, assert exit code != 0 and assert the EX entry is byte-identical pre/post.
- **Given** `/mm-council:evaluate` returns `verdict ∈ {revise, reject}`, **when** `/review-ex` parses the contract line, **then** the skill shall NOT prompt for an `approved` flip and the EX status shall remain `in_review`.
- **Given** `/mm-council:evaluate` returns no parseable `COUNCIL_VERDICT:` line, **when** `/review-ex` reaches step 7, **then** the skill shall log a warning, leave status at `in_review`, and ask the user how to proceed manually.
- **Given** `/mm-council:evaluate` emits a parseable `COUNCIL_VERDICT:` line but the `synthesis_markdown_path` it references is missing, unreadable, relative (not absolute), or not a regular file, **when** `/review-ex` reaches step 5, **then** the skill shall log a warning citing the path error, leave status at `in_review`, NOT mutate content (skip step 6), and prompt the user how to proceed.
- **Given** the radbot MCP server returns a transport-level error (connection refused, request timeout, or `tool not found`) on the step-1 `telos_get_entry` call, **when** `/review-ex` is invoked, **then** it shall exit with a non-zero code and a `MCP unreachable: <reason>` message **before** invoking `/mm-council:evaluate` and **before** mutating any EX status. Test: point the MCP client at an unreachable URL, invoke, assert exit code != 0 and message format matches.
- **Given** `/review-ex` succeeded at step 3 (status flipped to `in_review`) but a later step (4-7) fails, **when** the failure surfaces, **then** the skill shall NOT roll back the status to `proposed` (the review-attempt provenance must be visible) and shall print exact recovery instructions: "EX<N> is in `in_review` after a partial failure at step <K>. Re-run `/review-ex <N>` to retry."

### Item 3 — Scout instruction update (user-driven postmortem processing)

Edit `config/default_configs/instructions/scout.md` to add a "Postmortem processing" section. Uses the real (post-Item-0) MCP tool names.

**Trigger model (resolved blocker):** Scout's postmortem processing is **user-driven**, NOT automatic on every session start. Risk #3's single-user concurrency invariant rests on "single active session per EX" — having Scout silently mutate EX/PT/journal entries on every new session would create a second writer that races user-initiated `/review-ex` and `/postmortem-ex` runs. The original draft's "on every new session" trigger is replaced below.

1. **When the user asks Scout to process pending postmortems** (typical phrases: "Scout, process postmortems", "any pending postmortems?", "what postmortems do I have?"), run the **structured-format** query:

   ```
   mcp__radbot__telos_get_section({
     section: "journal",
     metadata_filter: {"type": "postmortem", "processed_at": null},
     format: "json"
   })
   ```

   Parse via `json.loads(response.text)["entries"]`. The `metadata_filter` and `format=json` parameters are added in **Item 0.c**; the JSON payload shape is pinned there. If the result is an empty list, reply "No pending postmortems." and stop. **Scout shall NOT poll this query autonomously on session start** — the user must ask explicitly.

2. **Processing means**: for each pending postmortem, parse its `## Followups` section to derive a deterministic followup list (see "Followup-key derivation" below), then for each followup, **first query for existing followups** keyed on the deterministic `(source_postmortem, postmortem_followup_role, postmortem_followup_key)` triple to avoid duplicates from a prior partial run:

   ```
   mcp__radbot__telos_get_section({
     section: "project_tasks",   # or "explorations" or "journal"
     metadata_filter: {
       "source_postmortem":         "<JR<N>>",
       "postmortem_followup_role":  "<role>",
       "postmortem_followup_key":   "<derived key>",
     },
     format: "json",
     include_inactive: true,     # so already-completed dedup hits still match
   })
   ```

   If the result is non-empty, **skip the create** and capture the existing ref_code for the union list in step 3. Otherwise, create the followup with all dedup metadata attached **atomically in the `*_add` call** — Item 0.b.ii makes `metadata_merge` available on `task_add` AND `exploration_add` so `source_postmortem` lands in the SAME DB write as the row insert. **No add-then-update sequence; no race window.** Parse the new ref_code from the structured response (Item 0.b.iv).

   - Actionable items → single call:
     ```
     mcp__radbot__task_add({
       parent_project:  "<from journal>",
       description:     "<one-line>",
       title:           "<short>",
       task_status:     "backlog",
       metadata_merge: {
         source_postmortem:        "<JR<N>>",
         postmortem_followup_role: "task",
         postmortem_followup_key:  "<derived key — see below>",
       }
     })
     → pt_ref = json.loads(response.text)["ref_code"]
     ```
   - Bigger work needing its own plan → single call:
     ```
     mcp__radbot__exploration_add({
       parent_project:  ...,
       topic:           "<short>",
       notes:           "<full>",
       status:          "proposed",
       metadata_merge: {
         source_postmortem:        "<JR<N>>",
         postmortem_followup_role: "exploration",
         postmortem_followup_key:  "<derived key>",
       }
     })
     → ex_ref = json.loads(response.text)["ref_code"]
     ```
   - Insight worth remembering → single call:
     ```
     mcp__radbot__journal_add({
       entry: "<insight>",
       metadata: {
         type:                     "postmortem_insight",
         source_postmortem:        "<JR<N>>",
         postmortem_followup_role: "journal_insight",
         postmortem_followup_key:  "<derived key>",
       }
     })
     → jr_ref = json.loads(response.text)["ref_code"]
     ```

   **Followup-key derivation (load-bearing — closes Round 2 council blocker on dedup determinism).** The dedup key MUST be regenerable from the postmortem markdown alone — not from any LLM-generated state — so retries produce byte-identical keys. The contract:

   - The postmortem markdown (created by `/postmortem-ex` per Item 4 step 3) contains a `## Followups` section structured as three sub-sections:
     ```markdown
     ## Followups

     ### Tasks
     1. <one-line description for PT followup>
     2. <one-line description for PT followup>

     ### Explorations
     1. <topic for EX followup>

     ### Insights
     1. <one-line insight to journal>
     ```
   - For each followup, Scout assigns:
     - `postmortem_followup_role`: enum `task | exploration | journal_insight` — derived from the sub-section heading (`### Tasks` → `task`; `### Explorations` → `exploration`; `### Insights` → `journal_insight`).
     - `postmortem_followup_key`: stable hash. Computed as:
       ```python
       import hashlib
       material = f"{source_postmortem_jr_ref}|{role}|{ordinal}"
       postmortem_followup_key = hashlib.sha256(material.encode()).hexdigest()[:16]
       ```
       where `ordinal` is the 1-based position in the numbered list (1, 2, 3, ...) within the role's sub-section. **Crucially: ordinal comes from the markdown structure, NOT from LLM whim** — re-parsing the same postmortem markdown twice produces identical (role, ordinal) tuples and therefore identical keys.
   - **`/postmortem-ex` shall write the `## Followups` section as part of the postmortem markdown** (Item 4 step 3) — this is the input contract that Scout's processing relies on. The markdown is the source of truth; Scout MUST NOT add follow-ups not enumerated in the markdown (and MUST NOT skip ones that are).

3. **Mark the postmortem processed** (only after ALL followups for this postmortem succeeded — newly created OR found by dedup):
   ```
   mcp__radbot__journal_update({
     ref_code: "<JR<N>>",
     metadata_merge: {
       processed_at:   "<iso8601 with Z suffix>",
       processed_by:   "scout",
       followup_refs:  <UNION of dedup-hit refs from step 2 PLUS newly-created refs>,
     }
   })
   ```
   **`followup_refs` is the UNION** (Round 2 council finding) — any followups created in a prior partial run that step 2's dedup query found AND any newly-created followups in this pass. This preserves the audit trail across retries. If any followup create failed mid-way, do NOT mark processed — re-running step 2 will dedup against the partial state and complete the rest.

Also bump the persona block in `config/default_configs/instructions/main_agent.md` (beto's instruction file) with one paragraph of identity/voice that previously came from the Telos anchor — see Item 6.

**Postmortem journal-entry invariant — enforced at shared `db.add_entry` layer (closes Round 2 + Round 3 findings on agent-side bypass and `metadata=None` AttributeError).** Postgres JSONB `@>` matches `{"processed_at": null}` only when the key is **explicitly present and serialized as null** — a missing key does NOT match. Item 4 step 5 always sets `processed_at: null` explicitly, but the invariant must be enforced at the lowest shared write layer so it covers EVERY writer (MCP `journal_add`, agent-side `telos_add_journal`, direct `db.add_entry` calls).

**Implementation pinned (load-bearing — Round 3 3-of-3 blocker):** at the top of `radbot/tools/telos/db.py:add_entry`:

```python
def add_entry(section, content, *, ref_code=None, metadata=None, status="active", sort_order=0):
    # Defensive normalize FIRST — db.add_entry signature accepts metadata=None for normal entries.
    # Without this, every non-postmortem journal write would raise AttributeError on metadata.get().
    metadata = dict(metadata or {})

    # Postmortem invariant — covers BOTH spelling conventions:
    #   - new MCP journal_add writes metadata.type='postmortem'
    #   - legacy agent-side telos_add_journal writes metadata.event_type='postmortem' (event_type kwarg)
    # Either spelling triggers the invariant; both must include processed_at (initially null).
    if section == Section.JOURNAL and (
        metadata.get("type") == "postmortem"
        or metadata.get("event_type") == "postmortem"
    ):
        if "processed_at" not in metadata:
            raise ValueError(
                "postmortem journal entries must include metadata.processed_at "
                "(initially null) — this enables the unprocessed-postmortem query"
            )

    # ... existing STATUS_VALUES validation and INSERT logic ...
```

**Plus: normalize `event_type` → `type` at the agent-side layer** (defense in depth). Update `telos_add_journal` (`telos_tools.py:207-233`): when `event_type == "postmortem"`, set `metadata["type"] = "postmortem"` AND default `metadata["processed_at"] = None` if not supplied, before delegating to `db.add_entry`. This way the canonical key (`type`) is always populated AND the invariant fires on the legacy spelling regardless. Single enforcement point at `db.add_entry`; agent-side normalization is the cleanup pass.

**Tests (mandatory):**
- `db.add_entry(Section.JOURNAL, "x", metadata={"type": "postmortem"})` → `ValueError`.
- `db.add_entry(Section.JOURNAL, "x", metadata={"event_type": "postmortem"})` → `ValueError` (covers agent-side bypass).
- `db.add_entry(Section.JOURNAL, "x", metadata={"type": "postmortem", "processed_at": None})` → succeeds.
- `db.add_entry(Section.JOURNAL, "x")` (no metadata kwarg) → succeeds (defensive normalize works).
- `db.add_entry(Section.JOURNAL, "x", metadata=None)` → succeeds (explicit None).
- `telos_add_journal(entry="x", event_type="postmortem")` → succeeds AND the resulting row has both `metadata.type == "postmortem"` AND `metadata.processed_at is None`.

**Acceptance criteria:**
- The instruction file shall include the three rules above (verbatim) using the post-Item-0 MCP tool names.
- The instruction file shall include exact tool-call examples for each step (Scout's instruction style is example-heavy).
- The instruction file shall state that Scout must NOT autonomously poll for pending postmortems on session start — the trigger is user-driven only.
- The instruction file shall require dedup-by-`(source_postmortem, postmortem_followup_role, postmortem_followup_key)` query before each followup create, including `include_inactive: true` so completed followups still count as duplicates.
- The instruction file shall pin the SHA-256-truncated-to-16-hex `postmortem_followup_key` derivation rule (verbatim Python snippet above) and assert that two re-parses of the same postmortem markdown produce byte-identical keys.
- Scout shall NOT use the `task_add → task_update` two-call pattern for `source_postmortem` linkage — the dedup metadata MUST be set atomically in the initial `*_add` call via `metadata_merge`. Test: simulate a process kill immediately after `task_add` and assert the followup is found by the dedup query on retry.
- The `db.add_entry` shared layer shall reject `Section.JOURNAL` writes with `metadata.type=="postmortem"` and missing `processed_at`. Test: call `db.add_entry(Section.JOURNAL, "<text>", metadata={"type": "postmortem"})` directly — assert `ValueError`; with `{"type": "postmortem", "processed_at": None}` — assert success.
- Test: simulate a partial failure (Scout creates 2 of 3 followups via `*_add` with `metadata_merge`, then crashes); re-run step 2; assert exactly 1 new followup is created (the missing ordinal) and 0 duplicates of the prior 2 (dedup query found them by stable key).
- Test: `journal_update` step shall record `followup_refs` as the union (e.g. simulate first run creates PT1+PT2, retry creates PT3, assert `followup_refs=[PT1,PT2,PT3]` after the retry's `journal_update`).

### Item 4 — Postmortem-back via journal (sibling `/postmortem-ex` skill)

A separate Claude Code skill the user invokes after `/ship` returns successfully. Not folded into `/ship` itself — `/ship` is mostly mechanical (Phase 11 = merge, Phase 12 = cleanup; postmortem-writing requires Claude Code to think about what happened, which doesn't fit that flow). The user runs `/postmortem-ex <PR#>` once `/ship` returns.

Behavior using **post-Item-0** MCP names. **Step ordering revised (blocker fix from Round 2):** EX validation now runs BEFORE `journal_add` so a malformed-marker abort never leaves an orphan `JR<N>`. The dedup check ALSO runs before `journal_add` for the same reason. Sequence: resolve_ex → fetch+validate → dedup → generate_md → journal_add → write_ex.

```
1. Resolve EX from PR. Resolution order (chosen for safety — do NOT assume
   PT-to-EX metadata links exist; defer that lookup until verified):
   (i)   Parse the branch name with the case-insensitive path-aware regex
         `(?i)(?:^|/)ex(\d+)\b` (matches `ex42-foo`, `EX42-foo`,
         `perry/ex42-foo`, etc — per Round 2 council finding on worktree
         prefixes).
   (ii)  Grep the PR title for `(?i)EX(\d+)\b`.
   (iii) Grep the PR body for `(?i)EX(\d+)\b`.

   Conflict handling: if multiple sources resolve to DIFFERENT EX numbers,
   ABORT with the conflict listed (do NOT silently first-wins). Example:
   "Branch resolved EX42, PR body resolved EX17 — re-run as
   /postmortem-ex <PR#> --ex-ref EX<N> to disambiguate."

   If all of (i-iii) miss, ABORT with an actionable message — do NOT
   prompt interactively (Claude Code skills running as shell subprocesses
   can hang or break terminal state if they read stdin without framework
   support; Round 2 Gemini finding):
       "Could not resolve EX link for PR #<N>. Re-run as:
        /postmortem-ex <PR#> --ex-ref EX<M>"
   The skill MUST accept an `--ex-ref` flag for this fallback.

   Note: if the branch matches `(?i)(?:^|/)pt(\d+)\b`, the resolver does
   NOT look up the parent EX from PT metadata in v1 (no evidence today
   that PT entries carry a parent-EX link). pt<N> branches fall through
   to (ii) and (iii). A future EX may add the PT→EX lookup if a verified
   link is established.

2. Fetch the current EX body AND validate postmortem markers (BEFORE
   creating the journal entry — closes the Round 2 step-ordering blocker):

       resp = mcp__radbot__telos_get_entry({section: "explorations",
                                            ref_code: "EX<N>",
                                            format: "json"})
       entry = json.loads(resp.text)["entry"]
       raw_body = entry["content"]

       cleaned = re.sub(
           r"\n*<!-- postmortem -->.*?<!-- /postmortem -->\n*",
           "\n",
           raw_body,
           flags=re.DOTALL,
       )
       n_open  = cleaned.count("<!-- postmortem -->")
       n_close = cleaned.count("<!-- /postmortem -->")
       if n_open or n_close:
           abort(f"Malformed postmortem markers in EX<N> "
                 f"(n_open={n_open}, n_close={n_close}); manually clean "
                 f"the EX body before re-running /postmortem-ex.")

   The cross-family block from Item 2 (delimited by `<!-- cross-family -->`
   ... `<!-- /cross-family -->`) is left **verbatim** in `cleaned` —
   /postmortem-ex preserves /review-ex's review provenance.

3. Dedup check — query for an existing postmortem journal entry with the
   same pr_url. **PR-URL canonicalization (load-bearing):** the URL string
   written at step 5 must equal the URL string queried here BYTE-IDENTICALLY
   for JSONB `@>` to hit. Canonicalize before both query AND write:

       owner, repo, pr_num = parse_pr_arg(pr_arg)  # accepts "42" or full URL
       pr_url = f"https://github.com/{owner.lower()}/{repo.lower()}/pull/{pr_num}"
       # No trailing slash. No query string. Lowercase owner/repo. Integer PR num.

   Then dedup query:

       mcp__radbot__telos_get_section({
         section: "journal",
         metadata_filter: {"type": "postmortem", "pr_url": pr_url},
         format: "json",
         include_inactive: true,   # so archived JRs from prior --supersede runs still surface
       })

   If the result is non-empty, ABORT with an actionable message (do NOT
   prompt interactively, same shell-subprocess constraint as step 1):
       "PR #<N> already has postmortem journal entry JR<M>
        (created <iso8601>). To create a new one anyway, re-run as:
        /postmortem-ex <PR#> --force-new
        Or to supersede the old entry, re-run as:
        /postmortem-ex <PR#> --supersede"
   The skill MUST accept `--force-new` and `--supersede` flags. **Behavior
   and ordering for these flags is load-bearing — closes the Round 3 blocker
   on archive-before-create leaving zero valid postmortems on partial failure
   AND the Round 3 major on `--force-new` leaving the old JR independently
   processable.**

   **`--supersede` ordering (delayed archive):** dedup-detection RECORDS
   the old JR ref but does NOT mutate it yet. Steps 4-7 proceed normally
   (generate markdown, journal_add, write EX body). ONLY AFTER step 7
   succeeds does the skill execute `_supersede_old_jr(old_ref, new_ref)`:

       mcp__radbot__journal_update({
         ref_code: <old JR ref>,
         metadata_merge: {
           processed_at:  "<iso8601>",
           processed_by:  "superseded_by_<new JR ref>",
           superseded_by: "<new JR ref>",
         },
         status: "archived",
       })

   This means if anything between dedup-detection and step-7-success
   fails, the old postmortem stays visible and intact. The
   `processed_at` write is critical: without it, future Scout queries
   that include archived rows (e.g. an audit query) would still surface
   the old JR as "unprocessed". With it, the old JR is unambiguously
   replaced.

   **`--force-new` ordering (mark-old-processed before create):**
   intentional-duplicate-creation must NOT leave both JRs independently
   processable. Before steps 4-7, mark the existing OLD JR as processed:

       mcp__radbot__journal_update({
         ref_code: <old JR ref>,
         metadata_merge: {
           processed_at: "<iso8601>",
           processed_by: "replaced_by_force_new_<placeholder>",
         },
       })

   Then proceed with steps 4-7 to create the NEW JR (which has its own
   `processed_at: null` invariant). After step 7 succeeds, patch the old
   JR's `processed_by` to reference the new ref:

       mcp__radbot__journal_update({
         ref_code: <old JR ref>,
         metadata_merge: {processed_by: "replaced_by_<new JR ref>"},
       })

   If steps 4-7 fail mid-way, the old JR is left marked-processed with
   the placeholder `processed_by` value — a follow-up `--supersede`
   invocation OR manual repair can fix that. The key invariant is that
   Scout's pending-postmortem query never sees TWO unprocessed JRs for
   the same PR.

4. Generate postmortem markdown from: PR diff, merged commits,
   plan-vs-actual delta, notable events from /ship's CI fix loop log.
   The markdown MUST include a `## Followups` section with three
   sub-sections (### Tasks / ### Explorations / ### Insights), each a
   numbered list — this is the input contract Scout's processing
   relies on (Item 3 followup-key derivation). If no followups apply
   for a sub-section, write `_None_` instead of an empty list so the
   structure is preserved for future re-parses.

5. Create the journal entry (after EX validation + dedup both passed):

       mcp__radbot__journal_add({
         entry: <postmortem markdown from step 4>,
         metadata: {
           type:          "postmortem",
           ex_ref:        "EX<N>",
           pt_refs:       ["PT<X>", "PT<Y>"],
           pr_url:        "<github URL>",
           processed_at:  null,                 # invariant — Item 3
           processed_by:  null,
           followup_refs: []
         }
       })
       jr_ref = json.loads(response.text)["ref_code"]

6. Append the new postmortem block to `cleaned` from step 2 (always
   normalized to end of body — matching Item 2's pattern):

       new_body = (
           cleaned +
           "\n\n<!-- postmortem -->\n" +
           "## Postmortem\n" +
           "- Journal: " + jr_ref + " (fetch via telos_get_entry).\n" +
           "<!-- /postmortem -->\n"
       )

7. Update the EX body — content ONLY; do NOT mutate status (Item 1.c
   single-ownership rule: /ship Phase 11 owns executing→completed,
   /postmortem-ex preserves whatever status /ship set):

       mcp__radbot__exploration_update({
         ref_code: "EX<N>",
         content:  new_body
         # status: OMITTED — /ship Phase 11 already set it to "completed"
       })

8. Print final UX nudge to user (closes Round 2 council finding on
   discoverability):

       "Postmortem JR<N> created and linked to EX<M>.
        Run 'Scout, process postmortems' when ready to generate followups."
```

**Acceptance criteria (Given/When/Then):**
- **Given** `/ship` merges PR #N linked to `EX<M>` via the branch/title convention, **when** `/postmortem-ex N` is invoked, **then** a new journal entry shall be created with `metadata.type="postmortem"`, `metadata.processed_at=null`, `metadata.ex_ref="EX<M>"`, and `metadata.pr_url=<the PR's GitHub URL>`.
- **Given** the user runs `/postmortem-ex N` for a PR with no resolvable EX link (no branch match AND no PR title/body match), **when** all three resolver steps miss, **then** the skill shall ABORT with the actionable message `"Could not resolve EX link for PR #<N>. Re-run as: /postmortem-ex <PR#> --ex-ref EX<M>"` and shall NOT prompt interactively. The skill shall accept the `--ex-ref` flag to bypass resolution.
- **Given** a PR whose branch and PR body resolve to DIFFERENT EX numbers, **when** `/postmortem-ex` runs step 1, **then** the skill shall ABORT with the conflict listed and request `--ex-ref` disambiguation. Test: seed a branch `ex42-foo` with PR body containing `EX17`; assert abort + zero side effects.
- **Given** a postmortem journal entry already exists for the same `pr_url`, **when** `/postmortem-ex` is re-invoked, **then** the skill shall ABORT with the actionable message and shall NOT silently create a duplicate. The skill shall accept `--force-new` (proceed and create another JR) and `--supersede` (archive the old JR via `journal_update(status: "archived")` then create the new one). Test: invoke `/postmortem-ex N` twice in a row without flags; assert the second invocation aborts with the existing JR ref in the message.
- **Given** an `EX<M>` already containing a `<!-- postmortem --> ... <!-- /postmortem -->` block (from a prior successful run), **when** `/postmortem-ex N` runs, **then** the prior postmortem block shall be removed and the new one appended at the end — the EX content shall NOT accumulate duplicate `## Postmortem` sections across re-runs.
- **Given** an `EX<M>` containing a `<!-- cross-family -->` block from a prior `/review-ex` run, **when** `/postmortem-ex N` writes the new EX body, **then** the cross-family block shall be preserved verbatim (postmortem block sits at the very end, cross-family block sits between the original body and the postmortem block).
- **Given** an `EX<M>` whose content contains a malformed postmortem marker pair (open without close, close without open, or any odd count after strip), **when** `/postmortem-ex N` runs step 2, **then** the skill shall abort with a clear error AND shall NOT create the journal entry AND shall NOT mutate the EX. Test: seed each malformed permutation, invoke, assert abort + EX byte-identical pre/post + zero new JR<N> rows.
- **Given** the journal entry is created at step 5, **when** the skill reaches step 7, **then** the EX body shall be updated with the new `<!-- postmortem -->` block AND the EX `status` shall be PRESERVED unchanged (single-ownership rule from Item 1.c — `/ship` Phase 11 owns the `executing → completed` transition; `/postmortem-ex` does NOT pass `status` to `exploration_update`).
- **Given** all steps succeed, **when** the skill exits, **then** stdout shall include the UX-nudge line: `"Postmortem JR<N> created and linked to EX<M>. Run 'Scout, process postmortems' when ready to generate followups."`

### Item 5 — Postmortem-processed flag + followup linking conventions

Pure metadata convention. The shapes are defined in Items 3 + 4 above. The MCP enablement (originally listed here as "optional MCP enhancement") has been **promoted to Item 0.c** as a mandatory prerequisite — all three council panelists agreed that client-side post-filtering against rendered markdown is fragile and that structured JSON returns + `metadata_filter` are required for this design. The reclassification eliminates the markdown round-trip data-loss risk that was a major finding.

**Convention:** every followup created from a postmortem includes `metadata.source_postmortem` set to the postmortem journal entry's `JR<N>` ref code (preferred — human-readable in journal exports). The presence of this key is the dedup signal Item 3 uses to avoid duplicate followups on retry. To make the "open followup tasks from any postmortem" query JSONB-`@>`-friendly without inventing a `$exists` operator, **followups MAY also set `metadata.has_source_postmortem: true`** (a denormalized boolean sentinel) — but this is optional. The primary lookup path is by specific `source_postmortem` value, not by key existence.

**v1 design decision (resolves Item 5 disagreement):** drop the `$exists`-style "any postmortem" query from the v1 AC. The other two queries (specific `processed_at: null` filter and specific `source_postmortem: "<JR<N>>"` filter) cover Scout's actual workflow needs and are pure JSONB containment, fully GIN-indexable. Adding a generic key-existence operator (`metadata ? key`) is a separate enhancement filed as a follow-up PT if real demand surfaces.

Verification queries (using Item 0.c tooling):

- "Show me unprocessed postmortems" →
  ```
  mcp__radbot__telos_get_section({
    section: "journal",
    metadata_filter: {"type": "postmortem", "processed_at": null},
    format: "json"
  })
  ```
  Relies on the Item 3 invariant that postmortem journal entries always serialize `metadata.processed_at` (initially `null`) — see the `journal_add` rejection rule in Item 3.

- "What followups did Scout produce from postmortem `JR<N>`?" → three queries (`project_tasks`, `explorations`, `journal`) each with `metadata_filter: {"source_postmortem": "JR<N>"}, format: "json", include_inactive: true` (so completed followups still surface).

- "Open followup tasks from a SPECIFIC postmortem" → `project_tasks` section with `metadata_filter: {"source_postmortem": "JR<N>", "task_status": "backlog"}, format: "json"`.

(The original draft's third query — "open followup tasks from ANY postmortem" — is dropped from v1. If/when needed, file a sibling PT for adding `metadata_keys_present: list[str]` to `metadata_filter`, translating to Postgres `metadata ? key` against the GIN index.)

**Acceptance criteria:**
- The schema migration in Item 1.a is the only schema change required by this EX; **no other migrations** for Item 5.
- All followup entries created from a postmortem shall include `metadata.source_postmortem` set to the postmortem journal entry's ref code (e.g. `"JR42"`).
- The two retained verification queries shall succeed against a journal section of up to 5000 entries with sub-second latency, given the GIN index on `telos_entries.metadata` from Item 0.c.
- The dropped "any postmortem" key-existence query shall NOT be present in the AC; if the use case re-emerges, the resolution is to file a follow-up PT for `metadata_keys_present` filter — not to handwave a fallback.

### Item 6 — Restrict `inject_telos_context` to scout-as-root only (Flavor 1)

Two-line code change, but the verification surface is bigger than the original draft assumed:

1. **Remove `inject_telos_context`** from beto's `before_model_callback` list at `radbot/agent/assembly.py:317` (verified location).
2. **Confirm scout-as-root's callback registration in `radbot/agent/research_agent/factory.py:217-242`** — specifically, the `if as_root:` block where `inject_telos_context` is the last entry of `adk_agent.before_model_callback`. The `as_root=True` flag itself is wired by `radbot/agent/assembly.py` (`AGENT_DEFS` + `_resolve_assembly` + the `chat_sessions.agent_name` selector) — verify both ends; do not assume.
3. **Confirm sub-agents stay excluded** — `_attach_subagent_callbacks` at `assembly.py:280-294` uses `_SUBAGENT_BEFORE_CBS` (lines 273-277) which does NOT include `inject_telos_context`. No change needed here, but the test in AC #4 below pins it.

Beto loses:
- Per-turn anchor (~300B): identity / mission / counts / tool pointer
- First-turn full block (~2KB): mission + problems + goals + projects + challenges + wisdom + last 5 journal entries

Beto retains:
- Full Telos tool surface — he can `telos_get_section`, `telos_get_entry`, etc., on demand via the 27 `TELOS_TOOLS` already wired into `_build_beto`'s tool list (`assembly.py:304`)
- His instruction file (`main_agent.md`) which has routing rules + a new persona/voice paragraph (Item 3 compensating edit)

**Specs to update:** `specs/agents.md` § "Telos persona injection (beto only)" — flip to "scout-as-root only" and update the rationale to cite `factory.py:217-242` as the registration site and `assembly.py` as the gating site. **Also reconcile the existing internal inconsistency:** `specs/agents.md` line 139 already documents scout-as-root receiving `inject_telos_context`, but line 303 (Callback Inventory table) labels it `beto only`. This conflict pre-dates Item 6 and must be resolved in the same edit.

**Acceptance criteria (Given/When/Then) — falsifiable replacements for the original AC #3:**

- **Producer-side marker pinning (NEW — closes Round 2 council finding that consumer absence-test is meaningless without producer guarantee).** The function `radbot/tools/telos/callback.py:build_telos_tiers()` shall emit, as load-bearing markers, all three literal strings: `"## Mission"`, `"## Identity"`, and `"ME:"`. **Test:** unit test on `build_telos_tiers()` that asserts each of the three substrings appears in the function's output (anchor or full block). This anchors the consumer-side absence test below — if a future rename moves `## Mission` to `## My Mission` in `callback.py`, this producer test fails first, alerting the implementer that Item 6's beto absence test must be updated in the same PR.
- **Given** a beto session is started, **when** beto receives his first user message, **then** `llm_request.config.system_instruction` shall NOT contain any output from `build_telos_tiers()`. **Test:** invoke beto with one user message; capture the `llm_request.config.system_instruction` via a one-shot before-model callback; assert that **none** of the producer-pinned markers appear in the captured text. Specifically, assert: (a) the literal substring `"## Mission"` is absent, AND (b) the literal substring `"## Identity"` is absent, AND (c) the user's identity ref `"ME:"` is absent. The producer-side AC above guarantees these markers ARE emitted by `build_telos_tiers()`; the consumer-side AC here verifies they don't reach beto.
- **Given** a scout-as-root session is started, **when** scout receives her first user message, **then** `llm_request.config.system_instruction` shall contain both the anchor and the full block as today. **Test:** assert `"## Mission"` is present (full-block marker) AND `"ME:"` is present (anchor marker).
- **Given** any sub-agent (`casa`, `planner`, `comms`, `axel`, `kidsvid`, `scout`-as-sub) receives its first turn, **when** the `before_model_callback` list runs, **then** `inject_telos_context` shall NOT be present in that list. **Test:** after `build_default_assembly()`, introspect each sub-agent's `before_model_callback` list (`agent.before_model_callback`) and assert `inject_telos_context` (the function reference imported from `radbot.tools.telos`) is not in the list.
- **AC #4 — Telos read regression test (rewritten to drop the format=json dependency, closing the Round 2 ordering contradiction).** **Given** beto's existing Telos read tools (`telos_get_section`, `telos_get_entry`, `telos_get_full`), **when** a regression test suite runs against a fixed set of representative conversations, **then** the parsed Telos read responses shall match a checked-in baseline structurally. **Test:** scripted set of 5 conversations covering routing, Telos read, Telos write, `transfer_to_agent`, and chitchat. **Pass criterion:** (a) transfer-targets match the baseline exactly; (b) Telos read responses, called with `format="markdown"` (the existing default — does NOT depend on Item 0.c's `format="json"`, allowing Item 6 to ship genuinely independently of Item 0.c) and parsed via a small AST-style helper that splits on the markdown delimiters (`### section: ref_code`, `**Status:**`, body, `**Metadata:**`), match structurally on `(ref_code, body_lines_sorted, metadata_dict)` against the baseline (timestamps and rendering order ignored); (c) the chitchat conversation produces a non-empty reply. **Baseline fixture (mandatory):** the baseline lives at `tests/fixtures/item6_regression_baseline.json`; regen via `make regen-item6-baseline` (added in this EX). PR checklist: any change to beto's instruction file requires regenerating the baseline IN THE SAME PR.
- **Specs-grep coherence AC.** **Given** the docs edits in Item 6 land, **when** `grep -n "inject_telos_context" specs/agents.md` runs, **then** every match shall agree on the same scope (scout-as-root only; not beto; not sub-agents). **Test:** automated grep + assert the resulting lines do NOT contain the substring `"beto only"` and DO contain at least one `"scout-as-root only"` mention.
- **AC #5 (smoke test for v1; literal-regex deferred).** **Given** beto loses the per-turn anchor, **when** the user asks "what are you?" in a fresh session, **then** beto shall reply (response is non-empty, contains the agent's name `"beto"` or a first-person identity claim `"I'm "`/`"I am "`, and does not error). **Risk acknowledgment (load-bearing — Round 2 council finding):** this smoke test is intentionally weak; it would pass even if Item 3's compensating persona-paragraph edit were forgotten entirely. The stronger literal-regex AC against the persona paragraph is deferred to a follow-up PT to ship together with Item 3's persona-paragraph draft, once the paragraph text is pinned. The post-deploy observation window (Risks #5) is the only catch for a forgotten or weak persona paragraph in v1. **Mitigation:** Item 6 ship is gated on Item 3's persona-paragraph edit landing in the SAME PR — a soft gate enforced by PR checklist (not by automated test). If a future contributor removes `inject_telos_context` from beto without adding the persona paragraph, the PR review must catch it.

## Risks / open questions (resolved decisions and remaining unknowns)

1. **Scope of postmortem-back: sibling skill, not folded into `/ship`.** Decided. `/postmortem-ex <PR#>` is a separate Claude Code skill the user invokes after `/ship` returns. `/ship` stays mostly mechanical (Phase 11 = merge, Phase 12 = cleanup) — postmortem-writing requires Claude Code to think, which doesn't fit. (Closes original Q1.)
2. **Linking PR → EX: best-effort branch convention; no /ship-side enforcement in v1 (downgraded after Round 2 council finding).** `/ship` already creates branches with the form `pt<N>-<slug>` or similar; the convention is extended so EX-implementing branches MAY use the prefix `ex<N>` (e.g. `ex42-council-loop`) AND/OR the PR title/body MAY contain the literal `EX<N>` token. `/postmortem-ex` resolves the EX with the case-insensitive path-aware regex from Item 4 step 1: (i) branch `(?i)(?:^|/)ex(\d+)\b`; (ii) PR title `(?i)EX(\d+)\b`; (iii) PR body `(?i)EX(\d+)\b`; (iv) if all miss, ABORT with an actionable message asking the user to re-run with `--ex-ref EX<N>` (do NOT prompt interactively — see Item 4 step 1 reasoning). **No /ship change in v1 to inject `EX<N>` into PR bodies** — this was a Round 2 council finding and is intentionally deferred: the manual fallback (`--ex-ref` flag) covers the case, /ship has its own complexity budget, and adding enforcement now would couple two skills unnecessarily. If telemetry shows the manual fallback firing >25% of the time, file a follow-up PT for /ship enforcement. **`pt<N>` branch handling:** branches matching `(?i)(?:^|/)pt(\d+)\b` do NOT trigger a PT-metadata lookup in v1 — there's no verified evidence today that PT entries carry a parent-EX link. `pt<N>` branches fall through to (ii)/(iii)/(iv). **Acceptance:** `/postmortem-ex` shall not create an orphan postmortem (one without `metadata.ex_ref`) — it aborts with the `--ex-ref` instruction before any side effects. (Closes original Q2 + Round 2 council finding on /ship enforcement gap.)
3. **Concurrency invariant: single-user, single active session per EX.** Decided — see Item 1 § Concurrency invariant + Item 3's user-driven trigger. No CAS or advisory lock added in v1; the invariant is honestly preserved (Item 3 no longer mutates state autonomously on session start; postmortem-processing dedup-by-`source_postmortem` provides defense-in-depth). Documented as a constraint in `CLAUDE.md` and Scout's instruction file. **Telemetry follow-up:** filed as a sibling project task — `telemetry_concurrent_telos_update_writes_alert` under PRJ1, to be created alongside Item 1.b's documentation pass. Re-evaluate the OCC decision only if that telemetry ever fires (>0 concurrent `update_entry` calls on the same `entry_id` within a 30-day window).
4. **Cycle risk if `chat_with_scout` ever lands.** Out of scope for this EX. Scout's `start_claude_session` could spawn a Claude Code subprocess that calls back to `chat_with_scout`, looping. Captured for future EX. (Same as original Q3.)
5. **Beto's reaction to the Telos context removal.** Item 6's AC suite covers behavioral regressions on routing + Telos read paths via scripted tests against a checked-in `tests/fixtures/item6_regression_baseline.json`. The persona/voice question is covered by **AC #5's structural smoke test** for v1 (response non-empty + contains `beto`/`I'm`/`I am`); the stronger **literal-regex AC against `main_agent.md`'s persona paragraph is deferred** to a follow-up PT pending the actual persona-paragraph draft. Item 6 ship is gated on Item 3's persona-paragraph edit landing in the SAME PR — a soft PR-checklist gate, not automated. Worth instrumenting one week post-deploy via the existing `radbot/tools/telemetry/` to spot any drop in `transfer_to_agent` rate or rise in beto-handles-it-himself rate. If telemetry shows regression OR PR review missed the persona paragraph, rollback is a single-line revert of `assembly.py:317`. (Closes original Q5 with concrete tests + acknowledged v1 weak spot.)
6. **`mm-council` output contract drift.** New question — `/mm-council:evaluate` is owned in `~/git/perrymanuk/claude-skills`. The `COUNCIL_VERDICT:` line contract from Item 2 needs a parallel commit there. Track as a sibling task in the personal marketplace repo.

## Out of scope

- `chat_with_scout` MCP tool (true real-time push to Scout). Captured as a future enhancement; not required for the v1 loop.
- LiteLLM proxy in radbot (PRJ1/PT18). No longer on the critical path for council quality — mm-council bypasses it. **Disposition:** keep PT18 open in Telos but downgrade to "future infra; mm-council fills the cross-family gap at the human gate." Update PT18's description in Telos as part of Item 1.b's documentation pass.
- `radbot/mcp_server/tools/council.py` — exposing the in-process critics over MCP. Replaced by mm-council; not needed.
- `repo_exploration` MCP wrappers — pruned in earlier design discussion (Claude Code has Read/Grep/Glob natively).
- Notification / push to Perry's phone when an `EX<N>` flips to `proposed`. Pruned per user preference (no ntfy).
- A radbot-side UI for browsing postmortems and followups. Querying via Scout chat or this Claude Code session through MCP is sufficient for v1.
- Compare-and-swap / advisory locks on `telos_update_entry`. Deferred per concurrency invariant in Item 1 + Risk #3. Re-evaluate only if telemetry surfaces concurrent same-entry writes.

## Implementation order (revised)

**Pre-commit verification step (NEW — Round 2 council finding on line-ref drift):** before opening the Item 0+1.a PR, re-grep every `file:line` reference in this EX against current HEAD and update any that have drifted. The Round 2 grounding pass found `_render_section` cited as `:155` when the actual line is `:145` — silent drift like this rots reviewer trust. Run:
```bash
grep -nE "(radbot/[^ ]+\.py|specs/[^ ]+\.md|\.claude/[^ ]+):[0-9]+" docs/plans/EX_DRAFT_council_loop_polish.md
```
For each match, verify the line by reading the file. Update stale refs in the same commit as the implementation.

1. **Item 0 + Item 1.a (combined PR) — ✅ SHIPPED via PR #113 (commit `f0e6e37`, merged 2026-05-03, CI 100/100).** Original scope (preserved verbatim for context): the MCP write-surface expansion (`journal_add`/`journal_update`, `exploration_update.status` + `content`-optional, `exploration_add.status`, **`metadata_merge` on `task_add` + `exploration_add` (Item 0.b.ii — closes chain-race blocker)**, `metadata_merge` on `task_update` + `exploration_update` with silent whitelist-wins precedence, **structured-return contract for all four `*_add` tools incl. `milestone_add` with JSON `_err` envelope (Item 0.b.iv)**, `telos_get_section.metadata_filter` + `format=json` + `ACTIVE_EQUIVALENT` default + `status_in: list[str]` on `db.list_section`, `telos_get_entry.format=json` with `_iso_default` Z-suffix, sibling `_apply_metadata_gin_index()` step in `init_telos_schema()` (Item 0.c — closes GIN-on-existing-DB issue), `db.add_entry` postmortem `processed_at` invariant at the shared layer (Item 3 — closes agent-side-bypass)) AND the `STATUS_VALUES` extension in `models.py` + idempotent definition-aware CHECK constraint migration with preflight + generated SQL from `STATUS_VALUES` (Item 1.a — closes constraint-drift). All shipped as planned; the only deviation from the spec text is that `*_update` success envelopes echo the lifecycle state under the `entry_status` key instead of a `status` key, to avoid colliding with the envelope's `status: success/error` discriminator (consumer-visible — document if anyone parses `*_update` responses). **Hard prerequisite for Items 2–5: cleared.** Release-note line: code rollback to a pre-Item-1.a build is unsafe once any row holds a new lifecycle status — see Item 1.a Rollback section.
2. **Item 1.b + 1.c — ✅ SHIPPED via PR #114 (commit `a0c42a2`, merged 2026-05-03, CI 100/100).** Pure-docs PR: pinned the From → To / Actor / Trigger transition table verbatim into `CLAUDE.md` (extended the existing lifecycle subsection PR #113 added), `specs/agents.md` (new "Scout / Telos exploration lifecycle" subsection), `radbot/config/default_configs/instructions/scout.md` (`status="proposed"` entry-point note on `telos_add_exploration`), and `.claude/skills/ship/SKILL.md` (Phase 11 step 5 flips linked EX `executing → completed` post-merge — single ownership; end-of-skill `/postmortem-ex <PR#>` pointer). Encoded the v1 concurrency invariant + stuck-state-recovery one-liner + `metadata.superseded_by: "EX<N>"` shape pin. The lifecycle ref-code flip from `EX_DRAFT_*` to a Telos `EX<N>` was deferred (creating the Telos row would have widened the PR scope past pure docs); fold into Item 3's PR.
3. **Item 3 — ✅ SHIPPED via PR #115 (commit `5fb4138`, merged 2026-05-03, CI 100/100).** Pure-docs PR: added section 7 "Process pending postmortems (user-driven, never autonomous)" to `radbot/config/default_configs/instructions/scout.md` (160 lines) — three-rule contract covering `metadata_filter` query, `## Followups` parse + `sha256(jr_ref|role|ordinal)[:16]` deterministic dedup key + atomic `*_add` with `metadata_merge` (no add-then-update race), and `journal_update` with UNION `followup_refs` semantics. Spec sync: extended `specs/agents.md` lifecycle subsection with a one-paragraph "Postmortem processing flow" pointer pinning the markdown contract. Persona-paragraph edit to `main_agent.md` deferred to Item 6's PR per the original soft gate.
4. **Item 6 — ✅ SHIPPED via PR #116 (commit `a86f08a`, merged 2026-05-03, CI 100/100 — manual merge: path-guard flagged Makefile).** First code-bearing PR in the sequence. One-line drop of `inject_telos_context` from beto's `before_model_callback` (`assembly.py:317`) + compensating persona paragraph in `main_agent.md` § Telos. Scout-as-root retains the callback (sole consumer post-Item-6). AC #4 (b) automated baseline-snapshot test landed at `tests/integration/test_item6_telos_read_regression.py` + `tests/fixtures/item6_regression_baseline.json` with `make regen-item6-baseline` regen target. AC #4 (a)+(c) are PR-checklist manual smoke (CI has no LLM client). AC #1 producer-marker pinning anchored to ACTUAL `loader.py` markers (`TELOS ANCHOR` / `USER CONTEXT (Telos)` / `IDENTITY:` / `MISSION:`) per the original spec drift identified mid-implementation. AC #5 deferred per Risks #5. Specs-grep coherence AC met. Soft gate honored: Item 3's persona-paragraph edit landed in this PR. Token savings expectation: ~75 tokens/turn anchor + ~500 tokens first-turn-block per beto session — observe `context_injection` telemetry counter for a week.
5. **Item 2** (`/review-ex` skill) — depends on Item 0 + Item 1. First user-facing artifact, immediately useful. Sibling change in `claude-skills` repo: emit `COUNCIL_VERDICT:` line from `/mm-council:evaluate` AND honor the `synthesis_markdown_path` file convention from Item 2.
6. **Item 4** (`/postmortem-ex` sibling skill) — depends on Item 0.a + 0.b.i + 0.c (`telos_get_entry.format=json`) + Item 3 (deterministic followup-key derivation expects `## Followups` markdown structure that `/postmortem-ex` writes). Closes the loop. Ship after Item 3 so Scout knows what to do with postmortems when they arrive AND so the markdown contract is settled before `/postmortem-ex` writes against it.
7. **Item 5** (followup conventions) — formalized as Items 3+4 land; the verification queries are now possible from day one because Item 0.c shipped first.

Total estimated effort: ~3 days for the combined Item 0 + Item 1.a PR (heavier than the Round 2 estimate — adds `metadata_merge` schema fields on `task_add`/`exploration_add` plus the milestone_add JSON return contract, JSON `_err` envelope refactor across all eight write tools, `_iso_default` helper with literal `Z` suffix, `db.list_section` signature change with default-active-equivalent and `status_in` parameter, definition-aware CHECK migration with `pg_get_constraintdef` inspection and SQL generation from `STATUS_VALUES`, sibling `_apply_metadata_gin_index` step, `db.add_entry` postmortem invariant, plus the mandatory backward-compat audit pass), ~½ day for Items 1.b/1.c docs, ~1 day for Item 3 (deterministic followup-key derivation requires careful instruction-file rewrite + test fixtures), ~½ day for Item 6 (smaller scope but harder ACs), ~½ day for Item 2, ~1 day for Item 4 (step reorder + branch regex + abort flags), Item 5 is passive. Total ~6.5 days focused work.
