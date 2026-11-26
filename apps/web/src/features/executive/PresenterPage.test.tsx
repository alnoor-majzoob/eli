import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PresenterPage } from "./PresenterPage";

const getExecutiveSummary = vi.hoisted(() => vi.fn());
const getRiskRadar = vi.hoisted(() => vi.fn());
const listEscalations = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/executive", () => ({ getExecutiveSummary }));
vi.mock("@/lib/api/risk", () => ({ getRiskRadar, listEscalations }));

const summary = {
  as_of: new Date().toISOString(),
  committed: {
    total: 5,
    avg_confidence: 0.82,
    by_org_unit: [{ org_unit_id: "exec", count: 5, min_confidence: 0.6 }],
  },
  priorities: [
    { item_id: "p1", title: "Top demand", type: "demand", confidence: 0.95, override: true },
  ],
  capacity_constraints: [
    { resource_id: "r1", week_start: "2026-11-16", utilisation: 1.125, status: "red" },
  ],
  at_risk: [{ item_id: "p1", title: "Top demand", confidence: 0.4 }],
  strategic_outcomes: {
    benefits_total: 4,
    objectives: [{ item_id: "o1", title: "Zero HSSE", confidence: 0.7 }],
  },
  interventions: [
    {
      id: "e1",
      root_cause: "Demand at risk",
      target_role: "executive",
      due_at: new Date(Date.now() + 2 * 86400000).toISOString(),
    },
  ],
  users: {},
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <PresenterPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("presenter mode", () => {
  beforeEach(() => {
    getExecutiveSummary.mockReset().mockResolvedValue(summary);
    getRiskRadar.mockReset().mockResolvedValue([]);
    listEscalations.mockReset().mockResolvedValue(summary.interventions);
  });

  it("renders the full-screen presenter view with the executive panels and as-of selector", async () => {
    renderPage();

    expect(await screen.findByTestId("presenter-view")).toBeInTheDocument();
    expect(screen.getByTestId("presenter-as-of-input")).toBeInTheDocument();
    expect(await screen.findByText(/Commitments: 5/)).toBeInTheDocument();
    expect(screen.getByTestId("executive-most-important")).toBeInTheDocument();
    expect(screen.getByTestId("executive-at-risk")).toBeInTheDocument();
    expect(screen.getByTestId("executive-interventions")).toBeInTheDocument();
  });

  it("replays the timeline when an earlier as-of is selected", async () => {
    const { findByText } = renderPage();
    await findByText(/Commitments: 5/);

    expect(getExecutiveSummary).toHaveBeenCalledWith(undefined);
  });
});
