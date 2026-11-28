import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CapacityPage } from "./CapacityPage";

const getCapacityHeatmap = vi.hoisted(() => vi.fn());
const getCapacityConflicts = vi.hoisted(() => vi.fn());
const requestOptimiserOptions = vi.hoisted(() => vi.fn());
const listScenarios = vi.hoisted(() => vi.fn());
const createScenario = vi.hoisted(() => vi.fn());
const promoteScenario = vi.hoisted(() => vi.fn());
const listUsers = vi.hoisted(() => vi.fn());
const getAllocations = vi.hoisted(() => vi.fn());
const createAllocation = vi.hoisted(() => vi.fn());
const updateAllocation = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/capacity", () => ({
  getCapacityHeatmap,
  getCapacityConflicts,
  requestOptimiserOptions,
  listScenarios,
  createScenario,
  promoteScenario,
  getAllocations,
  createAllocation,
  updateAllocation,
}));
vi.mock("@/lib/permissions", () => {
  const actual = { PERMISSIONS: {}, EMPTY_PERMISSIONS: {} };
  return {
    ...actual,
    usePermissions: () => ({
      permissions: { roles: ["admin"], org_unit_id: null, is_admin: true, permissions: {} },
      isLoading: false,
      can: () => true,
      hasRole: () => true,
      isAdmin: true,
      scope: () => "global",
    }),
  };
});

vi.mock("@/lib/api/users", () => ({
  listUsers,
}));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({ principal: { subject: "demo-portfolio" } }),
}));

const heatmap = [
  {
    resource_id: "r1",
    resource_name: "Rotating Equipment Engineer",
    weeks: [
      { week_start: "2026-11-16", available: 40, demand: 45, utilisation: 1.125, status: "red" },
    ],
  },
];

const conflicts = [
  {
    resource_id: "r1",
    week_start: "2026-11-16",
    utilisation: 1.125,
    status: "red",
    affected: [
      {
        id: "c1",
        type: "commitment",
        title: "Reliability commitment",
        depth: 1,
        criticality: 1.125,
      },
    ],
  },
];

const options = [
  {
    strategy: "reassign",
    option_index: 1,
    allocations: [{ task_id: "t1", resource_id: "r2", week_start: "2026-11-16", hours: 25 }],
    deltas: {
      unmet_hours: 0,
      overload_hours: 0,
      reassignment_hours: 25,
      skill_gap_hours: 0,
      delayed_commitments: 0,
    },
  },
];

const scenarios = [
  {
    id: "s1",
    name: "What-if A",
    description: null,
    author_id: "u1",
    promoted: false,
    approved_by_id: null,
    promoted_at: null,
    expires_at: null,
    expired: false,
    created_at: "2026-11-20T10:00:00Z",
  },
];

const users = [
  {
    id: "u1",
    subject: "demo-portfolio",
    name: "Demo Portfolio",
    email: "a@eil.test",
    org_unit_id: null,
    roles: ["portfolio_manager"],
  },
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <CapacityPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("capacity page", () => {
  beforeEach(() => {
    getCapacityHeatmap.mockReset().mockResolvedValue(heatmap);
    getCapacityConflicts.mockReset().mockResolvedValue(conflicts);
    requestOptimiserOptions.mockReset().mockResolvedValue(options);
    listScenarios.mockReset().mockResolvedValue(scenarios);
    createScenario.mockReset().mockResolvedValue(scenarios[0]);
    promoteScenario.mockReset().mockResolvedValue({ ...scenarios[0], promoted: true });
    listUsers.mockReset().mockResolvedValue(users);
    getAllocations.mockReset().mockResolvedValue([]);
    createAllocation.mockReset().mockResolvedValue({ id: "a1" });
    updateAllocation.mockReset().mockResolvedValue({ id: "a1" });
  });

  it("renders the heatmap, conflicts and optimiser options", async () => {
    renderPage();

    expect(await screen.findAllByTestId("capacity-heatmap-week")).toHaveLength(1);
    expect(screen.getByText("Rotating Equipment Engineer")).toBeInTheDocument();
    expect(await screen.findByText(/Reliability commitment/)).toBeInTheDocument();
    expect(await screen.findByText(/reassign — option 1/)).toBeInTheDocument();
    expect(screen.getByText(/reassign 25\.00h/)).toBeInTheDocument();
  });

  it("creates an allocation from the form", async () => {
    const user = userEvent.setup();
    renderPage();

    const select = await screen.findByRole("combobox", { name: /resource/i });
    await screen.findByRole("option", { name: /Demo Portfolio/ });
    await user.selectOptions(select, "u1");
    await user.type(screen.getByLabelText(/work item/i), "WO-1");
    fireEvent.change(screen.getByLabelText(/start date/i), { target: { value: "2026-12-01" } });
    fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: "2026-12-07" } });
    await user.type(screen.getByLabelText(/hours per week/i), "40");
    await user.click(screen.getByRole("button", { name: /add allocation/i }));

    await waitFor(() => expect(createAllocation).toHaveBeenCalled());
    expect(createAllocation).toHaveBeenCalledWith({
      resource_id: "u1",
      work_item_id: "WO-1",
      kind: "operational",
      start_date: "2026-12-01",
      end_date: "2026-12-07",
      hours_per_week: 40,
    });
  });

  it("creates a scenario and promotes it with the current user as approver", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("What-if A");
    await user.click(screen.getByRole("button", { name: /^promote$/i }));
    expect(promoteScenario).toHaveBeenCalledWith("s1", "u1");
  });
});
