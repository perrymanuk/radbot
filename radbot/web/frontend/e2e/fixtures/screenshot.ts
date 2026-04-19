import { Page, test } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

/**
 * Capture a full-page screenshot at a meaningful checkpoint.
 *
 * Output dir is parameterized via SCREENSHOT_DIR so the same specs can run
 * twice (main vs PR) into different folders for the visual-regression gate.
 *
 * Tag screenshot-emitting tests with @screenshot so the visual-regression job
 * can target the subset:
 *   test('admin status panel renders @screenshot', async ({ page }) => { ... })
 */
export async function snap(page: Page, name: string): Promise<void> {
  const dir = process.env.SCREENSHOT_DIR;
  if (!dir) {
    test.info().annotations.push({
      type: "snap-skipped",
      description: `SCREENSHOT_DIR not set; skipping snap("${name}")`,
    });
    return;
  }

  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(300);
  fs.mkdirSync(dir, { recursive: true });
  await page.screenshot({
    path: path.join(dir, `${name}.png`),
    fullPage: true,
  });
}
