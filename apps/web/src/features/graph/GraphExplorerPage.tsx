/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  useReactFlow,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getDownstreamImpact, getLineage, getNeighbors, type GraphNode } from "@/lib/api/graph";
import { listItemsPage } from "@/lib/api/items";
import { cn } from "@/lib/utils";

const LINK_COLORS: Record<string, string> = {
  part_of: "#8b5cf6",
  aligns_to: "#3b82f6",
  depends_on: "#f97316",
  fulfils: "#22c55e",
  realizes: "#06b6d4",
  threatens: "#ef4444",
  mitigates: "#a16207",
  duplicate_of: "#64748b",
  related_to: "#64748b",
  derived_from: "#475569",
  assigned_to: "#8b5cf6",
};

const RAG_STYLES: Record<string, string> = {
  green: "border-success/60 bg-success/10 text-success",
  amber: "border-warning/60 bg-warning/10 text-warning",
  red: "border-destructive/60 bg-destructive/10 text-destructive",
  none: "border-border bg-muted/40 text-foreground",
};

function ragOf(node: GraphNode): string {
  const rag = node.attributes?.rag;
  return rag === "green" || rag === "amber" || rag === "red" ? rag : "none";
}

interface WorkGraphNodeData {
  label: string;
  type: string | null;
  status: string;
  rag: string;
  sim: boolean;
  expanded: boolean;
  depth?: number;
}

function WorkGraphNode({ data }: { data: WorkGraphNodeData }) {
  const ragClass = RAG_STYLES[data.rag] ?? RAG_STYLES.none;
  return (
    <div className={cn("rounded-md border px-2.5 py-1.5 text-xs shadow-sm", ragClass)}>
      <div className="flex items-center gap-1.5">
        <span className="max-w-[110px] truncate font-medium" title={data.label}>
          {data.label}
        </span>
        {data.sim ? <Badge variant="outline">SIM</Badge> : null}
      </div>
      <div className="mt-0.5 flex items-center gap-1 text-[9px] uppercase text-muted-foreground">
        <span>{data.type ?? "resource"}</span>
        {data.expanded ? <span className="text-primary">· expanded</span> : null}
      </div>
    </div>
  );
}

const nodeTypes: NodeTypes = { workGraphNode: WorkGraphNode };

function edgeKey(srcId: string, dstId: string, linkType: string | null): string {
  return `${srcId}|${dstId}|${linkType ?? ""}`;
}

function positionFor(index: number): { x: number; y: number } {
  return { x: (index % 6) * 230, y: Math.floor(index / 6) * 160 };
}

function FitView({ count }: { count: number }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    fitView({ duration: 300, padding: 0.1 });
  }, [count, fitView]);
  return null;
}

type FlowNode = Node<any>;
type FlowEdge = Edge<any>;

export function GraphExplorerPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [hiddenLinkTypes, setHiddenLinkTypes] = useState<Set<string>>(new Set());
  const [hiddenStatuses, setHiddenStatuses] = useState<Set<string>>(new Set());
  const [showImpact, setShowImpact] = useState(false);

  const rootId = searchParams.get("root") ?? "";

  interface RootOption {
    id: string;
    label: string;
  }

  const { data: rootOptions } = useQuery({
    queryKey: ["items", "graph-root-picker"],
    queryFn: () => listItemsPage({ limit: 500 }),
  });
  const options = useMemo((): RootOption[] => {
    const items = (rootOptions?.items ?? []) as { id: string; type: string; title: string }[];
    return items.map((item) => ({ id: item.id, label: `${item.type}: ${item.title}` }));
  }, [rootOptions]);

  const lineageQuery = useQuery({
    queryKey: ["graph", "lineage", rootId],
    queryFn: () => getLineage(rootId),
    enabled: !!rootId,
  });
  const lineageItems = useMemo(() => lineageQuery.data?.items ?? [], [lineageQuery.data]);

  const loadIds = useMemo(() => {
    const ids = new Set<string>(lineageItems.map((item) => item.id));
    expandedIds.forEach((id) => ids.add(id));
    if (selectedId) ids.add(selectedId);
    return [...ids];
  }, [lineageItems, expandedIds, selectedId]);

  const neighborQueries = useQueries({
    queries: loadIds.map((id) => ({
      queryKey: ["graph", "neighbors", id],
      queryFn: () => getNeighbors(id),
    })),
  });

  const { nodeMap, flowNodes, flowEdges, visibleNodes, visibleEdges } = useMemo(() => {
    const map = new Map<string, GraphNode>();
    const edgeMap = new Map<string, { src_id: string; dst_id: string; link_type: string | null }>();
    const addNode = (node: GraphNode) => {
      if (!map.has(node.id)) map.set(node.id, node);
    };
    for (const item of lineageItems) addNode(item);
    loadIds.forEach((id, idx) => {
      const result = neighborQueries[idx]?.data;
      if (!result) return;
      addNode(result.node);
      for (const edge of result.edges) {
        edgeMap.set(edgeKey(edge.src_id, edge.dst_id, edge.link_type), edge);
        addNode(edge.src);
        addNode(edge.dst);
      }
    });

    const nodes: FlowNode[] = [...map.values()].map((node, index) => ({
      id: node.id,
      type: "workGraphNode",
      position: positionFor(index),
      data: {
        label: node.title,
        type: node.type,
        status: node.status ?? "",
        rag: ragOf(node),
        sim: node.is_simulated,
        expanded: expandedIds.has(node.id),
      },
      draggable: true,
      connectable: false,
    }));

    const edges: FlowEdge[] = [...edgeMap.values()]
      .filter((edge) => map.has(edge.src_id) && map.has(edge.dst_id))
      .map((edge) => ({
        id: edgeKey(edge.src_id, edge.dst_id, edge.link_type),
        source: edge.src_id,
        target: edge.dst_id,
        label: edge.link_type ?? "",
        type: "smoothstep",
        data: { linkType: edge.link_type },
        style: { stroke: LINK_COLORS[edge.link_type ?? ""] ?? "#64748b", strokeWidth: 2 },
      }));

    const visible = edges
      .filter(
        (edge) =>
          !hiddenLinkTypes.has(edge.data?.linkType ?? "") &&
          !hiddenStatuses.has(map.get(edge.source)?.status ?? "") &&
          !hiddenStatuses.has(map.get(edge.target)?.status ?? ""),
      )
      .sort((a, b) => a.source.localeCompare(b.source));
    const visibleIds = new Set(visible.flatMap((edge) => [edge.source, edge.target]));
    if (rootId) visibleIds.add(rootId);
    if (selectedId) visibleIds.add(selectedId);
    const visibleNodes = nodes.filter((node) => visibleIds.has(node.id));

    return {
      nodeMap: map,
      flowNodes: nodes,
      flowEdges: edges,
      visibleNodes,
      visibleEdges: visible,
    };
  }, [
    lineageItems,
    loadIds,
    neighborQueries,
    expandedIds,
    hiddenLinkTypes,
    hiddenStatuses,
    rootId,
    selectedId,
  ]);

  const selected = selectedId ? (nodeMap.get(selectedId) ?? null) : null;

  const impactQuery = useQuery({
    queryKey: ["graph", "impact", selectedId],
    queryFn: () => getDownstreamImpact(selectedId!),
    enabled: !!selectedId && showImpact,
  });

  const setRoot = (id: string) => {
    setSearchParams((params) => {
      params.set("root", id);
      return params;
    });
    setExpandedIds(new Set());
    setShowImpact(false);
  };

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const linkTypes = useMemo(
    () =>
      [...new Set(visibleEdges.map((edge) => edge.data?.linkType ?? "").filter(Boolean))].sort(),
    [visibleEdges],
  );
  const statusSet = useMemo(
    () => [...new Set(flowNodes.map((node) => node.data.status ?? "").filter(Boolean))],
    [flowNodes],
  );

  const typeSet = useMemo(
    () => [...new Set(flowNodes.map((node) => node.data.type ?? "").filter(Boolean))],
    [flowNodes],
  );

  return (
    <div className="mx-auto flex h-[72vh] max-w-6xl flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
        <div className="flex items-center gap-2">
          <h2 className="text-2xl font-semibold tracking-tight">{t("nav.graph")}</h2>
          <select
            value={rootId}
            onChange={(event) => setRoot(event.target.value)}
            className="h-8 rounded-md border bg-background px-2 text-xs"
            aria-label={t("graph.rootLabel")}
          >
            <option value="">{t("graph.selectRoot")}</option>
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <Button variant="outline" size="sm" onClick={() => void lineageQuery.refetch()}>
          {t("common.refresh")}
        </Button>
      </div>

      <div className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={visibleNodes}
          edges={visibleEdges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          nodesDraggable
          proOptions={{ hideAttribution: true }}
        >
          <FitView count={flowNodes.length + flowEdges.length} />
          <Background color="var(--muted)" size={2} />
          <Controls />
          <MiniMap zoomable pannable />
          <Panel position="top-right">
            <div className="flex max-w-[240px] flex-col gap-2 rounded-lg border bg-card/90 p-2 shadow-lg backdrop-blur">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t("graph.linkTypes")} ({linkTypes.length})
              </div>
              <div className="flex flex-wrap gap-1">
                {linkTypes.map((linkType) => {
                  const active = !hiddenLinkTypes.has(linkType ?? "");
                  return (
                    <Button
                      key={linkType}
                      variant="outline"
                      size="sm"
                      className="h-6 px-2 text-[10px]"
                      style={{
                        borderColor: active ? LINK_COLORS[linkType] : undefined,
                      }}
                      onClick={() =>
                        setHiddenLinkTypes((prev) => {
                          const next = new Set(prev);
                          if (next.has(linkType)) next.delete(linkType);
                          else next.add(linkType);
                          return next;
                        })
                      }
                    >
                      {linkType}
                      {active ? "" : " ✕"}
                    </Button>
                  );
                })}
              </div>
              {statusSet.length > 0 && (
                <>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {t("graph.status")}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {statusSet.map((status) => (
                      <Button
                        key={status}
                        variant="outline"
                        size="sm"
                        className="h-6 px-2 text-[10px]"
                        onClick={() =>
                          setHiddenStatuses((prev) => {
                            const next = new Set(prev);
                            if (next.has(status)) next.delete(status);
                            else next.add(status);
                            return next;
                          })
                        }
                      >
                        {status}
                      </Button>
                    ))}
                  </div>
                </>
              )}
              {typeSet.length > 0 && (
                <>
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {t("graph.type")}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {typeSet.map((type) => (
                      <Badge key={type} variant="outline" className="h-6 px-2 text-[10px]">
                        {type}
                      </Badge>
                    ))}
                  </div>
                </>
              )}
            </div>
          </Panel>
        </ReactFlow>
      </div>

      {selected ? (
        <Card className="absolute inset-x-3 bottom-3 z-10 max-h-[40vh] overflow-y-auto border shadow-xl">
          <CardHeader className="space-y-1 pb-2">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-base">{selected.title}</CardTitle>
              <div className="flex items-center gap-2">
                {selected.is_simulated ? <Badge variant="outline">SIM</Badge> : null}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void navigate(`/graph?root=${selected.id}`)}
                >
                  {t("graph.exploreFromHere")}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setSelectedId(null);
                    setShowImpact(false);
                  }}
                >
                  {t("common.close")}
                </Button>
              </div>
            </div>
            <div className="flex flex-wrap gap-1">
              <Badge variant="muted">{selected.type ?? "resource"}</Badge>
              <Badge variant="outline">{selected.status ?? t("graph.resource")}</Badge>
              <Badge variant="outline" className={RAG_STYLES[ragOf(selected)]}>
                RAG: {ragOf(selected)}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            {selected.description ? (
              <p className="text-xs text-muted-foreground">{selected.description}</p>
            ) : null}
            {selected.origin === "external" || selected.origin === "ai_extracted" ? (
              <div className="text-[10px] text-muted-foreground">
                {t("graph.origin")}: {selected.origin}
              </div>
            ) : null}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
              {selected.attributes?.planned_start ? (
                <span>
                  {t("graph.plannedStart")}: {selected.attributes.planned_start}
                </span>
              ) : null}
              {selected.attributes?.planned_end ? (
                <span>
                  {t("graph.plannedEnd")}: {selected.attributes.planned_end}
                </span>
              ) : null}
              {selected.attributes?.baseline_end ? (
                <span>
                  {t("graph.baselineEnd")}: {selected.attributes.baseline_end}
                </span>
              ) : null}
              {selected.attributes?.forecast_end ? (
                <span>
                  {t("graph.forecastEnd")}: {selected.attributes.forecast_end}
                </span>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => toggleExpanded(selected.id)}>
                {expandedIds.has(selected.id)
                  ? t("graph.collapseNeighbours")
                  : t("graph.expandNeighbours")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowImpact(true);
                }}
              >
                {t("graph.downstreamImpact")}
              </Button>
            </div>
            {showImpact ? (
              <div className="space-y-2">
                {impactQuery.isError ? (
                  <p className="text-xs text-destructive">{t("common.error")}</p>
                ) : null}
                {(impactQuery.data?.items ?? []).length === 0 ? (
                  <p className="text-xs text-muted-foreground">{t("graph.noImpact")}</p>
                ) : null}
                <div className="max-h-40 space-y-1 overflow-y-auto">
                  {(impactQuery.data?.items ?? []).map((item) => (
                    <div
                      key={item.id}
                      className="flex items-center justify-between rounded border px-2 py-1 text-xs"
                    >
                      <span className="truncate">
                        {item.type}: {nodeMap.get(item.id)?.title ?? item.title}
                      </span>
                      <span className="text-muted-foreground">
                        {t("graph.depth")}: {item.depth}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="pt-1">
              <p className="text-[10px] text-muted-foreground">
                {t("graph.chainHelp")}
                {lineageItems.length > 1
                  ? ` — ${lineageItems.map((item) => item.title).join(" → ")}`
                  : ""}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export default GraphExplorerPage;
