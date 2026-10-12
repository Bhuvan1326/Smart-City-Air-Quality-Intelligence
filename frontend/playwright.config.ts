import { defineConfig } from "@playwright/test";

// Browser walkthrough. Requires a RUNNING frontend + backend and demo users
// created with DEMO_USER_PASSWORD (see README). Services are not started here
// on purpose: run against an isolated test environment, never production.
//   E2E_BASE_URL (default http://localhost:3000), E2E_DEMO_PASSWORD (required)
export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
});
