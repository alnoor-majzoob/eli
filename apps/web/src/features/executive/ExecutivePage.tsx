import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getBenefitRollup, type BenefitRollupRow } from "@/lib/api/executive";
import { getExecutiveSummary } from "@/lib/api/executive";
import { getRiskRadar, listEscalations } from "@/lib/api/risk";
import { ExecutivePanels } from "./ExecutivePanels";

const f2 = (value: number | null) => (value === null ? "-" : value.toFixed(2));

function BenefitRollupPanel({ rollup }: { rollup: BenefitRollupRow[] }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base" data-testid="executive-benefit-rollup">
          {t("executive.benefitRollup")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {rollup.map((row) => (
          <div
            key={row.objective_id}
            className="space-y-1"
            data-testid="executive-benefit-rollup-row"
          >
            <div className="font-medium">{row.title}</div>
            <div className="text-xs text-muted-foreground">
              {t("executive.rollupKr", { count: row.kr_count })} ·{" "}
              {t("executive.rollupBenefits", { count: row.benefit_count })}
              {row.on_track ? "" : ` · ${t("executive.rollupBehind")}`}
            </div>
            <div className="text-xs text-muted-foreground">
              {t("executive.rollupActual", { value: f2(row.total_actual) })} ·{" "}
              {t("executive.rollupTarget", { value: f2(row.total_target) })} ·{" "}
              {t("executive.rollupForecast", { value: f2(row.total_forecast) })}
            </div>
          </div>
        ))}
        {rollup.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("executive.noItems")}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function ExecutivePage() {
  const { t } = useTranslation();
  const { data: summary } = useQuery({
    queryKey: ["executive", "summary"],
    queryFn: () => getExecutiveSummary(),
  });
  const { data: rollup = [] } = useQuery({
    queryKey: ["executive", "benefit-rollup"],
    queryFn: getBenefitRollup,
  });
  const { data: radar = [] } = useQuery({ queryKey: ["risk", "radar"], queryFn: getRiskRadar });
  const { data: escalations = [] } = useQuery({
    queryKey: ["risk", "escalations"],
    queryFn: listEscalations,
  });

  if (!summary) {
    return null;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight" data-testid="executive-title">
          {t("executive.title")}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("executive.subtitle")}</p>
      </div>
      <ExecutivePanels
        summary={summary}
        radar={radar}
        escalations={escalations}
        variant="compact"
      />
      <BenefitRollupPanel rollup={rollup} />
    </div>
  );
}
