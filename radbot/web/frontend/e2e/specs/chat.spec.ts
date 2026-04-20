import { expect, test } from "@playwright/test";
import { detectTransportError, judgeResponse } from "../fixtures/llm-judge";
import { snap } from "../fixtures/screenshot";
import { awaitAssistantMessage, sendChatMessage } from "../fixtures/ws-helpers";
import { chatScenarios } from "./chat-scenarios";

/**
 * Chat-with-beto golden-path tests. Each scenario sends a prompt, captures
 * beto's response from the WebSocket-backed UI, and grades it via the LLM
 * judge (Anthropic Haiku). A passing chat spec means the response was graded
 * AND scored >= 7 in category "correct".
 *
 * Each scenario owns its own session UUID (created via POST
 * /api/sessions/create in beforeEach, deleted via DELETE in afterEach) so
 * parallel workers never collide on a shared session. The UI is steered to
 * that session by intercepting GET /api/sessions/ with a single-entry list —
 * initSession() then picks it up as sessions[0]. No backend changes.
 *
 * Lives in the `anonymous` project — no admin auth needed for /.
 */
// SKIP: Gemini returns empty content for these prompts in CI (radbot.log
// shows "NO TEXT RESPONSE found in 0 events ... model returned empty content
// which will poison the session history"). Tracking + debug plan in
// https://github.com/perrymanuk/radbot/issues/38
// Remove this skip + fix root cause once that issue is resolved.
test.describe.skip("chat scenarios (skipped — see #38)", () => {
  // Per-test session lives on the testInfo annotations so afterEach can find it.
  const SESSION_ANNOTATION = "e2e-session-id";

  test.beforeEach(async ({ page, request }, testInfo) => {
    const sessionId = crypto.randomUUID();
    const name = `e2e-chat-${testInfo.title.slice(0, 40)}`;

    const res = await request.post("/api/sessions/create", {
      data: { session_id: sessionId, name, agent_name: "beto" },
    });
    expect(res.ok(), `create session failed: ${res.status()}`).toBe(true);

    testInfo.annotations.push({ type: SESSION_ANNOTATION, description: sessionId });

    // Steer the UI to our isolated session: intercept the list endpoint and
    // return only our session as the first (and only) entry. initSession()
    // picks sessions[0], so this is sufficient without app changes.
    const nowIso = new Date().toISOString();
    await page.route("**/api/sessions/", async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          sessions: [
            {
              id: sessionId,
              name,
              description: null,
              created_at: nowIso,
              last_message_at: null,
              preview: "e2e isolated session",
              agent_name: "beto",
            },
          ],
          active_session_id: sessionId,
        }),
      });
    });
  });

  test.afterEach(async ({ request }, testInfo) => {
    const ann = testInfo.annotations.find((a) => a.type === SESSION_ANNOTATION);
    const sessionId = ann?.description;
    if (!sessionId) return;

    // DELETE, not /reset — /reset throws 404 when the in-memory runner has
    // been evicted (see EX25 constraints).
    const res = await request.delete(`/api/sessions/${sessionId}`);
    if (!res.ok() && res.status() !== 404) {
      // Log but don't fail teardown — the test's own assertions matter more.
      // eslint-disable-next-line no-console
      console.warn(
        `[chat.spec] cleanup DELETE /api/sessions/${sessionId} returned ${res.status()}`,
      );
    }
  });

  for (const scenario of chatScenarios) {
    test(`chat: ${scenario.name} @screenshot`, async ({ page }, testInfo) => {
      test.setTimeout((scenario.timeoutMs ?? 30_000) + 30_000);

      await page.goto("/");
      await sendChatMessage(page, scenario.prompt);

      const response = await awaitAssistantMessage(page, {
        timeoutMs: scenario.timeoutMs ?? 30_000,
        quietMs: 1_000,
      });

      await snap(page, `chat-${scenario.name}`);

      // Fast structural fail-out before paying for a judge call
      const transportError = detectTransportError(response);
      if (transportError) {
        testInfo.attach(`judge-verdict-${scenario.name}.json`, {
          contentType: "application/json",
          body: JSON.stringify(transportError, null, 2),
        });
        throw new Error(
          `Transport error in scenario "${scenario.name}": ${transportError.reasoning}`,
        );
      }

      const verdict = await judgeResponse({
        prompt: scenario.prompt,
        response,
        expect: scenario.expect,
      });

      testInfo.attach(`judge-verdict-${scenario.name}.json`, {
        contentType: "application/json",
        body: JSON.stringify({ scenario: scenario.name, response, verdict }, null, 2),
      });

      expect(
        verdict.passed,
        `Judge verdict: category=${verdict.category} score=${verdict.score} — ${verdict.reasoning}`,
      ).toBe(true);
      expect(verdict.score).toBeGreaterThanOrEqual(7);
    });
  }
});
