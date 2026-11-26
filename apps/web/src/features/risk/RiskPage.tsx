import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  acknowledgeEscalation,
  getRiskRadar,
  listEscalations,
  type EscalationRow,
  type RadarRow,
} from "@/lib/api/risk";

function riskClass(riskScore: number): string {
  if (riskScore >= 0.8) return "text-destructive";
  if (riskScore >= 0.5) return "text-warning";
  return "text-success";
}

function daysUntil(dueAt: string): number {
  const ms = new Date(dueAt).getTime() - Date.now();
  return Math.ceil(ms / 86400000);
}

export function RiskPage() {
  const { t } = useTranslation();
  const { data: radar = [] } = useQuery({
    queryKey: ["risk", "radar"],
    queryFn: getRiskRadar,
  });
  const { data: escalations = [], refetch } = useQuery({
    queryKey: ["risk", "escalations"],
    queryFn: listEscalations,
  });

  const sortedRadar = useMemo(
    () => [...radar].sort((a, b) => b.risk_score - a.risk_score),
    [radar],
  );

  const acknowledge = (escalation: EscalationRow) => {
    void acknowledgeEscalation(escalation.id).then(() => void refetch());
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{t("risk.title")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("risk.subtitle")}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("risk.radar")}</CardTitle>
        </CardHeader>
        <CardContent>
          <table
            className="w-full text-sm"
            data-testid="risk-radar-table"
            aria-label={t("risk.radar")}
          >
            <caption className="sr-only">{t("risk.radar")}</caption>
            <thead>
              <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2.5 pr-4 font-medium" scope="col">
                  {t("risk.item")}
                </th>
                <th className="py-2.5 pr-4 font-medium" scope="col">
                  {t("risk.type")}
                </th>
                <th className="py-2.5 pr-4 font-medium text-right" scope="col">
                  {t("risk.confidence")}
                </th>
                <th className="py-2.5 pr-4 font-medium text-right" scope="col">
                  {t("risk.impact")}
                </th>
                <th className="py-2.5 pr-4 font-medium text-right" scope="col">
                  {t("risk.riskScore")}
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedRadar.map((row: RadarRow) => (
                <tr
                  key={row.item_id}
                  data-testid="risk-radar-row"
                  className="border-b last:border-b-0"
                >
                  <td className="py-3 pr-4 font-medium">{row.title}</td>
                  <td className="py-3 pr-4">
                    <Badge variant="outline">{row.type}</Badge>
                  </td>
                  <td className="py-3 pr-4 text-right font-mono">
                    {row.confidence === null ? "—" : `${Math.round(row.confidence * 100)}%`}
                  </td>
                  <td className="py-3 pr-4 text-right font-mono">{row.impact.toFixed(2)}</td>
                  <td className="py-3 pr-4 text-right font-semibold">
                    <span className={riskClass(row.risk_score)} data-testid="risk-score">
                      {row.risk_score.toFixed(2)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {sortedRadar.length === 0 ? (
            <p
              className="py-6 text-center text-sm text-muted-foreground"
              data-testid="risk-no-rows"
            >
              {t("risk.noRadar")}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("risk.escalations")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {escalations.map((escalation: EscalationRow) => (
            <div
              key={escalation.id}
              className="rounded border p-3 text-sm"
              data-testid="risk-escalation"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium">{escalation.root_cause}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {escalation.target_role}
                    {" · "}
                    {t("risk.due", { days: daysUntil(escalation.due_at) })}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={escalation.status === "acknowledged" ? "outline" : "destructive"}>
                    {escalation.status}
                  </Badge>
                  {escalation.status !== "acknowledged" ? (
                    <Button variant="outline" size="sm" onClick={() => acknowledge(escalation)}>
                      {t("risk.acknowledge")}
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
          {escalations.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              {t("risk.noEscalations")}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
