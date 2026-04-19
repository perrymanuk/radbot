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
 * Lives in the `anonymous` project — no admin auth needed for /.
 */
// SKIP: Gemini returns empty content for these prompts in CI (radbot.log
// shows "NO TEXT RESPONSE found in 0 events ... model returned empty content
// which will poison the session history"). Tracking + debug plan in
// https://github.com/perrymanuk/radbot/issues/38
// Remove this skip + fix root cause once that issue is resolved.
test.describe.skip("chat scenarios (skipped — see #38)", () => {
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
