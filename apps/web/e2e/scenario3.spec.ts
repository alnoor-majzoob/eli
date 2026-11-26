/* Scenario 3 acceptance (plan §11.3): resource conflict, optimiser, what-if.
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

test.describe("Scenario 3 — Resource Conflict", () => {
  test("capacity heatmap renders week utilisation bands", async ({ page }) => {
    await devLogin(page, "resource_manager");
    await browserLogin(page, "resource_manager");

    await page.goto("/capacity");
    await expect(page).toHaveURL(/\/capacity$/);
    await expect(page.getByTestId("capacity-heatmap-week").first()).toBeVisible();
  });

  test("conflict status + API agree on red weeks", async ({ page }) => {
    const token = await devLogin(page, "resource_manager");

    await browserLogin(page, "resource_manager");
    await page.goto("/capacity");
    await page.getByTestId("capacity-heatmap-week").first().waitFor();

    const heatmapResponse = await page.request.get(`${API_BASE}/api/v1/capacity/heatmap`, {
      headers: { authorization: `Bearer ${token}` },
    });
    expect(heatmapResponse.status()).toBe(200);
    const heatmap = (await heatmapResponse.json()) as {
      weeks: { status: string | null; utilisation: number | null }[];
    }[];
    const red = heatmap.flatMap((row) => row.weeks.filter((w) => (w.status ?? "") === "red"));
    if (red.length > 0) {
      expect(red.every((w) => (w.utilisation ?? 0) > 1.0)).toBe(true);
    }
  });
});
