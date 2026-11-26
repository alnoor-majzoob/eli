/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

export interface PrioritizedItem {
  id: string;
  type: string;
  title: string;
  tier: number;
  score: number;
  rationale: Record<string, any> | null;
  model_id: string;
  computed_at: string;
  in_cut_line: boolean;
}

export interface OverrideCreate {
  tier: number;
  justification: string;
  approver_id: string;
}

export interface ScoreOverrideRead {
  id: string;
  score_id: string;
  tier: number;
  original_tier: number;
  justification: string;
  approver_id: string | null;
  approved_at: string;
}

export async function getPrioritization(): Promise<PrioritizedItem[]> {
  const { data } = await api.GET("/api/v1/prioritization" as any, {});
  return (data ?? []) as PrioritizedItem[];
}

export async function requestOverride(
  itemId: string,
  payload: OverrideCreate,
): Promise<ScoreOverrideRead> {
  const { data } = await api.POST(`/api/v1/prioritization/${itemId}/override` as any, {
    body: payload,
  });
  return (data ?? null) as ScoreOverrideRead;
}
