import { Page } from "@playwright/test";

/**
 * Returns the admin bearer token from the env. Loaded into the process by
 * dotenv in playwright.config.ts (reads ../../../.env at the repo root).
 */
export function getAdminToken(): string {
  const t = process.env.RADBOT_ADMIN_TOKEN;
  if (!t) {
    throw new Error(
      "RADBOT_ADMIN_TOKEN not set. Locally: add it to .env at repo root. CI: provided by bootstrap-radbot-stack composite action.",
    );
  }
  return t;
}

/**
 * Inject the admin token into sessionStorage before any page script runs.
 *
 * radbot's admin store reads `sessionStorage.getItem('admin_token')` on init
 * (see src/stores/admin-store.ts), and Playwright's `storageState` does NOT
 * capture sessionStorage — so we set it via `addInitScript` per page instead.
 *
 * Call this in `beforeEach` for any spec that needs to start authenticated.
 */
export async function authAsAdmin(page: Page): Promise<void> {
  const token = getAdminToken();
  await page.addInitScript((t) => {
    sessionStorage.setItem("admin_token", t);
  }, token);
}
