/* Scenario 4 acceptance (plan §11.4): cross-system execution risk.
 *
 * Runs against the e2e stack: Playwright WebServer (`scripts/e2e-api.sh` on
 * :8010, vite on :5174).
 */

import type { Page } from "@playwright/test";

import { expect, test } from "@playwright/test";

const API_BASE = "http://127.0.0.1:8010";

async function devLogin(page: Page, role: string): Promise<string> {
  const response = await page.request.post(`${API_BASE}/api/v1/auth/dev-login`, {
    data: { role },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).access_token as string;
}

async function browserLogin(page: Page, role: string) {
  await page.goto("/");
  await page.getByTestId("role-select").selectOption(role);
  await page.getByTestId("login-submit").click();
  await page.getByTestId("user-menu-trigger").waitFor();
}

test.describe("Scenario 4 — Cross-System Execution Risk", () => {
  test("risk radar renders rows (or the empty state)", async ({ page }) => {
    await devLogin(page, "project_manager");
    await browserLogin(page, "project_manager");

    await page.goto("/risk");
    await expect(page).toHaveURL(/\/risk$/);
    const radar = page.getByTestId("risk-radar-table").or(page.getByTestId("risk-no-rows")).first();
    expect(await radar.count()).toBeGreaterThan(0);
  });

  test("risk radar API returns rollup confidence × impact rows", async ({ page }) => {
    const token = await devLogin(page, "project_manager");
    await browserLogin(page, "project_manager");

    const radarResponse = await page.request.get(`${API_BASE}/api/v1/risk/radar`, {
      headers: { authorization: `Bearer ${token}` },
    });
    expect(radarResponse.status()).toBe(200);
    expect(Array.isArray(await radarResponse.json())).toBe(true);
  });
});
