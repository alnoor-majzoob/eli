/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

export interface AiSuggestion {
  id: string;
  kind: string;
  status: string;
  payload: Record<string, any>;
  evidence: Record<string, any> | null;
  confidence: number | null;
  model: string;
  prompt_version: string;
  llm_call_id: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_reason: string | null;
  resulting_entity: string | null;
  created_at: string;
}

export interface AiSuggestionDetail extends AiSuggestion {
  source_artifact_id: string | null;
  source_excerpt: string | null;
  reviewer_name: string | null;
}

export interface AiSuggestionBulkResult {
  accepted: string[];
  rejected: string[];
  errors: Record<string, string>;
}

export async function listAiSuggestions(params?: {
  status?: string;
  kind?: string;
  limit?: number;
}): Promise<AiSuggestion[]> {
  const { data } = await api.GET("/api/v1/ai/suggestions" as any, {
    params: {
      query: {
        status: params?.status ?? undefined,
        kind: params?.kind ?? undefined,
        limit: params?.limit ?? 50,
      },
    },
  });
  return (data ?? []) as AiSuggestion[];
}

export async function getAiSuggestionDetail(id: string): Promise<AiSuggestionDetail> {
  const { data } = await api.GET(`/api/v1/ai/suggestions/${id}` as any, {});
  return (data ?? {}) as AiSuggestionDetail;
}

export async function acceptAiSuggestion(
  id: string,
  editedPayload?: Record<string, unknown>,
  reason?: string,
): Promise<AiSuggestion> {
  const body =
    editedPayload !== undefined || reason
      ? { payload: editedPayload, reason }
      : undefined;
  const { data } = await api.POST(`/api/v1/ai/suggestions/${id}/accept` as any, { body });
  return (data ?? {}) as AiSuggestion;
}

export async function rejectAiSuggestion(id: string, reason: string): Promise<AiSuggestion> {
  const { data } = await api.POST(`/api/v1/ai/suggestions/${id}/reject` as any, {
    body: { reason },
  });
  return (data ?? {}) as AiSuggestion;
}

export async function bulkAiSuggestions(
  items: { suggestion_id: string; action: "accept" | "reject"; reason?: string }[],
): Promise<AiSuggestionBulkResult> {
  const { data } = await api.POST("/api/v1/ai/suggestions/bulk" as any, { body: { items } });
  return (data ?? { accepted: [], rejected: [], errors: {} }) as AiSuggestionBulkResult;
}
