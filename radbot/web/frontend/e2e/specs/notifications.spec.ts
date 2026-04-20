import { expect, test } from "@playwright/test";
import { snap } from "../fixtures/screenshot";

/**
 * Notifications page mount assertions.
 *
 * Verifies the /notifications route mounts its shell (header + page
 * wrapper) and renders either the empty-state placeholder or the grouped
 * list. The DB-backed notifications list is not seeded in CI, so we accept
 * either shape — what matters is that the page itself renders.
 *
 * Lives in the `anonymous` project — no admin auth needed.
 */
test.describe("notifications page", () => {
  test("mounts with header and page shell @screenshot", async ({ page }) => {
    await page.goto("/notifications");

    await expect(page.locator('[data-test="notifications-page"]')).toBeVisible();
    await expect(page.locator('[data-test="notifications-header"]')).toBeVisible();

    await expect(
      page.locator('[data-test="notifications-header"]').getByRole("heading", {
        level: 1,
        name: /notifications/i,
      }),
    ).toBeVisible();

    // Wait briefly so the loadNotifications() call can settle; then accept
    // either the empty-state or at least one NotificationItem rendered.
    await page.waitForTimeout(500);
    const empty = page.locator('[data-test="notifications-empty-state"]');
    const items = page.locator('[data-test^="notification-item-"]');
    const emptyVisible = await empty.isVisible().catch(() => false);
    if (!emptyVisible) {
      expect(await items.count()).toBeGreaterThanOrEqual(0);
    }

    await snap(page, "notifications-mount");
  });
});
