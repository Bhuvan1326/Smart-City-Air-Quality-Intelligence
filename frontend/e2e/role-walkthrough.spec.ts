import { expect, test, type Page } from "@playwright/test";

/**
 * Four-role browser walkthrough (Week 2, C1).
 * STATUS: authored but NOT executed in the authoring sandbox (no browser could
 * be installed there). Treat as unverified until it has run in CI/staging.
 * Expectations mirror backend RequireAnalyst/RequireStaff (docs/week-1/rbac-permission-matrix.md).
 */
const PASSWORD = process.env.E2E_DEMO_PASSWORD;
const USERS = {
  admin: "admin@pune.gov.in",
  officer: "officer@mpcb.gov.in",
  inspector: "inspector@pune.gov.in",
  citizen: "citizen@pune.in",
} as const;
type Role = keyof typeof USERS;

test.skip(!PASSWORD, "E2E_DEMO_PASSWORD not set — demo users are required");

async function login(page: Page, role: Role) {
  await page.goto("/login");
  await page.locator("#email").fill(USERS[role]);
  await page.locator("#password").fill(PASSWORD as string);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(/\/dashboard/);
}

// route -> roles allowed to STAY on it (everyone else must be moved away).
const CASES: { path: string; stay: Role[]; leaves: RegExp }[] = [
  { path: "/dashboard/reports", stay: ["admin", "officer"], leaves: /\/dashboard\/reports/ },
  {
    path: "/dashboard/operations?module=enforcement",
    stay: ["admin", "officer", "inspector"],
    leaves: /module=enforcement/,
  },
  {
    path: "/dashboard/intelligence?module=analytics",
    stay: ["admin", "officer"],
    leaves: /module=analytics/,
  },
  {
    path: "/dashboard/intelligence?module=simulator",
    stay: ["admin", "officer"],
    leaves: /module=simulator/,
  },
  { path: "/dashboard/ai?module=agents", stay: ["admin", "officer"], leaves: /module=agents/ },
];

for (const role of Object.keys(USERS) as Role[]) {
  test.describe(`${role}`, () => {
    for (const c of CASES) {
      test(`direct URL ${c.path}`, async ({ page }) => {
        await login(page, role);
        await page.goto(c.path);
        if (c.stay.includes(role)) {
          await expect(page).toHaveURL(c.leaves);
        } else {
          await expect(page).not.toHaveURL(c.leaves);
        }
      });
    }

    test("restricted API calls are rejected server-side (UI bypassed)", async ({
      page,
      request,
    }) => {
      const res = await request.post("/api/backend/auth/login", {
        data: { email: USERS[role], password: PASSWORD },
      });
      expect(res.ok()).toBeTruthy();
      const token = (await res.json()).data.access_token as string;
      const headers = { Authorization: `Bearer ${token}` };
      const analystOnly = await request.get("/api/backend/reports", { headers });
      if (role === "admin" || role === "officer") {
        expect(analystOnly.status()).not.toBe(403);
      } else {
        expect(analystOnly.status()).toBe(403);
      }
      void page;
    });
  });
}

test("a previous user's access does not leak into the next session", async ({ page }) => {
  await login(page, "admin");
  await page.goto("/dashboard/reports");
  await expect(page).toHaveURL(/\/dashboard\/reports/);

  // switch identity in the same browser context
  await page.context().clearCookies();
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await login(page, "citizen");
  await page.goto("/dashboard/reports");
  await expect(page).not.toHaveURL(/\/dashboard\/reports/);
});
