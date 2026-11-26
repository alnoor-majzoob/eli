/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

type AnyData = any;

export async function listApprovals(params?: { status?: string; limit?: number }) {
  const { data } = await api.GET("/api/v1/approvals" as any, {
    params: { query: (params ?? { limit: 100 }) as any },
  });
  return (data ?? {}) as AnyData;
}

export async function listInbox() {
  const { data } = await api.GET("/api/v1/approvals/inbox" as any, {});
  return (data ?? {}) as AnyData;
}

export async function getApproval(approval_id: string) {
  const { data } = await api.GET(`/api/v1/approvals/${approval_id}` as any, {});
  return (data ?? {}) as AnyData;
}

export async function decideApproval(
  approval_id: string,
  decision: "approved" | "rejected",
  comment?: string,
) {
  const { error } = await api.POST(`/api/v1/approvals/${approval_id}/decide` as any, {
    body: { decision, comment },
  });
  return error;
}

export async function delegateApproval(approval_id: string, delegateTo: string) {
  const { error } = await api.POST(`/api/v1/approvals/${approval_id}/delegate` as any, {
    body: { delegate_to: delegateTo },
  });
  return error;
}

export async function escalateOverdueApprovals() {
  const { data, error } = await api.POST("/api/v1/approvals/escalate-overdue" as any, {});
  return { data: data as AnyData, error };
}
