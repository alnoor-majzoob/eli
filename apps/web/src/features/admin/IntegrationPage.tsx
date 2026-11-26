import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/api";
import {
  approveWriteback,
  createSource,
  deleteSource,
  executeWriteback,
  getSourceStatus,
  listConnectors,
  listSourceConflicts,
  listSourceWritebacks,
  listSources,
  resolveSourceConflict,
  syncSource,
  updateSource,
  type ApprovedSource,
} from "@/lib/api/integration";

const BADGE: Record<string, "success" | "warning" | "destructive" | "muted"> = {
  ok: "success",
  succeeded: "success",
  running: "muted",
  failed: "destructive",
  degraded: "warning",
  unavailable: "destructive",
};

export default function IntegrationPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ type: "p6", name: "", owner: "" });
  const [approvedBy, setApprovedBy] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const { data: connectors = [] } = useQuery({
    queryKey: ["integrations", "connectors"],
    queryFn: listConnectors,
  });
  const { data: sources = [], refetch: refetchSources } = useQuery({
    queryKey: ["integrations", "sources"],
    queryFn: listSources,
  });
  const connectorTypes = connectors.map((connector) => connector.system);

  const handle = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await refetchSources();
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    }
  };

  const create = () =>
    handle(async () => {
      if (!form.name.trim() || !form.owner.trim()) return;
      await createSource({ type: form.type, name: form.name.trim(), owner: form.owner.trim() });
      setForm({ type: form.type, name: "", owner: "" });
      void queryClient.invalidateQueries({ queryKey: ["integrations", "sources"] });
    });

  const createDisabled = !form.name.trim() || !form.owner.trim();

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{t("integration.title")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("integration.subtitle")}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetchSources()}>
          <RefreshCw className="size-3.5" />
          {t("common.refresh")}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("integration.connectors")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 pr-4">System</th>
                  <th className="py-2 pr-4">Record types</th>
                  <th className="py-2 pr-4">Modes</th>
                  <th className="py-2">Push</th>
                </tr>
              </thead>
              <tbody>
                {connectors.map((connector) => (
                  <tr key={connector.system} className="border-b last:border-0">
                    <td className="py-2 pr-4 font-medium">{connector.system}</td>
                    <td className="py-2 pr-4">
                      <span className="text-muted-foreground">
                        {connector.capabilities.record_types.join(", ")}
                      </span>
                    </td>
                    <td className="py-2 pr-4">
                      <span className="text-muted-foreground">
                        {connector.capabilities.modes.join(" / ")} · {connector.mode}
                      </span>
                    </td>
                    <td className="py-2">
                      <Badge variant={connector.push_supported ? "success" : "muted"}>
                        {connector.push_supported ? t("integration.push") : t("integration.noPush")}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("integration.sources")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("integration.noSources")}</p>
          ) : (
            sources.map((source) => (
              <SourceRow
                key={source.id}
                source={source}
                onUpdate={() => void refetchSources()}
                approvedBy={approvedBy[source.id] ?? ""}
                setApprovedBy={(v) => setApprovedBy({ ...approvedBy, [source.id]: v })}
              />
            ))
          )}
          <div className="flex items-center gap-2">
            <select
              value={form.type}
              onChange={(event) => setForm({ ...form, type: event.target.value })}
              className="h-8 rounded-md border bg-background px-2 text-xs"
              aria-label={t("integration.type")}
            >
              {connectorTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <input
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder={t("integration.name")}
              className="h-8 flex-1 rounded-md border bg-background px-2 text-xs"
              aria-label={t("integration.name")}
            />
            <input
              value={form.owner}
              onChange={(event) => setForm({ ...form, owner: event.target.value })}
              placeholder={t("integration.owner")}
              className="h-8 w-36 rounded-md border bg-background px-2 text-xs"
              aria-label={t("integration.owner")}
            />
            <Button size="sm" onClick={() => void create()} disabled={createDisabled}>
              {t("common.create")}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function SourceRow({
  source,
  onUpdate,
  approvedBy,
  setApprovedBy,
}: {
  source: ApprovedSource;
  onUpdate: () => void;
  approvedBy: string;
  setApprovedBy: (value: string) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const status = useQuery({
    queryKey: ["integrations", "source-status", source.id],
    queryFn: () => getSourceStatus(source.id),
  });
  const conflicts = useQuery({
    queryKey: ["integrations", "source-conflicts", source.id],
    queryFn: () => listSourceConflicts(source.id),
  });
  const writebacks = useQuery({
    queryKey: ["integrations", "source-writebacks", source.id],
    queryFn: () => listSourceWritebacks(source.id),
  });

  const doUpdate = async (body: Record<string, unknown>) => {
    setBusy(true);
    try {
      await updateSource(source.id, body);
      onUpdate();
      void queryClient.invalidateQueries({
        queryKey: ["integrations", "source-status", source.id],
      });
    } catch {
      /* surfaced via the page-level handler below */
    } finally {
      setBusy(false);
    }
  };

  const toggleEnabled = async () => {
    setBusy(true);
    try {
      await doUpdate({ enabled: !source.enabled });
    } finally {
      setBusy(false);
    }
  };

  const toggleAiProcessing = async () => {
    const next = !source.ai_processing_allowed;
    if (next && !approvedBy.trim()) {
      return; // SOD-4: needs a second approver (plan §13.2)
    }
    setBusy(true);
    try {
      await doUpdate(
        next
          ? {
              ai_processing_allowed: true,
              approved_by: approvedBy,
              reason: t("integration.secondApprover"),
            }
          : { ai_processing_allowed: false },
      );
    } finally {
      setBusy(false);
      if (next) setApprovedBy("");
    }
  };

  const sync = () => {
    setBusy(true);
    syncSource(source.id)
      .catch(() => undefined)
      .finally(() => {
        setBusy(false);
        void queryClient.invalidateQueries({
          queryKey: ["integrations", "source-status", source.id],
        });
        onUpdate();
      });
  };

  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{source.name}</p>
          <p className="text-[10px] text-muted-foreground">
            {source.type} · {source.owner} · {source.classification}
            {source.last_sync_at
              ? ` · ${t("integration.lastSync")}: ${new Date(source.last_sync_at).toLocaleString()}`
              : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant={BADGE[status.data?.health ?? "ok"] ?? "muted"}>
            {t("integration.health")}: {status.data?.health ?? t("common.loading")}
          </Badge>
          {status.data?.lag_seconds != null ? (
            <Badge variant="muted">
              {t("integration.lag")}: {status.data.lag_seconds}s
            </Badge>
          ) : null}
          {status.data?.error_count ? (
            <Badge variant="destructive">
              {t("common.error")}×{status.data.error_count}
            </Badge>
          ) : null}
          <Button variant="outline" size="sm" onClick={sync} disabled={busy}>
            {t("integration.syncNow")}
          </Button>
          <Button variant="outline" size="sm" onClick={() => void toggleEnabled()} disabled={busy}>
            {source.enabled ? t("integration.disable") : t("integration.enable")}
          </Button>
          {source.enabled ? null : (
            <Button
              variant="destructive"
              size="sm"
              onClick={() => void deleteSource(source.id).finally(onUpdate)}
            >
              <Trash2 className="size-3.5" />
              {t("common.delete")}
            </Button>
          )}
          {source.ai_processing_allowed ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => void toggleAiProcessing()}
              disabled={busy}
            >
              {t("integration.disableAiProcessing")}
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => void toggleAiProcessing()}
              disabled={busy}
            >
              {t("integration.enableAiProcessing")}
            </Button>
          )}
          {source.ai_processing_allowed && !approvedBy ? (
            <input
              value=""
              placeholder={t("integration.secondApproverPlaceholder")}
              onChange={(event) => setApprovedBy(event.target.value)}
              className="h-7 w-40 rounded-md border bg-background px-2 text-[10px]"
              aria-label={t("integration.secondApprover")}
            />
          ) : null}
          {source.ai_processing_allowed ? (
            <Badge variant="success">{t("integration.aiProcessing")}</Badge>
          ) : null}
        </div>
      </div>

      {conflicts.data?.length ? (
        <div className="space-y-1 rounded-md bg-muted/30 p-2">
          <p className="text-[10px] font-semibold uppercase text-muted-foreground">
            {t("integration.conflicts")} ({conflicts.data.length})
          </p>
          {conflicts.data.map((conflict) => (
            <div key={conflict.id} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-muted-foreground">
                {conflict.field}:{JSON.stringify(conflict.external_value)} vs{" "}
                {JSON.stringify(conflict.local_value)}
              </span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => void resolveSourceConflict(source.id, conflict.id).finally(onUpdate)}
              >
                {t("integration.resolve")}
              </Button>
            </div>
          ))}
        </div>
      ) : null}

      {writebacks.data?.length ? (
        <div className="space-y-1 rounded-md bg-muted/30 p-2">
          <p className="text-[10px] font-semibold uppercase text-muted-foreground">
            {t("integration.writebacks")}
          </p>
          {writebacks.data.map((change) => (
            <div key={change.id} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-muted-foreground">
                {change.action} — {change.status}
              </span>
              <div className="flex gap-1">
                {change.status === "pending" ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void approveWriteback(source.id, change.id).finally(onUpdate)}
                  >
                    {t("integration.approve")}
                  </Button>
                ) : null}
                {change.status === "approved" ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void executeWriteback(source.id, change.id).finally(onUpdate)}
                  >
                    {t("integration.execute")}
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
