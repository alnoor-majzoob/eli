import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RiskPage } from "./RiskPage";

const getRiskRadar = vi.hoisted(() => vi.fn());
const listEscalations = vi.hoisted(() => vi.fn());
const acknowledgeEscalation = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/risk", () => ({
  getRiskRadar,
  listEscalations,
  acknowledgeEscalation,
}));

const radarRows = [
  {
    item_id: "i1",
    title: "Big project",
    type: "project",
    status: "active",
    confidence: 0.8,
    impact: 2,
    risk_score: 1.6,
  },
];

const escalations = [
  {
    id: "e1",
    work_item_id: "i1",
    root_cause: "Delivery confidence below 0.5.",
    impact_cascade: null,
    recommended_actions: [],
    required_decision: "mitigation",
    target_role: "dept_head",
    due_at: new Date(Date.now() + 5 * 86400000).toISOString(),
    sla_days: 2,
    status: "open",
    acknowledged_by: null,
    acknowledged_at: null,
    created_at: new Date().toISOString(),
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <RiskPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("risk page", () => {
  beforeEach(() => {
    getRiskRadar.mockReset().mockResolvedValue(radarRows);
    listEscalations.mockReset().mockResolvedValue(escalations);
    acknowledgeEscalation.mockReset().mockResolvedValue(undefined);
  });

  it("renders the radar and escalations with acknowledge actions", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findAllByTestId("risk-radar-row")).toHaveLength(1);
    expect(screen.getByText("Big project")).toBeInTheDocument();
    expect(screen.getByTestId("risk-score")).toHaveTextContent("1.60");

    expect(await screen.findByTestId("risk-escalation")).toHaveTextContent(
      /Delivery confidence below 0\.5\./,
    );
    await user.click(screen.getByRole("button", { name: /acknowledge/i }));
    expect(acknowledgeEscalation).toHaveBeenCalledWith("e1");
  });

  it("shows the empty state without escalations", async () => {
    listEscalations.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByTestId("risk-no-rows")).toBeInTheDocument();
  });
});
