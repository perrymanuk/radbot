import { FullConfig } from "@playwright/test";

/**
 * Pre-flight: validate that RADBOT_ADMIN_TOKEN reaches the target stack
 * BEFORE spinning up workers. Catches "wrong token in .env" and "stack not
 * up" failures with one clear error instead of N flaky-looking spec failures.
 *
 * We do NOT save storageState here — radbot's admin store uses sessionStorage
 * (per-tab, not captured by Playwright's storageState). Authed specs use
 * fixtures/admin-token.ts `authAsAdmin(page)` which seeds sessionStorage via
 * addInitScript before each navigation.
 */
export default async function globalSetup(_config: FullConfig): Promise<void> {
  const baseUrl = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:5173";
  const token = process.env.RADBOT_ADMIN_TOKEN;

  if (!token) {
    throw new Error(
      "[global-setup] RADBOT_ADMIN_TOKEN is not set. " +
        "Locally: add it to .env at repo root. CI: set as a GH secret consumed by bootstrap-radbot-stack.",
    );
  }

  // Use the admin API to validate. /admin/api/credentials returns 200 + JSON
  // when authenticated, 401/403 otherwise.
  const url = `${baseUrl.replace(/\/$/, "")}/admin/api/credentials`;
  let resp: Response;
  try {
    resp = await fetch(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch (e) {
    throw new Error(
      `[global-setup] failed to reach ${url} (${(e as Error).message}). ` +
        `Is the radbot stack up at ${baseUrl}? Try \`make test-e2e-up\` or \`make run-web-custom\`.`,
    );
  }

  if (resp.status === 401 || resp.status === 403) {
    throw new Error(
      `[global-setup] admin token rejected by ${url} (HTTP ${resp.status}). ` +
        `Check RADBOT_ADMIN_TOKEN matches the stack's configured token.`,
    );
  }
  if (!resp.ok) {
    throw new Error(`[global-setup] unexpected status ${resp.status} from ${url}`);
  }

  // Pre-flight Anthropic key too — the chat spec will fail without it
  if (!process.env.ANTHROPIC_API_KEY) {
    throw new Error(
      "[global-setup] ANTHROPIC_API_KEY is not set; chat-quality grading cannot run. " +
        "Locally: export it. CI: set as a GH secret.",
    );
  }

  process.stderr.write(
    `[global-setup] OK — ${baseUrl} reachable, admin token valid, ANTHROPIC_API_KEY present.\n`,
  );
}
