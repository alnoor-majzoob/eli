import { expect, test } from "@playwright/test";

test.describe("Phase 0 platform smoke", () => {
  test("dev sign-in, platform status, RTL and sign-out", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);

    await page.getByTestId("role-select").selectOption("project_manager");
    await page.getByTestId("login-submit").click();

    await expect(page.getByTestId("overview-title")).toContainText("Execution overview");
    await expect(page.getByTestId("replay-badge").first()).toBeVisible();
    await expect(page.getByTestId("sim-badge").first()).toBeVisible();

    await page.getByTestId("language-toggle").click();
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    await page.getByTestId("theme-toggle").click();
    await expect(page.locator("html")).toHaveClass(/dark/);

    await page.getByTestId("user-menu-trigger").click();
    await page.getByTestId("logout").click();
    await expect(page).toHaveURL(/\/login$/);
  });
});

test.describe("Phase 1 navigation", () => {
  test("navigate objectives, demand, approvals and audit", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("role-select").selectOption("project_manager");
    await page.getByTestId("login-submit").click();
    await expect(page.getByTestId("overview-title")).toBeVisible();

    await page.getByRole("link", { name: /Objectives & OKRs/ }).click();
    await expect(page.getByRole("heading", { name: "Objectives & OKRs" })).toBeVisible();

    await page.getByRole("link", { name: /Demand pipeline/ }).click();
    await expect(page.getByRole("heading", { name: "Demand pipeline" })).toBeVisible();

    await page.getByRole("link", { name: /Approvals/ }).click();
    await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();

    await page.getByRole("link", { name: /Audit/ }).click();
    await expect(page.getByRole("heading", { name: "Audit" })).toBeVisible();
  });
});
