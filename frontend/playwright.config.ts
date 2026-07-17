import { defineConfig } from "@playwright/test";

/**
 * Playwright smoke config. Assumes:
 *   - Backend API is running at NIYAM_API_BASE (default http://localhost:8000)
 *   - Frontend dev server is up at http://localhost:3000
 *   - Postgres + Redis are running (via docker-compose up -d postgres redis)
 * The test seeds its own data via API — no dependency on the step-10
 * seed script.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,          // seeds a firm per test; serial keeps assertions simple
  reporter: "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
