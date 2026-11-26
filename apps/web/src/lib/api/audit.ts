/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

type AnyData = any;

export interface AuditFilters {
  action?: string;
  entity_id?: string;
  entity_type?: string;
  from_ts?: string;
  to_ts?: string;
}

export async function listAudit(filters?: AuditFilters) {
  const { data } = await api.GET("/api/v1/audit" as any, {
    params: { query: (filters ?? { limit: 100 }) as any },
  });
  return (data ?? []) as AnyData[];
}

export async function verifyAudit() {
  const { data } = await api.GET("/api/v1/audit/verify" as any, {});
  return (data ?? {}) as AnyData;
}

export async function exportAuditCsv(): Promise<string | null> {
  const { data, error, response } = await api.GET("/api/v1/audit/export.csv" as any, {
    parseAs: "blob",
  });
  if (!response.ok || error || !data) return null;
  const url = URL.createObjectURL(data as Blob);
  return url;
}
