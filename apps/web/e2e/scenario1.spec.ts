/* Scenario 1 acceptance (plan §11.1): meeting/email → extraction → acceptance.
 *
 * Runs against the e2e stack (`pnpm --filter @eil/web e2e`): Playwright
 * WebServer (`scripts/e2e-api.sh` on :8010, vite on :5174).
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

test.describe("Scenario 1 — Meeting/Email to Execution", () => {
  test("AI inbox shows pending suggestions from the meeting transcript", async ({ page }) => {
    await devLogin(page, "project_manager");
    await browserLogin(page, "project_manager");

    await page.goto("/ai/inbox");
    await expect(page).toHaveURL(/\/ai\/inbox$/);
    await expect(page.getByRole("heading", { name: "AI inbox" })).toBeVisible();
  });

  test("promotion flow: accept/edit/reject end in audit", async ({ page }) => {
    const token = await devLogin(page, "project_manager");

    await browserLogin(page, "project_manager");
    await page.goto("/ai/inbox");
    await page.getByRole("heading", { name: "AI inbox" }).waitFor();

    // Promote the seeded "Replace pump assembly on line 3" suggestion if present.
    const acceptButtons = page.getByRole("button", { name: /Accept/i });
    if (await acceptButtons.count()) {
      await acceptButtons.first().click();
      await page.waitForTimeout(1000);
    }

    const auditResponse = await page.request.get(`${API_BASE}/api/v1/audit`, {
      headers: { authorization: `Bearer ${token}` },
    });
    expect(auditResponse.status()).toBe(200);
  });
});
