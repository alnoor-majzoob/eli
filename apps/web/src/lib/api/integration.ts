/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

export interface ConnectorCapability {
  system: string;
  record_types: string[];
  modes: string[];
  default_mode: string;
  push_supported: boolean;
}

export interface ConnectorEntry {
  system: string;
  capabilities: ConnectorCapability;
  mode: string;
  push_supported: boolean;
}

export interface ApprovedSource {
  id: string;
  type: string;
  name: string;
  description: string | null;
  scope_filters: any;
  owner: string;
  classification: string;
  retention_days: number | null;
  ai_processing_allowed: boolean;
  enabled: boolean;
  owned_fields: string[];
  write_back_enabled: boolean;
  write_back_fields: string[];
  write_back_requires_approval: boolean;
  sync_cursor: string | null;
  sync_lag_seconds: number | null;
  last_sync_at: string | null;
  last_sync_error: string | null;
}

export interface SourceStatus {
  source_id: string;
  health: string;
  last_sync_at: string | null;
  lag_seconds: number | null;
  error_count: number;
  conflicts_unresolved: number;
}

export interface SyncConflict {
  id: string;
  source_id: string;
  work_item_id: string;
  field: string;
  external_value: any;
  local_value: any;
  description: string | null;
  resolved: boolean;
  resolved_at: string | null;
  created_at: string;
}

export interface WriteBackChange {
  id: string;
  source_id: string;
  work_item_id: string;
  action: string;
  payload: any;
  status: string;
  approved_by: string | null;
  executed_at: string | null;
  rejected_reason: string | null;
  created_at: string;
}

export async function listConnectors() {
  const { data } = await api.GET("/api/v1/integrations/connectors" as any, {});
  return (data ?? []) as ConnectorEntry[];
}

export async function listSources() {
  const { data } = await api.GET("/api/v1/integrations/sources" as any, {});
  return (data ?? []) as ApprovedSource[];
}

export async function createSource(body: any) {
  const { data } = await api.POST("/api/v1/integrations/sources" as any, { body });
  return (data ?? {}) as ApprovedSource;
}

export async function updateSource(sourceId: string, body: any) {
  const { data } = await api.PATCH(`/api/v1/integrations/sources/${sourceId}` as any, { body });
  return (data ?? {}) as ApprovedSource;
}

export async function deleteSource(sourceId: string) {
  await api.DELETE(`/api/v1/integrations/sources/${sourceId}` as any, {});
}

export async function syncSource(sourceId: string) {
  const { data } = await api.POST(`/api/v1/integrations/sources/${sourceId}/sync` as any, {});
  return (data ?? {}) as {
    id: string;
    status: string;
    records_count: number | null;
    errors: string[];
    triggered_by: string | null;
    last_error: string | null;
  };
}

export async function getSourceStatus(sourceId: string) {
  const { data } = await api.GET(`/api/v1/integrations/sources/${sourceId}/status` as any, {});
  return (data ?? {}) as SourceStatus;
}

export async function listSourceConflicts(sourceId: string) {
  const { data } = await api.GET(`/api/v1/integrations/sources/${sourceId}/conflicts` as any, {});
  return (data ?? []) as SyncConflict[];
}

export async function resolveSourceConflict(sourceId: string, conflictId: string) {
  const { data } = await api.POST(
    `/api/v1/integrations/sources/${sourceId}/conflicts/${conflictId}/resolve` as any,
    {},
  );
  return (data ?? {}) as SyncConflict;
}

export async function listSourceWritebacks(sourceId: string) {
  const { data } = await api.GET(`/api/v1/integrations/sources/${sourceId}/writebacks` as any, {});
  return (data ?? []) as WriteBackChange[];
}

export async function submitWriteback(sourceId: string, body: any) {
  const { data } = await api.POST(`/api/v1/integrations/sources/${sourceId}/writebacks` as any, {
    body,
  });
  return (data ?? {}) as WriteBackChange;
}

export async function approveWriteback(sourceId: string, changeId: string) {
  const { data } = await api.POST(
    `/api/v1/integrations/sources/${sourceId}/writebacks/${changeId}/approve` as any,
    {},
  );
  return (data ?? {}) as WriteBackChange;
}

export async function executeWriteback(sourceId: string, changeId: string) {
  await api.POST(
    `/api/v1/integrations/sources/${sourceId}/writebacks/${changeId}/execute` as any,
    {},
  );
}
