/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

export interface AssistantCitation {
  id: string;
  source?: string;
}

export interface AskEilResponse {
  answer: string;
  tool_log: { name: string; arguments: Record<string, any>; output: Record<string, any> }[];
  citations: AssistantCitation[];
}

export async function askEil(question: string): Promise<AskEilResponse> {
  const { data } = await api.POST("/api/v1/assistant/ask" as any, { body: { question } });
  return (data ?? null) as AskEilResponse;
}
