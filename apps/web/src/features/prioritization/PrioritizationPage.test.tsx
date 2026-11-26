import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PrioritizationPage } from "./PrioritizationPage";

const getPrioritization = vi.hoisted(() => vi.fn());
const requestOverride = vi.hoisted(() => vi.fn());
const listUsers = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/prioritization", () => ({
  getPrioritization,
  requestOverride,
}));

vi.mock("@/lib/api/users", () => ({
  listUsers,
}));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ principal: { subject: "demo-portfolio" } }),
}));

const sampleItems = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    type: "demand",
    title: "Flare gas recovery upgrade",
    tier: 1,
    score: 87.5,
    rationale: { strategic_alignment: 5, business_value: 4 },
    model_id: "model-1",
    computed_at: "2026-11-20T10:00:00Z",
    in_cut_line: false,
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    type: "demand",
    title: "Non-critical expansion",
    tier: 4,
    score: 42.25,
    rationale: null,
    model_id: "model-1",
    computed_at: "2026-11-19T09:00:00Z",
    in_cut_line: true,
  },
];

const sampleUsers = [
  {
    id: "u1",
    subject: "demo-portfolio",
    name: "Demo Portfolio",
    email: "demo-portfolio@example.invalid",
    org_unit_id: null,
    roles: ["portfolio_manager"],
  },
  {
    id: "u2",
    subject: "prio-approver",
    name: "Prio Approver",
    email: "prio-approver@eil.test",
    org_unit_id: null,
    roles: ["admin"],
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <PrioritizationPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("prioritization board", () => {
  beforeEach(() => {
    getPrioritization.mockReset().mockResolvedValue(sampleItems);
    requestOverride.mockReset().mockResolvedValue({
      id: "ov1",
      score_id: "s1",
      tier: 2,
      original_tier: 1,
      justification: "Strategic priority raised",
      approver_id: "u1",
      approved_at: "2026-11-22T08:00:00Z",
    });
    listUsers.mockReset().mockResolvedValue(sampleUsers);
  });

  it("lists items ranked with tier, score and rationale breakdown", async () => {
    renderPage();

    const rows = await screen.findAllByTestId("prioritization-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Flare gas recovery upgrade");
    expect(rows[0]).toHaveTextContent("Tier 1");
    expect(rows[0]).toHaveTextContent("strategic_alignment: 5");
    expect(screen.getByText("87.50")).toBeInTheDocument();
    expect(screen.queryByTestId("prioritization-empty")).toBeNull();
  });

  it("marks items below the cut-line", async () => {
    renderPage();

    const rows = await screen.findAllByTestId("prioritization-row");
    expect(rows[1]).toHaveTextContent(/Below cut-line/i);
    expect(rows[1]).toHaveTextContent("Tier 4");
  });

  it("shows the empty state when there are no scored items", async () => {
    getPrioritization.mockResolvedValue([]);
    renderPage();

    expect(await screen.findByTestId("prioritization-empty")).toBeInTheDocument();
  });

  it("shows an error surface when the board cannot be loaded", async () => {
    getPrioritization.mockRejectedValue(new Error("boom"));
    renderPage();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("submits an override through the per-row form", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findAllByTestId("prioritization-row");
    await user.click(
      screen.getByRole("button", { name: /override tier for flare gas recovery upgrade/i }),
    );
    await screen.findByTestId("prioritization-override-form");
    await user.type(screen.getByLabelText("Justification"), "Strategic priority raised");
    await user.click(screen.getByRole("button", { name: /apply override/i }));

    expect(requestOverride).toHaveBeenCalledWith("11111111-1111-1111-1111-111111111111", {
      tier: 2,
      justification: "Strategic priority raised",
      approver_id: "u1",
    });
    expect(await screen.findByText(/override applied/i)).toBeInTheDocument();
    expect(screen.queryByTestId("prioritization-override-form")).toBeNull();
  });
});
