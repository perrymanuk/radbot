# Browser e2e tests

How-to for working with the Playwright suite. Spec is in `specs/testing.md`.

## Adding a new spec

1. Add the file to `radbot/web/frontend/e2e/specs/your-feature.spec.ts`.
2. Add `data-test` attributes to the React components you assert on. Naming: `kebab-case-feature-element` (e.g. `your-feature-submit`). Register new attributes in `specs/web.md` § `data-test` attribute convention.
3. That's it — CI runs the full suite every run (EX25 / PT73 removed the manual coverage-map layer). No mapping step required.

## Adding a new chat scenario

Edit `radbot/web/frontend/e2e/specs/chat-scenarios.ts`:

```ts
{
  name: "your-scenario",
  prompt: "what the user types",
  expect: "What beto SHOULD do (and the negative cases — what beto must NOT do).",
  timeoutMs: 30_000,
}
```

The judge model uses your `expect` rubric verbatim. Be specific. Vague rubrics produce vague verdicts and false positives.

## Running locally

| Mode | Command | Use when |
|---|---|---|
| Dev-server fast loop | `make test-e2e-browser-dev` | Authoring or debugging a spec; sub-second iteration |
| Docker stack (CI parity) | `make test-e2e-browser` | Pre-push sanity check |
| Interactive UI | `cd radbot/web/frontend && npm run test:e2e:ui` | Stepping through a flaky test |
| Headed | `cd radbot/web/frontend && npm run test:e2e:headed` | Watch the browser |

Prerequisites:
- `RADBOT_ADMIN_TOKEN` in `.env` at repo root.
- `ANTHROPIC_API_KEY` exported in shell or `.env.local`.
- `GEMINI_API_KEY` in your dev DB credential store (already there if `make test-e2e` works).
- One-time: `cd radbot/web/frontend && npm install && npx playwright install chromium`.

## Failure triage

When CI's `functional-e2e` fails:
1. Download the artifact bundle from the workflow run (`functional-e2e-failure-<runid>`).
2. Open `playwright-report/index.html` for the rendered run, including video + trace.
3. Check `artifacts/compose-logs.txt` for service-level failures (Postgres init race, Qdrant cold-start, radbot startup).
4. Check `artifacts/health.json` to confirm the stack was healthy at the failure point.
5. Check `artifacts/radbot.log` for application-level errors.
6. For chat-spec failures specifically: look for the attached `judge-verdict-<scenario>.json` — the LLM judge's reasoning is right there.

When the LLM judge produces a flaky verdict:
- Verdict is non-deterministic by design (temp 0.1, not 0).
- If a scenario flakes >2x in a week, tighten the `expect` rubric or split the scenario.
- The judge's `reasoning` field is your debug surface — read it.

## Cost

Each chat scenario = ~1 Haiku judge call (~$0.001). Visual regression = one Anthropic vision call per `@screenshot`-tagged test (~$0.005–0.05). Hard ceiling per CI run: `ANTHROPIC_BUDGET_USD: 2.0`. The judge fixture aborts the suite if exceeded.

## When to add `data-test` attributes

Every React component you write or modify that an e2e spec needs to interact with. Use kebab-case, prefix with the page/feature name. See current seed list in `specs/web.md`.
