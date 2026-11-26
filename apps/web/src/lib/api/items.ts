/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

type AnyData = any;

export async function getDashboard() {
  const { data } = await api.GET("/api/v1/dashboard");
  return (data ?? {}) as AnyData;
}

export async function listItemsPage(params?: {
  type?: string;
  status?: string;
  parent_id?: string;
  limit?: number;
  offset?: number;
}) {
  const { data } = await api.GET("/api/v1/items" as any, {
    params: {
      query: {
        type: (params?.type ?? undefined) as any,
        status: (params?.status ?? undefined) as any,
        parent_id: params?.parent_id ?? undefined,
        limit: params?.limit ?? 50,
        offset: params?.offset ?? 0,
      },
    },
  });
  return (data ?? {}) as AnyData;
}

export async function listWorkflows() {
  const { data } = await api.GET("/api/v1/workflows" as any, {});
  return (data ?? []) as AnyData[];
}

export async function getItem(item_id: string) {
  const { data } = await api.GET(`/api/v1/items/${item_id}` as any, {});
  return (data ?? {}) as AnyData;
}

export async function createItem(body: AnyData) {
  const { data } = await api.POST("/api/v1/items" as any, { body });
  return (data ?? {}) as AnyData;
}

export async function updateItem(item_id: string, body: AnyData) {
  const { data } = await api.PATCH(`/api/v1/items/${item_id}` as any, { body });
  return (data ?? {}) as AnyData;
}

export async function updateItemStatus(item_id: string, status: string, version?: number) {
  return updateItem(item_id, { status, version });
}

export async function deleteItem(item_id: string) {
  const { error } = await api.DELETE(`/api/v1/items/${item_id}` as any, {});
  return error;
}

export async function submitItem(item_id: string, workflowKey?: string) {
  const params = workflowKey ? { params: { query: { workflow_key: workflowKey } } } : {};
  const { data } = await api.POST(`/api/v1/items/${item_id}/submit` as any, params as any);
  return (data ?? {}) as AnyData;
}

export async function listLinks(item_id: string) {
  const { data } = await api.GET(`/api/v1/items/${item_id}/links` as any, {});
  return (data ?? []) as AnyData[];
}

export async function createLink(item_id: string, body: AnyData) {
  const { data } = await api.POST(`/api/v1/items/${item_id}/links` as any, { body });
  return (data ?? {}) as AnyData;
}

export async function deleteLink(item_id: string, link_id: string) {
  const { error } = await api.DELETE(`/api/v1/items/${item_id}/links/${link_id}` as any, {});
  return error;
}

export async function getBenefitMeasurements(item_id: string) {
  const { data } = await api.GET(`/api/v1/items/${item_id}/benefit-measurements` as any, {});
  return (data ?? []) as AnyData[];
}

export async function getBenefitRealisation(item_id: string) {
  const { data } = await api.GET(`/api/v1/items/${item_id}/benefit-realisation` as any, {});
  return (data ?? {}) as AnyData;
}
