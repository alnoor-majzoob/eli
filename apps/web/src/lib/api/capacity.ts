/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

export interface HeatmapWeek {
  week_start: string;
  available: number;
  demand: number;
  utilisation: number | null;
  status: string | null;
}

export interface HeatmapResource {
  resource_id: string;
  resource_name: string;
  weeks: HeatmapWeek[];
}

export interface ConflictAffected {
  id: string;
  type: string;
  title: string;
  depth: number;
  criticality: number;
}

export interface CapacityConflict {
  resource_id: string;
  week_start: string;
  utilisation: number;
  status: string;
  affected: ConflictAffected[];
}

export interface OptimiserAllocation {
  task_id: string;
  resource_id: string;
  week_start: string;
  hours: number;
}

export interface OptimiserDeltas {
  unmet_hours: number;
  overload_hours: number;
  reassignment_hours: number;
  skill_gap_hours: number;
  delayed_commitments: number;
}

export interface OptimiserOption {
  strategy: string;
  option_index: number;
  allocations: OptimiserAllocation[];
  deltas: OptimiserDeltas;
}

export interface Scenario {
  id: string;
  name: string;
  description: string | null;
  author_id: string;
  promoted: boolean;
  approved_by_id: string | null;
  promoted_at: string | null;
  expires_at: string | null;
  expired: boolean;
  created_at: string;
}

export interface ScenarioMetrics {
  scenario_id: string;
  overload_hours: number;
  red_weeks: number;
  delayed_commitments: number;
  cost_proxy: number;
}

export interface Allocation {
  id: string;
  resource_id: string;
  work_item_id: string | null;
  kind: string;
  start_date: string;
  end_date: string;
  hours_total: number | null;
  hours_per_week: number | null;
  locked: boolean;
  scenario_id: string | null;
}

export interface AllocationCreate {
  resource_id: string;
  work_item_id?: string | null;
  kind: string;
  start_date: string;
  end_date: string;
  hours_total?: number | null;
  hours_per_week?: number | null;
}

export async function getCapacityHeatmap(): Promise<HeatmapResource[]> {
  const { data } = await api.GET("/api/v1/capacity/heatmap" as any, {});
  return ((data as any)?.resources ?? []) as HeatmapResource[];
}

export async function getCapacityConflicts(): Promise<CapacityConflict[]> {
  const { data } = await api.GET("/api/v1/capacity/conflicts" as any, {});
  return (data ?? []) as CapacityConflict[];
}

export async function requestOptimiserOptions(): Promise<OptimiserOption[]> {
  const { data } = await api.POST("/api/v1/capacity/optimise" as any, {});
  return (data ?? []) as OptimiserOption[];
}

export async function listScenarios(): Promise<Scenario[]> {
  const { data } = await api.GET("/api/v1/scenarios" as any, {});
  return (data ?? []) as Scenario[];
}

export async function createScenario(name: string): Promise<Scenario> {
  const { data } = await api.POST("/api/v1/scenarios" as any, { body: { name } });
  return (data ?? null) as Scenario;
}

export async function promoteScenario(id: string, approverId: string): Promise<Scenario> {
  const { data } = await api.POST(`/api/v1/scenarios/${id}/promote` as any, {
    body: { approver_id: approverId },
  });
  return (data ?? null) as Scenario;
}

export async function getScenarioMetrics(id: string): Promise<ScenarioMetrics> {
  const { data } = await api.GET(`/api/v1/scenarios/${id}/metrics` as any, {});
  return (data ?? null) as ScenarioMetrics;
}

export async function getAllocations(): Promise<Allocation[]> {
  const { data } = await api.GET("/api/v1/allocations" as any, {});
  return (data ?? []) as Allocation[];
}

export async function createAllocation(payload: AllocationCreate): Promise<Allocation> {
  const { data } = await api.POST("/api/v1/allocations" as any, { body: payload });
  return (data ?? null) as Allocation;
}

export async function updateAllocation(
  id: string,
  payload: Partial<AllocationCreate>,
): Promise<Allocation> {
  const { data } = await api.PATCH(`/api/v1/allocations/${id}` as any, { body: payload });
  return (data ?? null) as Allocation;
}
