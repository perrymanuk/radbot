---
name: telos-review
description: >
  Operate the Claude Code side of the Telos Bipartite Review Loop — the formal
  Scout↔Claude Code protocol for grounding plans in codebase reality before
  execution. Use when the user says "review EX<N>", "reality check this
  exploration", "check scout's plan", "read EX<N> from telos", or wants to
  pressure-test an exploration written by Scout. Also use when the user says
  "execute PT<N>", "work PT<X> then PT<Y>", "run the telos tasks", or asks to
  pick up Project Tasks that Scout has solidified. Covers both the read-only
  Reality Check stage (Stage 2) and the Contract Execution stage (Stage 4) of
  the lifecycle. Trigger aggressively whenever the user references an EX<N> or
  PT<N> code from Telos in a way that implies review or execution — the
  lifecycle discipline matters more than the exact phrasing.
---

# telos-review — Bipartite Review Loop (Claude Code side)

## What this skill is

Radbot uses a **Bipartite Review Loop** to keep plans honest. Scout drafts
hypotheses in Telos; Claude Code (you) grounds them against the real
repository before they harden into Project Tasks. This skill is the Claude
Code half of that protocol.

The loop has five stages. You are invoked for two of them:

- **Stage 2 — Reality Check** — read an Exploration (`EX<N>`), compare it to the
  actual codebase, report what will break. **Do not implement anything.**
- **Stage 4 — Contract Execution** — once Scout has solidified the plan into
  Project Tasks (`PT<N>`), pick them up one at a time and execute.

Stages 1, 3, 5 happen on Scout's side (and in Perry's head) — you do not drive
them, but you should understand them so your output feeds them cleanly.

## Memory primitive discipline

Radbot's memory primitives are strictly typed. When writing back to Telos or
memory, respect the boundary — do not conflate them:

| Primitive | Purpose | Who writes |
|---|---|---|
| `store_agent_memory` | Durable architectural patterns, repo rules, web findings | Scout (post-mortem) |
| `telos_add_journal` | Personal trajectory, state changes, daily decisions | Scout (post-mortem) |
| `telos_add_exploration` (`EX<N>`) | Long-form proposals, 5-role context packages, **unverified** | Scout (Stage 1) |
| `telos_add_task` (`PT<N>`) | Granular, single-turn-sized execution bounds on a Project | Scout (Stage 4) |

The 5-role context package inside an Exploration is: **Authority** (who/what
decided this), **Exemplar** (concrete pattern to follow), **Constraints**
(hard limits), **Rubric** (how we know it's done), **Metadata** (refs,
dependencies). Review against these roles — each one is a place the plan can
fail.

## Stage 2 — Reality Check

### Rule #1: you do not write code in this stage

The whole point of the Bipartite Review Loop is that Scout's plan may be
elegant in the abstract but broken against physical repo constraints. If you
start editing, you collapse the review into implementation and Scout never
gets the feedback. **Read, grep, reason, report. No Edit / Write / Bash
mutations.**

If you notice a trivial fix while reading, *still do not fix it* — note it in
the report. Perry will relay to Scout and the plan will absorb it.

### Procedure

1. **Fetch the exploration from Telos.** Use `mcp__radbot__telos_get_entry`
   with the section `explorations` and the `ref_code` the user named (e.g.
   `EX12`). If the user didn't name one, ask — don't guess from recent
   journal entries, because Explorations and Journals live in separate
   sections.

2. **Read the 5-role context package carefully.** Before touching the repo,
   write down (in your head, or a short scratch block) what each role is
   claiming:
   - What Authority / decision is being invoked?
   - What Exemplar file/pattern is the plan imitating?
   - What Constraints does Scout think apply?
   - What Rubric will say this is done?
   - What Metadata (refs, deps, affected modules) is declared?

3. **Consult the LLM Wiki for external research context.** Invoke the
   `llm-wiki:query` skill with the exploration's topic and any library /
   pattern / technique names Scout cited. The wiki is our **research**
   knowledge base — agentic AI patterns, Claude Code practice, production
   agent deployments, AI-intel feeds (HN / arxiv / YouTube). Use it to
   check whether the approach Scout proposed has known pitfalls, better
   alternatives, or prior art from outside this repo. **The wiki is not a
   source of internal project decisions** — those live in `SPEC.md`,
   `specs/*.md`, `CLAUDE.md`, and `docs/`, which you read separately in
   step 4. If the wiki surfaces something that contradicts or refines the
   plan, fold it into the review. If it's silent on a technique the plan
   leans on heavily, that's a research gap worth flagging.

4. **Ground each role against the codebase and internal docs.**
   - Exemplar: does the referenced file/pattern actually exist and still
     look the way Scout described? Read it. Patterns rot.
   - Constraints: are there *other* constraints Scout missed? Grep for
     callers of any function the plan wants to change. Read the spec files
     (`SPEC.md`, `specs/*.md`, `CLAUDE.md`) and `docs/` entries that govern
     the affected area — these are the canonical internal record and
     override anything the wiki says about how *this* project works.
   - Metadata: follow at least one dependency link. If Scout says "uses
     `get_integration_config`," open that function and confirm the signature
     still matches what the plan assumes.
   - Rubric: is the success criterion actually observable from outside? If
     not, Scout probably needs to add a test surface before this can ship.

4. **Look for the classes of failure Scout can't see from outside the repo:**
   - **Stale references** — file/function/flag named in the plan has been
     renamed or removed.
   - **Hidden callers** — the change surface has more callers than the plan
     acknowledges.
   - **Spec drift** — the plan contradicts a rule in `CLAUDE.md` /
     `specs/*.md` that Scout didn't re-read.
   - **Context engineering issues** — the plan would require a single Claude
     Code turn to hold more context than is reasonable (cross-cutting, many
     files, ambiguous boundaries). Flag this; Scout should split.
   - **Agentic technical debt** — the plan ships a shortcut that will force
     future turns to work around it (missing tests, silent fallbacks,
     backwards-compat shims the code doesn't need).
   - **Dependency clashes** — the plan assumes a library/version/behavior
     that isn't what's actually installed (`pyproject.toml`, lockfiles).

5. **Report in this shape.** Keep it scannable — Perry will paste this back
   to Scout:

   ```
   ## Reality Check: EX<N>

   **Verdict:** <airtight | needs revision | fundamentally broken>

   **Grounded correctly:**
   - <role or claim that checks out, with file:line evidence>

   **Will break:**
   - <concrete failure mode, with file:line evidence and why it breaks>

   **Missing from the plan:**
   - <constraint / caller / spec rule Scout should have cited>

   **Suggested refinements for Scout:**
   - <what to change in EX<N> to make it airtight — as guidance, not a rewrite>
   ```

6. **Stop.** Do not proceed to implementation even if the plan looks perfect.
   The handoff from Stage 2 → Stage 4 goes through Scout, not directly from
   you. Perry will come back with `PT<N>` codes when the contract is ready.

### Why no edits in Stage 2

Two reasons. First, the Exploration is still Scout's artifact — mutating the
code underneath an unratified plan creates a state Scout didn't see. Second,
the review's value is precisely that you haven't committed yet; the moment
you start implementing, your incentive shifts from "find problems" to "make
this work," and the review degrades.

## Stage 4 — Contract Execution

Once Scout has broken `EX<N>` into `PT<N>` tasks, each task is sized so one
Claude Code turn can complete it. Your job is to execute them — one at a
time, in the order Perry specifies.

### Procedure

1. **Fetch each task** via `mcp__radbot__telos_get_entry` (section:
   `project_tasks`, ref_code: `PT<N>`). If Perry names multiple (e.g.
   "execute PT34 then PT35"), fetch them all up front so you can see the
   shape, but **execute sequentially** — do not interleave.

2. **Before touching a task, verify its preconditions.** The contract was
   written when Scout and you both agreed `EX<N>` was airtight, but time may
   have passed or the previous `PT<N>` may have shifted state. If the
   preconditions no longer hold, stop and tell Perry — don't improvise
   around a broken contract.

3. **Execute within the task's bounds.** `PT<N>` tasks are deliberately
   narrow. If you find yourself wanting to do work that isn't in the task,
   that's a signal the contract needs to go back to Scout for re-scoping,
   not that you should expand scope. Note it and finish the task you were
   given.

4. **Mark the task complete** via `mcp__radbot__task_complete` when done,
   with a brief completion note. This is what lets Stage 5 (Scout's
   post-mortem) find the task and extract lessons.

5. **Report to Perry**: what changed (files + a one-line summary), any
   friction you hit, and whether the next `PT<N>` in the chain still looks
   executable given the state you left the repo in. Keep it terse — Perry
   will relay the friction notes to Scout for Stage 5.

### Don't skip the post-mortem surface

Stage 5 is how Scout learns. Your completion note and friction report are
the raw material. If something was harder than the plan suggested, *say so*
even if the task succeeded. Silent successes produce worse future plans
than noisy successes.

## Triggering shortcuts

- User names a code starting with `EX` → Stage 2 (Reality Check).
- User names a code starting with `PT` → Stage 4 (Contract Execution).
- User says "review scout's plan" without a code → ask which `EX<N>`;
  optionally list recent explorations via `mcp__radbot__search_memory` or
  `telos_get_section` before asking.
- User says "work through the telos tasks" without codes → list the open
  `PT<N>` tasks via `mcp__radbot__list_tasks` and confirm the order with
  Perry before starting.

## Anti-patterns

- **Collapsing Stage 2 into Stage 4.** Reading `EX<N>` and then implementing
  it directly because it "looks fine." Defeats the loop.
- **Writing new tasks yourself.** `PT<N>` creation belongs to Scout. If you
  think a task is missing, report that as a refinement suggestion in the
  Reality Check output.
- **Editing the Exploration.** You do not mutate `EX<N>`. Scout owns the
  drafting table.
- **Silent scope creep during Stage 4.** Expanding a `PT<N>` because it
  "obviously also needs X." Finish the bounded task, report X as friction.
- **Skipping the Exemplar check.** The Exemplar is the most common source
  of plan rot — a named pattern that has since moved or been replaced.
  Always read the file Scout cited.
