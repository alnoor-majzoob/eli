/* Scenario 5 acceptance (plan §11.5): the executive view answers the five
 * questions — commitments, priorities, capacity, risks, outcomes, interventions —
 * and the assistant answers free-form questions with resolvable citations while
 * authorisation is respected.
 *
 * Runs against the e2e stack (`pnpm --filter @eil/web e2e`): Playwright
 * WebServer (`scripts/e2e-api.sh` on :8010, vite on :5174).
 */

import type { Page } from "@playwright/test";

import { expect, test } from "@playwright/test";

const API_BASE = "http://127.0.0.1:8010";

interface ExecutiveSummary {
  as_of: string;
  committed: { total: number };
  priorities: { item_id: string; title: string; confidence: number; override: boolean }[];
  capacity_constraints: { resource_id: string; week_start: string; status: string }[];
  at_risk: { item_id: string; title: string; confidence: number }[];
  strategic_outcomes: {
    benefits_total: number;
    objectives: { item_id: string; title: string; confidence: number }[];
  };
  interventions: { id: string; root_cause: string; target_role: string; due_at: string }[];
}

async function devLogin(page: Page, role: string): Promise<string> {
  const response = await page.request.post(`${API_BASE}/api/v1/auth/dev-login`, {
    data: { role },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).access_token as string;
}

async function getJson(page: Page, token: string, path: string) {
  const response = await page.request.get(`${API_BASE}${path}`, {
    headers: { authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(200);
  return response.json();
}

async function browserLogin(page: Page, role: string) {
  await page.goto("/");
  await page.getByTestId("role-select").selectOption(role);
  await page.getByTestId("login-submit").click();
  await page.getByTestId("user-menu-trigger").waitFor();
}

test.describe("Scenario 5 — executive view", () => {
  test("panels match the executive metrics source of truth (§11.5)", async ({ page }) => {
    const token = await devLogin(page, "executive");
    const summary: ExecutiveSummary = await getJson(page, token, "/api/v1/metrics/summary");

    await browserLogin(page, "executive");
    await page.goto("/executive");
    await page.getByTestId("executive-committed").waitFor();

    // 1. What are we committed to?
    await expect(page.getByTestId("executive-committed")).toContainText(
      `Commitments: ${summary.committed.total}`,
    );

    // 2. What is most important? (top priorities with scores + override flags)
    const mostImportant = page.getByTestId("executive-most-important");
    for (const row of summary.priorities.slice(0, 3)) {
      await expect(mostImportant).toContainText(row.title);
      await expect(mostImportant).toContainText(row.confidence.toFixed(2));
      if (row.override) {
        await expect(mostImportant).toContainText("override");
      }
    }

    // 3. Where are resources constrained?
    const constrained = page.getByTestId("executive-constrained");
    for (const row of summary.capacity_constraints.slice(0, 5)) {
      await expect(constrained).toContainText(row.resource_id.slice(0, 8));
      await expect(constrained).toContainText(row.status);
    }

    // 4. What is at risk and why?
    for (const row of summary.at_risk.slice(0, 3)) {
      await expect(page.getByTestId("executive-at-risk")).toContainText(row.title);
    }

    // 5. Which strategic outcomes are affected?
    await expect(page.getByTestId("executive-outcomes")).toContainText(
      `Benefits: ${summary.strategic_outcomes.benefits_total}`,
    );
    for (const row of summary.strategic_outcomes.objectives.slice(0, 3)) {
      await expect(page.getByTestId("executive-outcomes")).toContainText(row.title);
    }

    // 6. Where is intervention required?
    for (const row of summary.interventions.slice(0, 3)) {
      await expect(page.getByTestId("executive-interventions")).toContainText(row.root_cause);
    }
  });

  test("presenter mode: full-screen view with as-of replay (§11.5)", async ({ page }) => {
    const token = await devLogin(page, "executive");

    await browserLogin(page, "executive");
    await page.goto("/executive/presenter");
    await page.getByTestId("presenter-view").waitFor();
    await expect(page.getByTestId("presenter-title")).toBeVisible();
    await expect(page.getByTestId("presenter-as-of-input")).toBeVisible();
    await expect(page.getByTestId("presenter-as-of-value")).toContainText("Viewing as of");
    await expect(page.getByTestId("executive-committed")).toBeVisible();

    // Scrub the timeline to an earlier date: the view replays as of that time.
    const iso = new Date("2026-01-01T00:00").toISOString();
    const past: ExecutiveSummary = await getJson(
      page,
      token,
      `/api/v1/metrics/summary?as_of=${encodeURIComponent(iso)}`,
    );
    await page.getByTestId("presenter-as-of-input").fill("2026-01-01T00:00");
    await expect(page.getByTestId("presenter-as-of-value")).toContainText("Viewing as of");
    await expect(page.getByTestId("executive-committed")).toContainText(
      `Commitments: ${past.committed.total}`,
    );

    // Auto-refresh toggle is present and switches state.
    await expect(page.getByTestId("presenter-auto-refresh")).toContainText("Auto-refresh");
    await page.getByTestId("presenter-auto-refresh").click();
    await expect(page.getByTestId("presenter-auto-refresh")).toContainText("Stop auto-refresh");
  });
});

test.describe("Scenario 5 — Ask EIL (§11.5)", () => {
  test("graceful when AI is disabled; authorisation respected (R12, §13.1)", async ({ page }) => {
    const executiveToken = await devLogin(page, "executive");

    await browserLogin(page, "executive");
    await page.goto("/assistant");
    await expect(page.getByTestId("assistant-empty")).toBeVisible();

    const question =
      "What is threatening the Q2 reliability target, and who needs to decide what this week?";

    // Executive: graceful unavailability while AI is off (R12).
    const ask = await page.request.post(`${API_BASE}/api/v1/assistant/ask`, {
      headers: { authorization: `Bearer ${executiveToken}` },
      data: { question },
    });
    expect(ask.status()).toBe(409);
    expect((await ask.json()).code).toBe("not_available");

    // Integration Admin: no assistant access — nothing is exposed (§13.1).
    const denied = await page.request.post(`${API_BASE}/api/v1/assistant/ask`, {
      headers: { authorization: `Bearer ${await devLogin(page, "integration_admin")}` },
      data: { question },
    });
    expect(denied.status()).toBe(403);
    expect(JSON.stringify(await denied.json())).not.toContain("escalation");
  });
});
