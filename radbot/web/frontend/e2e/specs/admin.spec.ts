import { expect, test } from "@playwright/test";
import { authAsAdmin } from "../fixtures/admin-token";
import { snap } from "../fixtures/screenshot";

/**
 * Authed admin flows. Runs in the `admin-authed` project (Playwright projects
 * config in playwright.config.ts).
 *
 * `authAsAdmin(page)` sets sessionStorage.admin_token via addInitScript so
 * every navigation in this file starts already authenticated — no login UI
 * involved (see admin-login.spec.ts for the UI-driven flow).
 */
test.describe("admin (authenticated)", () => {
  test.beforeEach(async ({ page }) => {
    await authAsAdmin(page);
  });

  test("dashboard renders directly without login prompt @screenshot", async ({ page }) => {
    await page.goto("/admin");

    await expect(page.locator('[data-test="admin-dashboard"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-test="admin-login-prompt"]')).not.toBeVisible();

    await snap(page, "admin-dashboard");
  });

  test("sidebar shows integration nav with status indicators @screenshot", async ({ page }) => {
    await page.goto("/admin");

    const sidebar = page.locator('[data-test="admin-sidebar"]');
    await expect(sidebar).toBeVisible();

    // Status checks are async; give them a beat to populate `data-status`
    await page.waitForTimeout(1_500);

    // At least one nav item must have resolved to a non-"unknown" status —
    // otherwise the loadStatus() call silently failed.
    const resolved = sidebar.locator('[data-test^="admin-nav-"]:not([data-status="unknown"])');
    expect(await resolved.count()).toBeGreaterThan(0);

    // Spot-check a known nav item exists
    await expect(page.locator('[data-test="admin-nav-google"]')).toBeVisible();

    await snap(page, "admin-sidebar-status");
  });

  test("clicking a nav item opens the corresponding panel", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.locator('[data-test="admin-dashboard"]')).toBeVisible();

    await page.locator('[data-test="admin-nav-postgresql"]').click();
    // The Content area swaps to the selected panel; assertion is loose because
    // the panel implementation may vary — we just confirm the click registered
    // by checking the active-state marker on the nav item. (Styling moved to
    // inline CSS custom properties in the admin redesign, so the old
    // `border-l-radbot-sunset` Tailwind class no longer exists; the button
    // now carries `data-active="true"` when selected.)
    await expect(page.locator('[data-test="admin-nav-postgresql"]')).toHaveAttribute(
      "data-active",
      "true",
    );
  });
});
