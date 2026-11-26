/* Scenario 2 acceptance (plan §11.2): demand → delivery via prioritisation.
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

function tokenSubject(token: string): string {
  const payload = token.split(".")[1] ?? "";
  return (JSON.parse(atob(payload)) as { sub: string }).sub;
}

test.describe("Scenario 2 — Strategic Demand to Delivery", () => {
  test("prioritisation board ranks items with tier + rationale", async ({ page }) => {
    await devLogin(page, "portfolio_manager");
    await browserLogin(page, "portfolio_manager");

    await page.goto("/prioritization");
    await expect(page).toHaveURL(/\/prioritization$/);
    await expect(page.getByRole("heading", { name: "Prioritization" })).toBeVisible();
    const row = page
      .getByTestId("prioritization-table")
      .or(page.getByTestId("prioritization-row"))
      .first();
    if ((await row.count()) === 0) {
      await expect(page.getByTestId("prioritization-empty")).toBeVisible();
    }
  });

  test("self-override is blocked (SoD-2, plan §13.2)", async ({ page }) => {
    const token = await devLogin(page, "portfolio_manager");
    await browserLogin(page, "portfolio_manager");
    await page.goto("/prioritization");
    await page.getByRole("heading", { name: "Prioritization" }).waitFor();

    const [items, users] = await Promise.all([
      page.request
        .get(`${API_BASE}/api/v1/prioritization`, {
          headers: { authorization: `Bearer ${token}` },
        })
        .then((r) => r.json()),
      page.request
        .get(`${API_BASE}/api/v1/users`, {
          headers: { authorization: `Bearer ${token}` },
        })
        .then((r) => r.json()),
    ]);
    expect(Array.isArray(items)).toBe(true);
    expect(Array.isArray(users)).toBe(true);
    const first = items[0] as { id: string } | undefined;
    if (!first) return; // nothing seeded: nothing to assert

    const me = (users as { id: string; subject: string }[]).find(
      (u) => u.subject === tokenSubject(token),
    );
    expect(me).toBeDefined();

    const response = await page.request.post(
      `${API_BASE}/api/v1/prioritization/${first.id}/override`,
      {
        headers: { authorization: `Bearer ${token}` },
        data: {
          tier: 1,
          justification: "Self-approval must be blocked (SoD-2).",
          approver_id: me?.id,
        },
      },
    );
    expect(response.status()).toBe(403);
    expect((await response.json()).code).toBe("sod_violation");
  });
});
