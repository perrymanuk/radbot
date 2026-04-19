import { expect, test } from "@playwright/test";
import { getAdminToken } from "../fixtures/admin-token";
import { snap } from "../fixtures/screenshot";

/**
 * Drives the real admin login UI end-to-end. This is the only spec that
 * exercises the login flow — every other admin spec uses sessionStorage
 * injection (see fixtures/admin-token.ts authAsAdmin) so login-UI changes
 * only break this one file.
 *
 * Lives in the `anonymous` project (no admin auth pre-applied).
 */
test.describe("admin login", () => {
  test.beforeEach(async ({ page }) => {
    // Belt-and-suspenders: clear any prior auth in case test isolation breaks
    await page.goto("/");
    await page.evaluate(() => {
      try {
        sessionStorage.removeItem("admin_token");
      } catch {
        /* ignore */
      }
    });
  });

  test("rejects an invalid token and stays on login form @screenshot", async ({ page }) => {
    await page.goto("/admin");

    const prompt = page.locator('[data-test="admin-login-prompt"]');
    await expect(prompt).toBeVisible();

    await page.locator('[data-test="admin-token-input"]').fill("definitely-not-the-real-token");
    await page.locator('[data-test="admin-token-submit"]').click();

    // Login prompt must still be visible (no dashboard render)
    await expect(prompt).toBeVisible({ timeout: 5_000 });
    await expect(page.locator('[data-test="admin-dashboard"]')).not.toBeVisible();

    await snap(page, "admin-login-rejected");
  });

  test("accepts the real token and renders the dashboard @screenshot", async ({ page }) => {
    const token = getAdminToken();

    await page.goto("/admin");
    await expect(page.locator('[data-test="admin-login-prompt"]')).toBeVisible();

    await page.locator('[data-test="admin-token-input"]').fill(token);
    await page.locator('[data-test="admin-token-submit"]').click();

    await expect(page.locator('[data-test="admin-dashboard"]')).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-test="admin-login-prompt"]')).not.toBeVisible();
    await expect(page.locator('[data-test="admin-sidebar"]')).toBeVisible();

    await snap(page, "admin-login-success");
  });
});
