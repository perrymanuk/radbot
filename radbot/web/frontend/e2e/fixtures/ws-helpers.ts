import { Locator, Page, expect } from "@playwright/test";

/**
 * Wait for the next assistant message bubble to appear and then settle.
 *
 * "Settle" = no DOM mutations on the bubble for `quietMs` ms in a row, which
 * is our proxy for "streaming complete". Returns the rendered text.
 *
 * Assumes the chat UI marks assistant message containers with
 * `data-test="message-assistant"`. Add that attribute to the relevant
 * MessageBubble component in src/components/chat/.
 */
export async function awaitAssistantMessage(
  page: Page,
  opts: { timeoutMs?: number; quietMs?: number } = {},
): Promise<string> {
  const timeoutMs = opts.timeoutMs ?? 30_000;
  const quietMs = opts.quietMs ?? 1_000;
  const deadline = Date.now() + timeoutMs;

  const bubble = page.locator('[data-test="message-assistant"]').last();
  await bubble.waitFor({ state: "visible", timeout: timeoutMs });

  let lastText = await bubble.innerText();
  let lastChange = Date.now();

  while (Date.now() < deadline) {
    await page.waitForTimeout(200);
    const text = await bubble.innerText();
    if (text !== lastText) {
      lastText = text;
      lastChange = Date.now();
    } else if (Date.now() - lastChange >= quietMs) {
      return text;
    }
  }

  // One last read so callers always get the latest content even on timeout
  return await bubble.innerText();
}

/**
 * Type into the chat composer and submit. Composer must carry data-test
 * attributes "chat-input" (the textarea) and "chat-send" (the submit button).
 */
export async function sendChatMessage(page: Page, prompt: string): Promise<void> {
  const input = page.locator('[data-test="chat-input"]');
  await expect(input).toBeVisible();
  await input.fill(prompt);
  await page.locator('[data-test="chat-send"]').click();
}

/** Locator for the most recent assistant bubble. */
export function lastAssistantBubble(page: Page): Locator {
  return page.locator('[data-test="message-assistant"]').last();
}
