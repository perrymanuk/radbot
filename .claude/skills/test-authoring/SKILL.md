---
name: test-authoring
description: >
  Author unit tests for a radbot module using stub-first TDD with a diff-scoped
  mutation-score acceptance gate. Use when the user says "write tests for X",
  "add test coverage for X", "TDD this feature", or when adding a new tool /
  function that will ship without existing test coverage. Encodes EX18 / PT49:
  AAA pattern, test_<subject>_<behavior>_<condition> naming, mock-only-at-
  boundaries, 3-retry mutation-fix cap, mutation score ≥ 70% on changed files.
  Does NOT run global mutation — diff-scoped only.
---

# /test-authoring — stub-first TDD with mutation-gate finish

**DRAFT — user to refine.** Derived from radbot Telos EX18 (Agent Test Authoring Improvement Plan) + PT49, and wiki concepts [[agent-test-authoring]] and [[mutation-testing-llm]].

## Arguments

- `--target <path>` — file or dotted module to test (e.g. `radbot/tools/scheduler/engine.py`)
- `--scope harden|catch` — hardening (regression protect existing code) or catching (detect faults in new code). Default: inferred from git status.
- `--skip-mutation` — skip the mutation gate (local iteration only; NOT allowed in PR)
- `--min-score <N>` — override mutation-score floor (default 70)

## Constants

```
MAX_MUTATION_FIX_ATTEMPTS=3
DEFAULT_MIN_MUTATION_SCORE=70
DIFF_BASE=origin/main
```

## Non-negotiables

These are **hard rules**. A test run that violates any of them is a fail regardless of how green the bar is.

1. **AAA structure.** Every test has three comment-delimited sections: `# Arrange`, `# Act`, `# Assert`. No exceptions for "trivial" tests.
2. **Naming.** `test_<subject>_<behavior>_<condition>`. Examples: `test_scheduler_add_task_rejects_invalid_cron`, `test_memory_search_returns_empty_on_miss`. No `test_foo`, no `test_happy_path`.
3. **Mock only at system boundaries.** HTTP, DB, filesystem, external APIs. **Never mock the unit under test.** If the unit is too coupled to mock at a boundary, add a comment `# TODO: refactor coupling — see EX18` and mock the seam, but flag it explicitly.
4. **No `pass` bodies, no tautologies.** `assert foo() == foo()` is a fail. Every assertion must reference a value the test did not itself produce.
5. **Public interface only.** Do not test private methods (`_foo`), internal state, or implementation details. Test observable behavior.
6. **No `sleep()` based waits.** If timing matters, inject a clock or use `freezegun` / `time-machine`.

## Phase 1 — Understand the target

1. Read the target file and its siblings. Identify **public entry points** (what callers invoke).
2. Read any existing tests in `tests/unit/` for this module — match conventions and avoid duplication.
3. Read `specs/testing.md` for the quality-pipeline gate definitions.
4. Produce a one-paragraph plan: "I will test these N behaviors at the boundary of `<module>`. Inputs/outputs are `<shape>`. External dependencies to mock: `<list>`."
5. **Wait for user ack** before proceeding to Phase 2.

## Phase 2 — Stub-first scaffold (RED, without ImportErrors)

This is the single biggest departure from naive "failing-first TDD" — see EX18 council (Impl persona). If you write tests before stubs exist, the RED phase is `ImportError` and the feedback loop is garbage.

1. **If `--scope catch`** (new feature): create stub functions / classes in the target module with correct signatures and `pass` / `raise NotImplementedError` bodies. Commit this scaffold separately with `chore(test-scaffold): …`.
2. **If `--scope harden`** (existing code): skip stubbing; the target already exists.
3. Write the test file at `tests/unit/test_<module>.py` (or the matching nested path).
4. Every test body fully written: Arrange → Act → Assert. No `pass`. No `pytest.mark.skip`.
5. Run: `$(PYTEST) tests/unit/test_<module>.py -x`.
6. **Confirm every test fails with a real `AssertionError` or domain exception** — NOT `ImportError`, `AttributeError`, or `NameError`. If you see import-shaped failures, back up: the scaffold is wrong.
7. **STOP and show the user the RED output.** Do not proceed.

## Phase 3 — Implement (GREEN)

1. Fill in the stubs so tests pass. One behavior at a time.
2. Run after each edit: `$(PYTEST) tests/unit/test_<module>.py`.
3. Do not refactor yet. Do not touch unrelated code.
4. When all tests green: commit with `feat(<module>): …` or `fix(<module>): …`.

## Phase 4 — Refactor (still GREEN)

1. Clean up duplication, improve names, simplify.
2. Tests must stay green continuously. Run after every edit.
3. If a refactor breaks a test, revert the refactor — do not "fix" the test.

## Phase 5 — Mutation gate (the real acceptance criterion)

Coverage lies. A 93% line-coverage suite can have a 58% mutation score ([[mutation-testing-llm]] canonical case). This phase is where quality is actually graded.

1. Run: `make test-mutation-diff DIFF_BASE=origin/main MIN_SCORE=$(DEFAULT_MIN_MUTATION_SCORE)`.
2. Read `scripts/mutation-summary.py` output. For each surviving mutant:
   - Note the `file:line` and the diff.
   - Ask: **what assertion would have killed this mutant?** If none, the test suite is blind to this behavior.
3. Add kill-tests one surviving mutant at a time. Re-run the gate after each.
4. **Hard cap: `MAX_MUTATION_FIX_ATTEMPTS` (3) iterations.** If still below `MIN_SCORE` after 3 tries, STOP and escalate to the user — likely the code under test is not structured for testability and needs refactoring, OR the mutation is equivalent (see below).

### When a survivor is "equivalent"

Not every survivor indicates a missing test. Equivalent mutants produce semantically identical behavior (e.g. `x + 0` → `x + 1` in an unreachable branch). If you believe a survivor is equivalent:

1. Document in a comment **in the test file** (not the source): `# mutant <id>: equivalent — <rationale>`.
2. Cap equivalent-mutant claims at 20% of survivors per run. More than that = you're probably wrong.

## Phase 6 — Commit + ship

1. Final commit: `test(<module>): add unit tests (mutation score XX%)`.
2. Update `specs/testing.md` if you introduced a new testing convention.
3. Hand off to `/ship` as normal.

## Anti-patterns to reject immediately

| Symptom | What went wrong |
|---|---|
| Tests import `from <module> import _private_fn` | Phase 1 / rule 5 violated — testing internals |
| `mock.patch('<same module>.the_function_under_test')` | Rule 3 violated — mocked the unit |
| `assert result is not None` only | Tautological — what value do you expect? |
| Test passes without running the implementation | Over-mocking; real path never executed |
| `time.sleep(0.5)` anywhere | Rule 6 violated — inject a clock |
| Mutation score 100% on first try | Suspicious — are the tests actually running? Check `mutmut results` raw output |
| ImportError in Phase 2 RED | Scaffold is wrong — fix stubs before tests |

## Outputs

When this skill completes, the user should have:

- A commit series: `chore(test-scaffold)` → `feat/fix(module)` → `test(module)`.
- A mutation score printed in the final commit message.
- All phase gates explicitly observed (RED shown, GREEN shown, mutation survivors addressed or escalated).

## Open questions (for the user to resolve before first real use)

1. **Pilot module.** Scheduler (`radbot/tools/scheduler/engine.py`) vs Telos markdown I/O vs Reminders? EX18 doesn't scope a starter.
2. **Should Phase 5 be gated in `/ship`'s local pre-flight**, or only in the PR CI? Running mutmut locally on every ship adds 1–5 minutes per module.
3. **Integration with scout Plan Council (EX13).** Should scout grade *test plans* against this skill's rubric before axel implements?
4. **Equivalent-mutant claim review** — who audits? If nobody, agents will over-use the escape hatch.

## References

- `explorations:EX18` — Agent Test Authoring Improvement Plan (council-reviewed)
- `project_tasks:PT49` — mutation-summary.py + test-mutation-diff (prerequisite, landed alongside this skill)
- `wiki/concepts/agent-test-authoring.md` — prompt patterns, anti-patterns
- `wiki/concepts/mutation-testing-llm.md` — coverage-vs-mutation gap, hybrid CI pattern
- [Yoshimoto et al., MSR '26](https://arxiv.org/abs/2603.13724) — AI authors 16.4% of test commits; higher assertion density
- [Meta ACH / JiTTesting](https://www.infoq.com/news/2026/01/meta-llm-mutation-testing/) — 73% engineer acceptance, 4× regression catch
