import { expect, test } from "@playwright/test";
import { snap } from "../fixtures/screenshot";

/**
 * Smoke tests for the /projects page. Hits the two unauth'd telos read
 * endpoints (projects/summary + projects/entries) and verifies the shell
 * + left rail + detail pane render. No admin auth needed.
 */
test.describe("projects page", () => {
  test("loads shell with header and filter input @screenshot", async ({ page }) => {
    await page.goto("/projects");

    await expect(page.locator('[data-test="projects-page"]')).toBeVisible();
    await expect(page.locator('[data-test="projects-list"]')).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.locator('[data-test="projects-filter"]')).toBeVisible();

    await snap(page, "projects-shell");
  });

  test("renders detail pane when a project exists or the empty-state copy", async ({ page }) => {
    await page.goto("/projects");

    const listItem = page.locator('[data-test^="projects-list-item-"]').first();
    const count = await listItem.count();

    if (count === 0) {
      // Fresh DB or no active projects — the right pane shows the picker hint.
      await expect(page.getByText(/select a project/i)).toBeVisible({ timeout: 10_000 });
      return;
    }

    // Detail pane should auto-load the first project via the default-select path.
    await expect(page.locator('[data-test="projects-detail"]')).toBeVisible({
      timeout: 10_000,
    });

    // Tab bar with at least Overview should render.
    await expect(page.locator('[data-test="projects-tab-overview"]')).toBeVisible();
  });

  test("keyboard 1-5 cycles tabs when a project is loaded", async ({ page }) => {
    await page.goto("/projects");

    const detail = page.locator('[data-test="projects-detail"]');
    if ((await detail.count()) === 0) {
      test.skip();
    }
    await expect(detail).toBeVisible({ timeout: 10_000 });

    await page.keyboard.press("2");
    await expect(page).toHaveURL(/tab=milestones/);

    await page.keyboard.press("3");
    await expect(page).toHaveURL(/tab=tasks/);

    await page.keyboard.press("1");
    // Overview deletes the tab param
    await expect(page).not.toHaveURL(/tab=/);
  });
});
