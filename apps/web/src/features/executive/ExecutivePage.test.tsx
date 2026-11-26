import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExecutivePage } from "./ExecutivePage";

const getExecutiveSummary = vi.hoisted(() => vi.fn());
const getBenefitRollup = vi.hoisted(() => vi.fn());
const getRiskRadar = vi.hoisted(() => vi.fn());
const getCapacityHeatmap = vi.hoisted(() => vi.fn());
const listEscalations = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/executive", () => ({ getExecutiveSummary, getBenefitRollup }));
vi.mock("@/lib/api/risk", () => ({ getRiskRadar, listEscalations }));
vi.mock("@/lib/api/capacity", () => ({ getCapacityHeatmap }));

const summary = {
  as_of: new Date().toISOString(),
  committed: {
    total: 3,
    avg_confidence: 0.8,
    by_org_unit: [{ org_unit_id: "u1", count: 3, min_confidence: 0.5 }],
  },
  priorities: [
    { item_id: "p1", title: "Top demand", type: "demand", confidence: 0.9, override: true },
  ],
  capacity_constraints: [
    { resource_id: "r1", week_start: "2026-11-16", utilisation: 1.125, status: "red" },
  ],
  at_risk: [{ item_id: "p1", title: "Top demand", confidence: 0.45 }],
  strategic_outcomes: {
    benefits_total: 2,
    objectives: [{ item_id: "o1", title: "Zero HSSE", confidence: 0.7 }],
  },
  interventions: [
    {
      id: "e1",
      root_cause: "Demand at risk",
      target_role: "dept_head",
      due_at: new Date(Date.now() + 2 * 86400000).toISOString(),
    },
  ],
  users: {},
};

const radar = [
  {
    item_id: "p1",
    title: "Top demand",
    type: "demand",
    status: "active",
    confidence: 0.8,
    impact: 2,
    risk_score: 1.6,
  },
];

const benefitRollup = [
  {
    objective_id: "o1",
    title: "Zero HSSE",
    kr_count: 2,
    benefit_count: 1,
    total_actual: 1.5,
    total_target: 2,
    total_forecast: 2,
    latest_actual_at: "2026-11-01",
    on_track: false,
  },
];

const heatmap = [
  {
    resource_id: "r1",
    resource_name: "Rotating Engineer",
    weeks: [
      { week_start: "2026-11-16", available: 40, demand: 45, utilisation: 1.125, status: "red" },
    ],
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ExecutivePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("executive view", () => {
  beforeEach(() => {
    getExecutiveSummary.mockReset().mockResolvedValue(summary);
    getBenefitRollup.mockReset().mockResolvedValue(benefitRollup);
    getRiskRadar.mockReset().mockResolvedValue(radar);
    getCapacityHeatmap.mockReset().mockResolvedValue(heatmap);
    listEscalations.mockReset().mockResolvedValue(summary.interventions);
  });

  it("renders the five executive panels and the risk radar", async () => {
    renderPage();

    expect(await screen.findByText(/Commitments: 3/)).toBeInTheDocument();
    expect(screen.getAllByText(/Top demand/).length).toBeGreaterThan(0);
    expect(screen.getByText("override")).toBeInTheDocument();
    expect(screen.getAllByText(/Zero HSSE/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Demand at risk/)).toBeInTheDocument();
    expect(screen.getByText(/Benefits: 2/)).toBeInTheDocument();
    expect(screen.getAllByText("red").length).toBeGreaterThan(0);
  });

  it("renders the benefit roll-up panel", async () => {
    renderPage();

    expect(await screen.findByTestId("executive-benefit-rollup")).toBeInTheDocument();
    expect(await screen.findByTestId("executive-benefit-rollup-row")).toBeInTheDocument();
    expect(await screen.findAllByText(/Zero HSSE/)).toHaveLength(2);
  });
});
