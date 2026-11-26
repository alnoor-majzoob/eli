/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

export interface RadarRow {
  item_id: string;
  title: string;
  type: string;
  status: string;
  confidence: number | null;
  impact: number;
  risk_score: number;
}

export interface EscalationRow {
  id: string;
  work_item_id: string | null;
  root_cause: string;
  impact_cascade: string | null;
  recommended_actions: Record<string, any>[];
  required_decision: string | null;
  target_role: string;
  due_at: string;
  sla_days: number;
  status: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  created_at: string;
}

export async function getRiskRadar(): Promise<RadarRow[]> {
  const { data } = await api.GET("/api/v1/risk/radar" as any, {});
  return (data ?? []) as RadarRow[];
}

export async function listEscalations(): Promise<EscalationRow[]> {
  const { data } = await api.GET("/api/v1/escalations" as any, {});
  return (data ?? []) as EscalationRow[];
}

export async function acknowledgeEscalation(id: string): Promise<void> {
  await api.PATCH(`/api/v1/escalations/${id}/acknowledge` as any, {});
}
