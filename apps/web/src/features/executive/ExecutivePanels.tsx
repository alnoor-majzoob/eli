import { useTranslation } from "react-i18next";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ExecutiveSummary } from "@/lib/api/executive";
import type { EscalationRow, RadarRow } from "@/lib/api/risk";

const BADGE_VARIANT: Record<string, BadgeProps["variant"]> = {
  red: "destructive",
  amber: "warning",
  green: "success",
};

const f2 = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : value.toFixed(2);

const daysUntil = (dueAt: string) => Math.ceil((new Date(dueAt).getTime() - Date.now()) / 86400000);

interface ExecutivePanelsProps {
  summary: ExecutiveSummary;
  radar?: RadarRow[];
  escalations?: EscalationRow[];
  variant?: "compact" | "presenter";
}

export function ExecutivePanels({
  summary: s,
  radar = [],
  escalations = [],
  variant = "compact",
}: ExecutivePanelsProps) {
  const { t } = useTranslation();
  const big = variant === "presenter";
  const panelGrid = big ? "grid gap-6 md:grid-cols-2 xl:grid-cols-3" : undefined;
  const cardClass = big ? "border-2 shadow-lg" : undefined;
  const valueClass = big ? "text-2xl font-bold" : "font-mono";
  const rowClass = big
    ? "flex items-center justify-between gap-3 text-base"
    : "flex items-center justify-between gap-2";

  const atRiskIds = new Set(s.at_risk.map((row) => row.item_id));
  const atRiskList = [...s.at_risk.map((row) => ({ ...row, kind: "at-risk" as const }))];

  return (
    <div className={panelGrid}>
      <Card data-testid="executive-committed" className={cardClass}>
        <CardHeader>
          <CardTitle>{t("executive.committed")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-base">
            {t("executive.committedTotal", { count: s.committed.total })} —{" "}
            {t("executive.asOf", { date: new Date(s.as_of).toLocaleDateString() })}
          </p>
          <p className="mt-1 text-base">
            {t("executive.committedAvg", { confidence: f2(s.committed.avg_confidence) })}
          </p>
          {s.committed.by_org_unit.length > 0 ? (
            <ul className={big ? "mt-2 space-y-1" : "mt-2 space-y-0.5 text-xs"}>
              {s.committed.by_org_unit.map((row) => (
                <li key={String(row.org_unit_id)}>
                  {t("executive.byOrgUnit", {
                    unit: row.org_unit_id ?? t("executive.otherUnit"),
                    count: row.count,
                    confidence: f2(row.min_confidence),
                  })}
                </li>
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>

      <Card data-testid="executive-most-important" className={cardClass}>
        <CardHeader>
          <CardTitle>{t("executive.mostImportant")}</CardTitle>
        </CardHeader>
        <CardContent>
          {s.priorities.length === 0 ? (
            <p className="text-base">{t("executive.noItems")}</p>
          ) : (
            <ul className={big ? "space-y-2" : "space-y-1 text-sm"}>
              {s.priorities.slice(0, 10).map((row) => (
                <li key={row.item_id} data-testid="executive-priority" className={rowClass}>
                  <span className="min-w-0 truncate">{row.title}</span>
                  <span
                    className={
                      big
                        ? `${valueClass} flex shrink-0 items-center gap-2`
                        : "flex shrink-0 items-center gap-1"
                    }
                  >
                    {f2(row.confidence)}
                    {row.override ? (
                      <Badge variant="outline" className="ms-1">
                        {t("executive.override")}
                      </Badge>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card data-testid="executive-constrained" className={cardClass}>
        <CardHeader>
          <CardTitle>{t("executive.constrained")}</CardTitle>
        </CardHeader>
        <CardContent>
          {s.capacity_constraints.length === 0 ? (
            <p className="text-base">{t("executive.noItems")}</p>
          ) : (
            s.capacity_constraints.slice(0, 5).map((row) => (
              <p
                key={`${row.resource_id}-${row.week_start}`}
                data-testid="executive-constraint"
                className={rowClass}
              >
                <span className="min-w-0 truncate">
                  {String(row.resource_id).slice(0, 8)} ·{" "}
                  {new Date(row.week_start).toLocaleDateString()}
                </span>
                <Badge variant={BADGE_VARIANT[row.status] ?? "muted"}>{row.status}</Badge>
              </p>
            ))
          )}
        </CardContent>
      </Card>

      <Card data-testid="executive-at-risk" className={cardClass}>
        <CardHeader>
          <CardTitle>{t("executive.atRisk")}</CardTitle>
        </CardHeader>
        <CardContent>
          {atRiskList.length === 0 ? (
            <p className="text-base">{t("executive.noItems")}</p>
          ) : (
            <ul className={big ? "space-y-2" : "space-y-1 text-sm"}>
              {atRiskList.slice(0, 10).map((row) => (
                <li key={row.item_id} data-testid="executive-at-risk-row" className={rowClass}>
                  <span className="min-w-0 truncate">{row.title}</span>
                  <span className={big ? valueClass : "font-mono"}>{f2(row.confidence)}</span>
                </li>
              ))}
            </ul>
          )}
          {radar.filter((row) => atRiskIds.has(row.item_id)).length > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">{t("executive.riskRadar")}</p>
          ) : null}
        </CardContent>
      </Card>

      <Card data-testid="executive-outcomes" className={cardClass}>
        <CardHeader>
          <CardTitle>{t("executive.outcomes")}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-base">
            {t("executive.benefits", { count: s.strategic_outcomes.benefits_total })}
          </p>
          {s.strategic_outcomes.objectives.length === 0 ? (
            <p className="mt-1 text-base">{t("executive.noItems")}</p>
          ) : (
            <ul className={big ? "mt-2 space-y-2" : "space-y-1 text-sm"}>
              {s.strategic_outcomes.objectives.map((row) => (
                <li key={row.item_id} data-testid="executive-objective" className={rowClass}>
                  <span className="min-w-0 truncate">{row.title}</span>
                  <span className={big ? valueClass : "font-mono"}>{f2(row.confidence)}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card data-testid="executive-interventions" className={cardClass}>
        <CardHeader>
          <CardTitle>{t("executive.interventions")}</CardTitle>
        </CardHeader>
        <CardContent>
          {escalations.length === 0 ? (
            <p className="text-base">{t("executive.noItems")}</p>
          ) : (
            escalations.map((row) => (
              <p key={row.id} data-testid="executive-intervention" className={rowClass}>
                <span className="min-w-0 truncate">{row.root_cause}</span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {row.target_role} · {t("executive.dueIn", { days: daysUntil(row.due_at) })}
                </span>
              </p>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
