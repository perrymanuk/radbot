import { defineConfig, devices } from "@playwright/test";
import * as dotenv from "dotenv";
import * as path from "path";

dotenv.config({ path: path.resolve(__dirname, "../../../../.env") });

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:5173";

// CI debug: surface what we resolved before workers fork.
// eslint-disable-next-line no-console
console.error(
  `[playwright.config] BASE_URL=${BASE_URL} (PLAYWRIGHT_BASE_URL=${process.env.PLAYWRIGHT_BASE_URL ?? "<unset>"})`,
);

export default defineConfig({
  testDir: "./specs",
  globalSetup: "./global-setup.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    viewport: { width: 1280, height: 900 },
  },

  projects: [
    {
      name: "anonymous",
      // baseURL repeated explicitly: project-level `use` shadows top-level
      // `use.baseURL` when devices are spread in, causing page.goto("/")
      // to fail with "Cannot navigate to invalid URL".
      use: { ...devices["Desktop Chrome"], baseURL: BASE_URL },
      testMatch: /.*\.spec\.ts/,
      testIgnore: /admin\.spec\.ts/,
    },
    {
      name: "admin-authed",
      use: { ...devices["Desktop Chrome"], baseURL: BASE_URL },
      testMatch: /admin\.spec\.ts/,
    },
  ],
});
