# Telos — Persistent Self-Context for radbot

## Purpose

Give beto and all sub-agents a structured, always-loaded understanding of the
user (role, mission, goals, projects, challenges, wisdom, taste, calibration
history, journal). The file is **alive**: the agent writes to it during
interactions so it compounds over time, instead of sitting frozen as a prompt
append.

Adapted from [Daniel Miessler's Telos framework](https://github.com/danielmiessler/Telos).
The conceptual path — **Problems → Mission → Narratives → Goals → Challenges →
Strategies → Projects → Journal** — is preserved so the file roundtrips with
canonical Telos markdown (paste in, paste out, shared across tools).

Single-user system (`user_id = "web_user"`); no user scoping in schema.

---

## Data model

One table, one source of truth. Section-specific metadata lives in JSONB so we
don't churn the schema when adding sections.

```sql
CREATE TABLE telos_entries (
    entry_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    section      TEXT NOT NULL,          -- see section catalogue below
    ref_code     TEXT,                   -- "G1", "P3", "PRED4" — human-readable, unique within section
    content      TEXT NOT NULL,          -- the main body of the entry
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,  -- section-specific fields
    status       TEXT NOT NULL DEFAULT 'active',      -- active | completed | archived | superseded
    sort_order   INTEGER NOT NULL DEFAULT 0,          -- for user-defined ordering of goals, problems, etc.
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (section, ref_code)
);

CREATE INDEX idx_telos_section_status ON telos_entries (section, status);
CREATE INDEX idx_telos_active ON telos_entries (section) WHERE status = 'active';
CREATE INDEX idx_telos_journal_recent ON telos_entries (created_at DESC) WHERE section = 'journal';
```

`identity` is a special single-entry section: enforced by convention (the tools
only ever upsert one entry with `ref_code = 'ME'`), not by a DB constraint.

### Section catalogue

Each section's `metadata` JSONB shape is documented here. The loader, tools,
and markdown parser all agree on these shapes.

| Section         | Cardinality | Metadata fields |
|-----------------|-------------|-----------------|
| `identity`      | 1           | `{name, location, role, pronouns?}` |
| `history`       | N           | `{}` (prose) |
| `problems`      | N           | `{}` — top-level things the user is trying to solve |
| `mission`       | N           | `{}` — usually 1-3 entries |
| `narratives`    | N           | `{}` — self-story sentences |
| `goals`         | N           | `{deadline?, kpi?, parent_problem?, status_notes?}` |
| `challenges`    | N           | `{parent_goal?}` |
| `strategies`    | N           | `{parent_goal?, parent_challenge?}` |
| `projects`      | N           | `{priority?, parent_goal?, due?}` |
| `wisdom`        | N           | `{origin?}` — principles user lives by |
| `ideas`         | N           | `{}` — opinions / hot takes |
| `predictions`   | N           | `{probability, deadline, resolution?, resolved_at?, outcome?}` |
| `wrong_about`   | N           | `{origin_date?, source?}` — calibration history |
| `best_books`    | N           | `{sentiment: strong_positive, note?}` |
| `best_movies`   | N           | `{sentiment, note?}` |
| `best_music`    | N           | `{sentiment, note?}` |
| `taste`         | N           | `{category, sentiment}` — misc preferences (food, tools, games) |
| `traumas`       | N           | `{}` — sensitive, on-demand only |
| `metrics`       | N           | `{target?, current?, unit?}` — long-lived KPIs |
| `journal`       | N           | `{event_type?, related_refs?: [str]}` — append-only stream |

`status` values:
- `active` — currently true / in force
- `completed` — goal achieved, prediction resolved, challenge overcome
- `archived` — no longer relevant but kept for history
- `superseded` — replaced by a newer entry (store the new `ref_code` in `metadata.superseded_by`)

---

## Injection model

Telos is beto-only. Sub-agents (casa, planner, tracker, comms, axel, scout)
are tool executors — they need scoped instructions + their tools, not the
user's mission / wisdom / journal. Injecting Telos into their prompts would
bloat them for zero benefit and muddy their single-purpose framing.

Within beto, the block is **not** sent with every turn. That's wasteful as
Telos grows and dilutes signal on routing-heavy turns where persona is
irrelevant. Three tiers strike the balance:

| Tier | When | Size | Purpose |
|---|---|---|---|
| 1. Anchor | Every turn | ~300 bytes | Identity + Mission + pointer to tools |
| 2. Full block | First turn of each session | ~2KB | Ground beto in the user's full context at session start |
| 3. On-demand sections | Tool call | arbitrary | Deep dive when relevant |

### Why session-start works

ADK chat sessions have stable IDs; each new web chat or CLI session gets a
fresh one. The full block is injected into the **conversation history** on
turn 1, so it stays in-context for all subsequent turns in that session
without re-sending. Subsequent turns carry only the anchor (in
`system_instruction`) — enough to keep beto grounded and to remind it that
`telos_get_section` / `telos_get_full` exist for deeper lookups.

When ADK eventually compacts / summarises old turns, the turn-1 Telos block
may get compressed out. The anchor present on every turn ensures beto
always knows how to re-fetch.

### Implementation — beto-only, via `before_model_callback`

`global_instruction` is **not** used for Telos — ADK propagates it to sub-
agents. Instead, a callback on beto's `before_model_callback` chain
appends to beto's `system_instruction` at request time:

```python
# radbot/tools/telos/callback.py
_ANCHOR_TEMPLATE = """TELOS ANCHOR: {identity_line}
Mission: {mission_line}
{counts_line}
Use telos_get_section(name) or telos_get_full() for details.
"""

def inject_telos_context(callback_context, llm_request):
    anchor, full_block = build_telos_tiers()  # loader builds both
    if not anchor:
        return  # empty Telos — callback is a no-op

    # Tier 1: anchor goes on every turn
    existing = llm_request.config.system_instruction or ""
    llm_request.config.system_instruction = f"{existing}\n\n{anchor}"

    # Tier 2: full block on first turn of session only
    if not callback_context.state.get("telos_bootstrapped"):
        llm_request.contents = inject_system_note_at_start(
            llm_request.contents, full_block
        )
        callback_context.state["telos_bootstrapped"] = True
```

Tier 2 is injected as a synthetic first "system note" turn in
`llm_request.contents` so it lands in the conversation history and stays
visible for the whole session. Tier 1 goes into `system_instruction` so
it's present on every call regardless of history compaction.

The callback is registered only on the root `beto` agent in
`agent_core.py:168` — sub-agents' callback chains are untouched.

### Anchor contents (Tier 1, every turn)

Kept deliberately small:

```
TELOS ANCHOR: Perry (realitysandwich@gmail.com), <role>, <location>
Mission: <first active mission, one line>
Active: N goals, M projects, K problems, J active journal entries
Use telos_get_section(name) or telos_get_full() for details.
```

Hard cap: 500 bytes. If Identity or Mission entries are long, truncate to
one line each.

### Full block contents (Tier 2, session start)

Built by `build_telos_tiers()`, returned alongside the anchor. Contents, in
order, each skipped if empty:

1. **Identity** — one-liner
2. **Mission** — all `active`
3. **Problems** — all `active` (summary only: `ref_code: content`)
4. **Goals** — all `active`, sorted by `sort_order`
5. **Active projects** — `active` only
6. **Challenges** — `active` only
7. **Wisdom** — all (usually short list)
8. **Recent journal** — last 5 entries, `created_at` desc

Hard budget: target ~2KB, truncate journal first if over. On a fresh
install (empty DB), both anchor and full_block are empty and the callback
is a no-op — beto runs with its normal instruction only.

### Mid-session data changes

Ambient writes by beto during a session (new journal entry, resolved
prediction, added wisdom) are already visible to beto in the transcript —
beto saw its own tool call. No re-injection needed within the session.

Admin-UI edits during a live session are rare for a single-user setup. If
it becomes a real issue, the anchor can include a `telos_version` derived
from `SELECT MAX(updated_at) FROM telos_entries` (cached for a few
seconds). Comparing against `callback_context.state["telos_bootstrapped_version"]`
lets us re-trigger Tier 2 when they diverge. Deferred until needed —
overkill for Phase 1.

### On-demand sections (Tier 3)

Beto calls `telos_get_section(section)` or `telos_get_full()` when a
section is relevant to the current request. Full list of retrievable
sections matches the catalogue above. `traumas` is on-demand only (never
always-loaded — privacy).

---

## Tools (FunctionTools on beto)

All tools return `{"status": "success" | "error", ...}` per radbot convention.
Silent vs. confirm-required is enforced by the agent's instructions, not the
tool signature — the tool just does what it's asked.

### Read tools

| Tool | Purpose |
|---|---|
| `telos_get_section(section: str)` | Return all active entries in a section |
| `telos_get_entry(section: str, ref_code: str)` | Fetch one entry by ref_code |
| `telos_get_full()` | Return full Telos as canonical markdown (for review / export) |
| `telos_search_journal(query: str, limit: int = 20)` | Simple ILIKE search over journal content |

### Silent-update tools (no confirmation required)

| Tool | Trigger heuristic |
|---|---|
| `telos_add_journal(entry, event_type=None, related_refs=None)` | Anything notable that happens in the conversation |
| `telos_add_prediction(claim, probability, deadline)` | User makes a claim with a probability or timeframe |
| `telos_resolve_prediction(ref_code, outcome, actual_value=None)` | Resolution moment; auto-adds a `wrong_about` entry if `outcome == False` and `probability >= 0.75` |
| `telos_note_wrong(thing, why)` | User acknowledges being wrong about something |
| `telos_note_taste(category, item, sentiment, note=None)` | Strong opinion on a book/movie/music/food/tool |
| `telos_add_wisdom(principle, origin=None)` | User voices a quotable principle they live by |
| `telos_add_idea(idea)` | User voices a strong opinion/hot-take |

### Confirmation-required tools (agent proposes, user approves in plain language)

| Tool | Why it's structural |
|---|---|
| `telos_upsert_identity(...)` | Changes the always-loaded one-liner about who you are |
| `telos_add_problem(description)` / `telos_update_problem(ref_code, ...)` | Top-level framing — rare, high-impact |
| `telos_upsert_mission(content, replace_ref=None)` | Rare, reframes everything downstream |
| `telos_add_narrative(content)` / `telos_update_narrative(ref_code, ...)` | Self-story — structural |
| `telos_add_goal(title, deadline=None, kpi=None, parent_problem=None)` | Significant commitment |
| `telos_update_goal(ref_code, status=None, deadline=None, kpi=None, notes=None)` | Changes live commitment |
| `telos_complete_goal(ref_code, resolution)` | Marks success; auto-adds journal entry |
| `telos_add_challenge(description, parent_goal=None)` | Structural |
| `telos_add_strategy(content, parent_goal=None, parent_challenge=None)` | Structural |
| `telos_add_project(name, priority=None, parent_goal=None, due=None)` / `telos_update_project(...)` | Active work scope |
| `telos_archive(section, ref_code, reason)` | Soft-delete — always confirm before losing state |

Policy enforcement lives in `main_agent.md`:

> **Telos update policy.** You have tools that modify the user's persistent
> Telos file. For tools marked silent (journal, predictions, wrong-about,
> taste, wisdom, ideas), update freely when the conversation clearly warrants
> it — do not ask permission. For all other telos_* tools, propose the change
> in one plain sentence and wait for confirmation before calling. Never
> archive without explicit approval.

### Ref-code assignment

When creating entries in sections that use ref_codes (problems, goals,
predictions, projects, challenges, strategies, narratives), the tool auto-
assigns the next available code: `P1`, `P2`, … for problems; `G1`, `G2`, …
for goals; `PRED1` … for predictions. Prefix table lives in `models.py`.
Users can override by passing `ref_code` explicitly.

---

## Markdown I/O

`radbot/tools/telos/markdown_io.py` provides:

- `parse_telos_markdown(text: str) -> list[Entry]` — strict parser for the
  canonical Telos format (`## SECTION` headers, `- REF: content` bullets).
- `render_telos_markdown(entries: list[Entry]) -> str` — inverse.

Round-trip rule: parse → render → parse must be idempotent. Unknown sections
parse into `metadata.raw_section_name` and render back unchanged.

Used by:
- `telos_get_full()` tool (export)
- Admin UI "Import" textarea (paste a canonical Telos md file)
- CLI one-shot: `uv run python -m radbot.tools.telos.cli import path/to/telos.md`

---

## File layout

```
radbot/tools/telos/
├── __init__.py          # exports init_telos_schema, build_telos_context, tool list
├── db.py                # init_telos_schema(), CRUD (add_entry, update_entry, list_by_section, archive, bulk_upsert)
├── models.py            # Entry dataclass, Section enum, REF_PREFIX map
├── telos_tools.py       # FunctionTools — all telos_* tools wrapped here
├── loader.py            # build_telos_tiers() -> (anchor_str, full_block_str)
├── callback.py          # inject_telos_context — tier 1 every turn, tier 2 session-start only (state flag)
├── markdown_io.py       # parse_telos_markdown, render_telos_markdown
└── cli.py               # uv run python -m radbot.tools.telos.cli {onboard|import|export|show|reset}
```

Admin API and UI (Phase 2) live in the standard locations:
- `radbot/web/api/telos.py` — REST router
- `radbot/web/frontend/src/components/admin/panels/TelosPanel.tsx` — edit UI

---

## Integration points

All file:line refs verified against current `main`:

| Change | Location |
|---|---|
| Register schema init | `radbot/agent/agent_tools_setup.py:27` — add `("telos_init", "radbot.tools.telos", "init_telos_schema")` to `_SCHEMA_INITS` |
| Inject Telos into **beto only** | `radbot/agent/agent_core.py:168` — add `inject_telos_context` from `radbot.tools.telos.callback` to the root agent's `before_model_callback` list. Do **not** use `global_instruction` (propagates to sub-agents). Do **not** add to `_before_cbs` used by sub-agents at line 151 |
| Register beto's read + write tools | `radbot/agent/agent_core.py` — where `beto_tools` is assembled (just before line 160); add the Telos tool list alongside memory tools |
| Agent guidance | `radbot/config/default_configs/instructions/main_agent.md` — add "Telos update policy" section only (silent vs. confirm tools). No onboarding text |
| Startup schema init (idempotent safety net) | `radbot/web/app.py :: initialize_app_startup()` — add `from radbot.tools.telos import init_telos_schema; init_telos_schema()` alongside existing schema inits |

**Scoped memory vs Telos**: sub-agents keep their per-agent Qdrant memory
(source_agent tag). Telos lives **only** on beto — sub-agents are tool
executors and don't need the user's mission / wisdom / journal in their
prompts. The callback is deliberately attached to beto's callback chain,
not the shared `_before_cbs` list used by sub-agents.

---

## Admin UI (Phase 2)

Single navigation entry at `/admin/` → "Telos". The panel branches on
`GET /api/telos/status`:

- **`has_identity === false`** → render the onboarding wizard (see
  Onboarding section above). One-time; never shown again after Identity
  is saved.
- **`has_identity === true`** → render the normal editor:
  - **Identity** — single form (name, location, role, pronouns)
  - **Mission / Problems / Goals / Projects / Challenges** — editable lists with add/archive/complete
  - **Predictions** — list with "resolve" buttons (prompts for outcome)
  - **Journal** — chronological feed, read-only except for manual add
  - **Wisdom / Ideas / Taste** — editable lists
  - **Wrong About** — list (rarely edited)
  - **History / Traumas** — freeform prose editors, collapsed by default
  - **Import / Export** — markdown textarea + download/upload buttons

Follows existing admin-panel patterns in
`radbot/web/frontend/src/components/admin/panels/`. No credential store
integration — Telos isn't secret, just user content in a regular DB table.

Not required for Phase 1 — CLI onboarding and direct DB editing cover
the one-time bootstrap.

---

## Onboarding

Radbot is single-user, single-install. Onboarding is a **one-time setup
event**, not an agent conversation — the agent shouldn't know about it at
all. Baking the interview into `main_agent.md` or a skill file would waste
prompt tokens forever after it's done, and complicates beto's framing for a
task beto doesn't need to own.

Instead, onboarding runs **outside the agent loop**, directly populating the
DB. Two entry points, both writing via the same REST endpoints:

### Primary: admin panel wizard

A guided form in the existing admin UI at `/admin/` → "Telos" →
"Onboarding" (only shown while the DB is empty; hidden once Identity
exists). Multi-step wizard covering the same 9 sections:

1. Identity (name, location, role, pronouns) — single form
2. Problems (1–3, add rows)
3. Mission (1–2 sentences)
4. Goals (add rows, each with optional deadline + KPI)
5. Projects (add rows, optional priority + due)
6. Challenges (add rows, optional parent goal dropdown)
7. Wisdom (add rows, optional origin)
8. Taste — best books / movies (add rows)
9. History (freeform textarea — optional, explicitly skippable)

Each step has "Skip" and "Save & Next." At any point the user can "Finish"
to commit what they have. Final step saves everything in one transaction
via `POST /api/telos/bulk` and flips the wizard to hidden on subsequent
loads.

Traumas and predictions are not part of the wizard — too sensitive /
session-dependent. Those populate through ambient agent updates later.

### Secondary: CLI

Power-user alternative, for folks who'd rather answer in a terminal:

```bash
uv run python -m radbot.tools.telos.cli onboard
```

Interactive prompt loop, same 9 questions, same destination. Also:

```bash
uv run python -m radbot.tools.telos.cli import path/to/my_telos.md
uv run python -m radbot.tools.telos.cli export > my_telos.md
uv run python -m radbot.tools.telos.cli reset   # wipes all entries (confirms)
```

### Completion marker

Presence of an `identity` entry. The admin panel checks
`GET /api/telos/status` → `{has_identity: bool}` to decide whether to show
the onboarding wizard or the normal editor. That's the only place the
"onboarded?" question is asked — beto never sees this flag.

### Agent involvement: none

- `main_agent.md` gets only the Telos **update policy** (silent vs.
  confirm tools). No onboarding instructions, no skill file, no nudges.
- No `telos_onboarding_status` tool. Deleted from the tool list.
- `before_model_callback` does not inject any onboarding hint. On empty
  Telos it simply injects nothing.
- `telos_import_markdown` **stays** as an agent tool — it's a legit
  utility ("load this Telos file I just pasted") unrelated to onboarding.

---

## Phased plan

### Phase 1 — Backend MVP + CLI onboarding (1 PR)

Ships the smallest thing that works end-to-end: schema, agent tools, beto
injection, and a way to actually populate the DB (CLI onboarding + markdown
import).

1. `radbot/tools/telos/` module: `db.py`, `models.py`, `loader.py`,
   `callback.py`, `markdown_io.py`, `telos_tools.py`, `cli.py`
2. Register schema init in `agent_tools_setup.py` + `app.py`
3. Wire `inject_telos_context` into **beto's** `before_model_callback` list
   in `agent_core.py:168` — **not** into the shared `_before_cbs` used by
   sub-agents (line 151). Not via `global_instruction`
4. Register Telos read + write tools on beto (`telos_get_*`, silent tools,
   confirm-required tools, `telos_import_markdown`). No
   `telos_onboarding_status`
5. Update `main_agent.md` with the Telos **update policy** only (silent vs.
   confirm-required tools). No onboarding instructions
6. CLI onboarding: `uv run python -m radbot.tools.telos.cli onboard`
   (interactive prompts), plus `import`, `export`, `show`, `reset`
   subcommands
7. Unit tests: markdown round-trip; silent tool creates entry; confirm-
   required tool creates entry (no enforcement at tool layer — instructions
   do that); `build_telos_tiers()` anchor ≤500 bytes; full block ≤2KB;
   callback injects full block only on first turn (state flag gates it);
   subsequent turns receive anchor only; callback does nothing when DB
   is empty; callback is present on beto but absent from sub-agents
8. Update `specs/tools.md` (new section listing), `specs/agents.md` (beto
   tool count), `specs/storage.md` (new table), `SPEC.md` (quick-ref)

**Bootstrap path for first run**: after deploying, run
`uv run python -m radbot.tools.telos.cli onboard` once in the terminal to
populate the DB. From there, the agent keeps it alive ambiently. Admin UI
onboarding wizard is Phase 2.

### Phase 2 — Admin UI + onboarding wizard (1 PR)

1. `radbot/web/api/telos.py` — REST router:
   - `GET /api/telos/status` → `{has_identity}`
   - `GET /api/telos/section/{section}` / `GET /api/telos/full`
   - `PUT /api/telos/entry/{section}/{ref_code}` / `POST /api/telos/entry/{section}`
   - `POST /api/telos/archive/{section}/{ref_code}`
   - `POST /api/telos/bulk` — atomic multi-section upsert (used by wizard)
   - `POST /api/telos/import` (markdown body) / `GET /api/telos/export`
2. `TelosOnboardingWizard.tsx` — multi-step form, only rendered when
   `status.has_identity === false`
3. `TelosPanel.tsx` — normal editor for sections (identity, mission,
   problems, goals, projects, challenges, wisdom, ideas, predictions with
   resolve, journal feed, taste, wrong-about, history, traumas); shown
   when `status.has_identity === true`. Includes import/export markdown
   textarea
4. Register in `AdminPage.tsx` NAV_ITEMS + PANEL_MAP (single "Telos"
   entry; the panel internally branches wizard vs. editor on status)
5. Update `specs/web.md` (new router + panel)

### Phase 3 — Review loop (optional, 1 PR)

A scheduled task that runs weekly (via existing `tools/scheduler/`):

> "Review predictions past their deadlines, goals nearing their deadlines,
>  recent journal entries that might be wisdom worth canonicalizing, and
>  active problems that haven't had journal activity in 60+ days."

Agent proposes edits, user approves. Uses only existing tools; no new code
beyond registering the scheduled task prompt.

---

## Open design questions (to decide before coding)

1. **Should `telos_resolve_prediction` auto-create a `wrong_about` entry on
   miscalibration?** Current draft says yes when `outcome == False` and
   `probability >= 0.75` (you were confident and wrong). Could also cover the
   symmetric case (outcome True, probability ≤ 0.25). Tradeoff: automatic
   miscalibration logging is the whole point of predictions, but feels
   presumptuous if the agent does it silently. Proposal: silent, because the
   user can always ask the agent to remove entries.

2. **Section size caps for always-loaded?** e.g. if you have 50 active goals
   the `global_instruction` bloats. Proposal: hard cap of 15 goals / 10
   projects / 10 challenges / 20 wisdom items in always-loaded; the full list
   is still available via `telos_get_section`. Overflow is surfaced in the
   injection as `"(+N more — call telos_get_section('goals') for full list)"`.

3. **Multi-line content** (e.g. long mission paragraphs) — supported in the
   DB (content is TEXT), but canonical Telos markdown uses single-line
   bullets. Proposal: markdown parser allows indented continuation lines and
   joins them with `\n`; renderer emits them the same way.

4. **ref_code collisions on markdown import** — if an imported file reuses a
   code that's already in the DB, either overwrite or renumber. Proposal:
   import is always "merge into current" (update existing by ref_code, add
   new ones). A separate `--replace` flag wipes the section first.

5. **Journal retention** — unbounded growth is fine for now (one user, text
   is cheap). Revisit if the table exceeds ~10K rows; add an archive job
   that moves entries older than 2 years to `status='archived'` so the
   "recent 5" query stays fast (the partial index already handles this).
