/* eslint-disable @typescript-eslint/no-explicit-any */
import { api } from "@/lib/api";

export interface GraphNode {
  id: string;
  type: string | null;
  title: string;
  description: string | null;
  status: string | null;
  origin: string | null;
  attributes: Record<string, any>;
  is_simulated: boolean;
}

export interface GraphEdge {
  id: string | null;
  src_id: string;
  dst_id: string;
  link_type: string | null;
  weight: number | null;
  is_virtual: boolean;
  src: GraphNode;
  dst: GraphNode;
}

export interface NeighborsResult {
  node_id: string;
  node: GraphNode;
  edges: GraphEdge[];
}

export interface LineageResult {
  items: GraphNode[];
}

export interface PathResult {
  exists: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ImpactItem {
  id: string;
  type: string;
  title: string;
  depth: number;
  strongest_path_weight: number | null;
}

export interface DownstreamImpactResult {
  root_id: string;
  items: ImpactItem[];
}

export async function getNeighbors(itemId: string, direction: "in" | "out" | "both" = "both") {
  const { data } = await api.GET(`/api/v1/graph/nodes/${itemId}/neighbors` as any, {
    params: { query: { direction, include_virtual: true } },
  });
  return (data ?? { node_id: "", edges: [] }) as NeighborsResult;
}

export async function getLineage(itemId: string) {
  const { data } = await api.GET(`/api/v1/graph/nodes/${itemId}/lineage` as any, {});
  return (data ?? { items: [] }) as LineageResult;
}

export async function getPath(fromId: string, toId: string) {
  const { data } = await api.GET("/api/v1/graph/path" as any, {
    params: { query: { from: fromId, to: toId, include_virtual: true } },
  });
  return (data ?? { exists: false, nodes: [], edges: [] }) as PathResult;
}

export async function getDownstreamImpact(itemId: string) {
  const { data } = await api.GET(`/api/v1/graph/nodes/${itemId}/downstream-impact` as any, {
    params: { query: { max_depth: 6 } },
  });
  return (data ?? { root_id: itemId, items: [] }) as DownstreamImpactResult;
}
