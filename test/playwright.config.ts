import { defineConfig, devices } from "@playwright/test";

/**
 * The suite runs on the host against the container started by the normal start
 * script. There is no webServer block: global-setup.ts calls the real start
 * script so that the script itself is exercised, and the tests then talk to
 * http://localhost:8000 like a user would.
 *
 * Serial, single worker, on purpose. Every test mutates one shared SQLite
 * database inside one container, so parallel workers would trade against each
 * other's cash balance. Determinism beats wall-clock here.
 */
export default defineConfig({
  testDir: "./specs",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 45_000,
  globalSetup: "./global-setup.ts",
  reporter: [["list"], ["html", { open: "never" }]],
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: process.env.FINALLY_URL ?? "http://localhost:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    actionTimeout: 10_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 1000 } },
    },
  ],
});
