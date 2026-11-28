import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/api";
import {
  createAllocation,
  createScenario,
  getAllocations,
  getCapacityConflicts,
  getCapacityHeatmap,
  listScenarios,
  promoteScenario,
  requestOptimiserOptions,
  type Allocation,
  type Scenario,
  updateAllocation,
} from "@/lib/api/capacity";
import { listUsers } from "@/lib/api/users";
import { useAuth } from "@/lib/auth";
import { PERMISSIONS, usePermissions } from "@/lib/permissions";
import { cn } from "@/lib/utils";

const STATUS_CLASS: Record<string, string> = {
  red: "bg-destructive/20 text-destructive",
  amber: "bg-warning/20 text-warning",
  green: "bg-success/20 text-success",
};

const STATUS_VARIANT: Record<string, BadgeProps["variant"]> = {
  red: "destructive",
  amber: "warning",
  green: "success",
};

const f2 = (value: number | null) => (value === null ? "-" : value.toFixed(2));

function weekLabel(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function CapacityPage() {
  const { t } = useTranslation();
  const { principal } = useAuth();
  const { can } = usePermissions();
  const canAllocate = can(PERMISSIONS.ALLOCATION_MANAGE);
  const canPromote = can(PERMISSIONS.SCENARIO_PROMOTE);
  const [newScenarioName, setNewScenarioName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: heatmap = [], refetch: heatmapRefetch } = useQuery({
    queryKey: ["capacity", "heatmap"],
    queryFn: getCapacityHeatmap,
  });
  const { data: conflicts = [], refetch: conflictsRefetch } = useQuery({
    queryKey: ["capacity", "conflicts"],
    queryFn: getCapacityConflicts,
  });
  const { data: options = [], refetch: optionsRefetch } = useQuery({
    queryKey: ["capacity", "optimise"],
    queryFn: requestOptimiserOptions,
    enabled: canAllocate,
  });
  const { data: scenarios = [], refetch: scenariosRefetch } = useQuery({
    queryKey: ["capacity", "scenarios"],
    queryFn: listScenarios,
  });
  const { data: users = [] } = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const { data: allocationRows = [], refetch: allocationsRefetch } = useQuery({
    queryKey: ["capacity", "allocations"],
    queryFn: getAllocations,
    enabled: canAllocate,
  });
  const [allocForm, setAllocForm] = useState({
    resourceId: "",
    workItemId: "",
    startDate: "",
    endDate: "",
    hoursPerWeek: "",
  });
  const [editingAllocId, setEditingAllocId] = useState<string | null>(null);
  const [editingAllocHours, setEditingAllocHours] = useState("");

  const approverId = users.find((user) => user.subject === principal?.subject)?.id ?? "";

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    }
  };

  const refetchAll = () =>
    Promise.all([heatmapRefetch(), conflictsRefetch(), optionsRefetch(), scenariosRefetch()]);

  const createAlloc = () =>
    void run(async () => {
      const resourceId = allocForm.resourceId.trim();
      const startDate = allocForm.startDate.trim();
      const endDate = allocForm.endDate.trim();
      if (!resourceId || !startDate || !endDate) {
        setError(t("capacity.allocationRequired"));
        return;
      }
      const hoursPerWeek = allocForm.hoursPerWeek.trim()
        ? Number.parseFloat(allocForm.hoursPerWeek)
        : null;
      if (hoursPerWeek !== null && (!Number.isFinite(hoursPerWeek) || hoursPerWeek <= 0)) {
        setError(t("capacity.allocationInvalidHours"));
        return;
      }
      await createAllocation({
        resource_id: resourceId,
        work_item_id: allocForm.workItemId.trim() || null,
        kind: "operational",
        start_date: startDate,
        end_date: endDate,
        hours_per_week: hoursPerWeek,
      });
      setAllocForm({
        resourceId: "",
        workItemId: "",
        startDate: "",
        endDate: "",
        hoursPerWeek: "",
      });
      await allocationsRefetch();
    });

  const saveAllocHours = (allocation: Allocation) =>
    void run(async () => {
      await updateAllocation(allocation.id, {
        hours_per_week: editingAllocHours.trim() ? Number.parseFloat(editingAllocHours) : null,
      });
      setEditingAllocId(null);
      await allocationsRefetch();
    });

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{t("capacity.title")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("capacity.subtitle")}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("capacity.heatmap")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {heatmap.map((resource) => (
            <div key={resource.resource_id} className="space-y-1">
              <div className="text-sm font-medium">{resource.resource_name}</div>
              <div className="flex flex-wrap gap-1">
                {resource.weeks.map((week) => {
                  const weekTooltip = t("capacity.weekTooltip", {
                    date: weekLabel(week.week_start),
                    demand: f2(week.demand),
                    available: f2(week.available),
                    utilisation: f2(week.utilisation),
                  });
                  return (
                    <span
                      key={week.week_start}
                      data-testid="capacity-heatmap-week"
                      className={cn(
                        "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                        STATUS_CLASS[week.status ?? ""] ?? "bg-muted/40 text-muted-foreground",
                      )}
                      title={weekTooltip}
                      aria-label={weekTooltip}
                    >
                      {weekLabel(week.week_start)}
                    </span>
                  );
                })}
              </div>
            </div>
          ))}
          {heatmap.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("capacity.noCapacity")}</p>
          ) : null}
        </CardContent>
      </Card>

      {canAllocate ? (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("capacity.allocations")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={allocForm.resourceId}
              onChange={(event) => setAllocForm((f) => ({ ...f, resourceId: event.target.value }))}
              aria-label={t("capacity.allocationResource")}
              className="h-8 rounded-md border bg-background px-2 text-xs"
            >
              <option value="">{t("capacity.allocationResource")}…</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name}
                </option>
              ))}
            </select>
            <input
              value={allocForm.workItemId}
              onChange={(event) => setAllocForm((f) => ({ ...f, workItemId: event.target.value }))}
              placeholder={t("capacity.allocationWorkItem")}
              aria-label={t("capacity.allocationWorkItem")}
              className="h-8 w-64 rounded-md border bg-background px-2 text-xs"
            />
            <input
              type="date"
              value={allocForm.startDate}
              onChange={(event) => setAllocForm((f) => ({ ...f, startDate: event.target.value }))}
              aria-label={t("capacity.allocationStart")}
              className="h-8 rounded-md border bg-background px-2 text-xs"
            />
            <input
              type="date"
              value={allocForm.endDate}
              onChange={(event) => setAllocForm((f) => ({ ...f, endDate: event.target.value }))}
              aria-label={t("capacity.allocationEnd")}
              className="h-8 rounded-md border bg-background px-2 text-xs"
            />
            <input
              value={allocForm.hoursPerWeek}
              onChange={(event) =>
                setAllocForm((f) => ({ ...f, hoursPerWeek: event.target.value }))
              }
              placeholder={t("capacity.allocationHoursPerWeek")}
              aria-label={t("capacity.allocationHoursPerWeek")}
              className="h-8 w-20 rounded-md border bg-background px-2 text-xs"
            />
            <Button
              size="sm"
              disabled={!allocForm.resourceId || !allocForm.startDate || !allocForm.endDate}
              onClick={createAlloc}
            >
              {t("capacity.allocationCreate")}
            </Button>
          </div>
          {allocationRows.map((allocation) => (
            <div
              key={allocation.id}
              className="flex flex-wrap items-center gap-2 text-sm"
              data-testid="capacity-allocation-row"
            >
              <span className="font-medium">
                {users.find((user) => user.id === allocation.resource_id)?.name ??
                  allocation.resource_id.slice(0, 8)}
              </span>
              <span className="text-xs text-muted-foreground">
                {allocation.start_date} → {allocation.end_date}
              </span>
              {editingAllocId === allocation.id ? (
                <>
                  <input
                    value={editingAllocHours}
                    onChange={(event) => setEditingAllocHours(event.target.value)}
                    aria-label={t("capacity.allocationHoursPerWeek")}
                    className="h-8 w-20 rounded-md border bg-background px-2 text-xs"
                  />
                  <Button size="sm" variant="outline" onClick={() => saveAllocHours(allocation)}>
                    {t("capacity.allocationSave")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditingAllocId(null)}>
                    {t("capacity.allocationCancel")}
                  </Button>
                </>
              ) : (
                <>
                  <span className="text-xs text-muted-foreground">
                    {allocation.hours_per_week ?? "—"} h/wk
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setEditingAllocId(allocation.id);
                      setEditingAllocHours(String(allocation.hours_per_week ?? ""));
                    }}
                  >
                    {t("capacity.allocationEdit")}
                  </Button>
                </>
              )}
              {allocation.locked ? (
                <Badge variant="muted">{t("capacity.allocationLocked")}</Badge>
              ) : null}
            </div>
          ))}
          {allocationRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("capacity.noAllocations")}</p>
          ) : null}
        </CardContent>
      </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("capacity.conflicts")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {conflicts.map((conflict) => (
            <div
              key={`${conflict.resource_id}-${conflict.week_start}`}
              className="rounded border p-3 text-sm"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium">{conflict.resource_id.slice(0, 8)}</span>
                <Badge
                  variant={STATUS_VARIANT[conflict.status] ?? "muted"}
                  data-testid="capacity-conflict-status"
                >
                  {conflict.status}
                </Badge>
              </div>
              {conflict.affected.length > 0 ? (
                <ul className="mt-2 space-y-0.5">
                  {conflict.affected.map((item) => (
                    <li key={item.id}>
                      {item.type}: {item.title}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">{t("capacity.noAffected")}</p>
              )}
            </div>
          ))}
          {conflicts.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("capacity.noConflicts")}</p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("capacity.options")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {options.map((option) => (
            <div key={`${option.strategy}-${option.option_index}`} className="rounded border p-3">
              <div className="text-sm font-medium">
                {t("capacity.strategy", { strategy: option.strategy, index: option.option_index })}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {t("capacity.deltas", {
                  unmet: f2(option.deltas.unmet_hours),
                  overload: f2(option.deltas.overload_hours),
                  reassign: f2(option.deltas.reassignment_hours),
                  skill: f2(option.deltas.skill_gap_hours),
                  delayed: option.deltas.delayed_commitments,
                })}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {option.allocations.map((row) => row.hours).join(", ")}
              </div>
            </div>
          ))}
          {options.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("capacity.noOptions")}</p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("capacity.whatIf")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {canAllocate ? (
          <div className="flex gap-2">
            <input
              value={newScenarioName}
              onChange={(event) => setNewScenarioName(event.target.value)}
              placeholder={t("capacity.scenarioName")}
              className="h-9 flex-1 rounded-md border bg-background px-3 text-sm"
              aria-label={t("capacity.scenarioName")}
            />
            <Button
              size="sm"
              disabled={!newScenarioName.trim()}
              onClick={() =>
                void run(async () => {
                  const scenario: Scenario | null = await createScenario(newScenarioName.trim());
                  if (scenario) setNewScenarioName("");
                })
              }
            >
              {t("capacity.createScenario")}
            </Button>
          </div>
          ) : null}
          {scenarios.map((scenario) => (
            <div
              key={scenario.id}
              className="flex items-center justify-between rounded border p-3 text-sm"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium">{scenario.name}</span>
                {scenario.promoted ? (
                  <Badge variant="outline">{t("capacity.promoted")}</Badge>
                ) : null}
              </div>
              {canPromote ? (
              <Button
                variant="outline"
                size="sm"
                disabled={!approverId || scenario.promoted}
                onClick={() =>
                  void run(async () => {
                    if (approverId) {
                      await promoteScenario(scenario.id, approverId);
                      await refetchAll();
                    }
                  })
                }
              >
                {t("capacity.promote")}
              </Button>
              ) : null}
            </div>
          ))}
          {scenarios.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("capacity.noScenarios")}</p>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
