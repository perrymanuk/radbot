import { expect, test } from "@playwright/test";
import { snap } from "../fixtures/screenshot";

/**
 * Terminal page mount-only assertions.
 *
 * This spec is deliberately narrow: it verifies the /terminal route mounts
 * and renders its shell (header + page wrapper). It does NOT exercise PTY /
 * Nomad worker interactions — Nomad is not bootstrapped in the CI frontend
 * job, and the backend terminal endpoints depend on a worker runtime that
 * isn't available there. See EX25 "Terminal Constraints".
 *
 * Lives in the `anonymous` project — no admin auth needed.
 */
test.describe("terminal page", () => {
  test("mounts with header and page shell @screenshot", async ({ page }) => {
    await page.goto("/terminal");

    await expect(page.locator('[data-test="terminal-page"]')).toBeVisible();
    await expect(page.locator('[data-test="terminal-header"]')).toBeVisible();

    // The "Terminal" title lives in the header; assert it to catch the case
    // where the route renders the fallback ChatPage instead.
    await expect(
      page.locator('[data-test="terminal-header"]').getByRole("heading", {
        level: 1,
        name: /terminal/i,
      }),
    ).toBeVisible();

    await snap(page, "terminal-mount");
  });
});
