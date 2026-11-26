/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

export interface ExecutiveSummary {
  as_of: string;
  committed: {
    total: number;
    avg_confidence: number | null;
    by_org_unit: { org_unit_id: string | null; count: number; min_confidence: number | null }[];
  };
  priorities: {
    item_id: string;
    title: string;
    type: string;
    confidence: number;
    override: boolean;
  }[];
  capacity_constraints: {
    resource_id: string;
    week_start: string;
    utilisation: number;
    status: string;
  }[];
  at_risk: { item_id: string; title: string; confidence: number }[];
  strategic_outcomes: {
    benefits_total: number;
    objectives: { item_id: string; title: string; confidence: number }[];
  };
  interventions: { id: string; root_cause: string; target_role: string; due_at: string }[];
  users: Record<string, string>;
}

export interface BenefitRollupRow {
  objective_id: string;
  title: string;
  kr_count: number;
  benefit_count: number;
  total_actual: number | null;
  total_target: number | null;
  total_forecast: number | null;
  latest_actual_at: string | null;
  on_track: boolean;
}

export async function getExecutiveSummary(asOf?: string): Promise<ExecutiveSummary> {
  const { data } = await api.GET("/api/v1/metrics/summary" as any, {
    params: asOf ? ({ query: { as_of: asOf } } as any) : {},
  });
  return (data ?? null) as ExecutiveSummary;
}

export async function getBenefitRollup(): Promise<BenefitRollupRow[]> {
  const { data } = await api.GET("/api/v1/items/benefit-rollup" as any, {});
  return (data ?? []) as BenefitRollupRow[];
}
