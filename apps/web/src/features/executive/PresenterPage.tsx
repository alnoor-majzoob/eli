import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Square } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { getExecutiveSummary } from "@/lib/api/executive";
import { getRiskRadar, listEscalations } from "@/lib/api/risk";
import { ExecutivePanels } from "./ExecutivePanels";

const AUTO_REFRESH_MS = 5000;

export function PresenterPage() {
  const { t } = useTranslation();
  const [asOf, setAsOf] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const asOfIso = asOf ? new Date(asOf).toISOString() : undefined;
  const refreshKey = asOfIso ?? "now";

  const { data: summary } = useQuery({
    queryKey: ["executive", "summary", "presenter", refreshKey],
    queryFn: () => getExecutiveSummary(asOfIso),
    refetchInterval: autoRefresh ? AUTO_REFRESH_MS : false,
  });
  const { data: radar = [] } = useQuery({
    queryKey: ["risk", "radar", "presenter", refreshKey],
    queryFn: getRiskRadar,
    refetchInterval: autoRefresh ? AUTO_REFRESH_MS : false,
  });
  const { data: escalations = [] } = useQuery({
    queryKey: ["risk", "escalations", "presenter", refreshKey],
    queryFn: listEscalations,
    refetchInterval: autoRefresh ? AUTO_REFRESH_MS : false,
  });

  return (
    <div className="min-h-screen space-y-8 p-6 lg:p-12" data-testid="presenter-view">
      <header className="space-y-3 border-b pb-6">
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="text-4xl font-bold tracking-tight" data-testid="presenter-title">
            {t("executive.presenterTitle")}
          </h1>
          <label
            htmlFor="presenter-as-of"
            className="text-2xl font-semibold"
            data-testid="presenter-as-of-label"
          >
            {t("executive.presenterAsOfLabel")}
          </label>
          <input
            id="presenter-as-of"
            data-testid="presenter-as-of-input"
            type="datetime-local"
            value={asOf}
            onChange={(event) => setAsOf(event.target.value)}
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            aria-label={t("executive.presenterAsOfLabel")}
          />
          <Button data-testid="presenter-as-of-now" onClick={() => setAsOf("")}>
            {t("executive.presenterAsOfNow")}
          </Button>
          <Button
            data-testid="presenter-auto-refresh"
            variant={autoRefresh ? "default" : "outline"}
            onClick={() => setAutoRefresh((value) => !value)}
          >
            {autoRefresh ? <Square className="size-4" /> : <RefreshCw className="size-4" />}
            {autoRefresh
              ? t("executive.presenterAutoRefreshStop")
              : t("executive.presenterAutoRefresh")}
          </Button>
        </div>
        <p className="text-lg text-muted-foreground">{t("executive.presenterSubtitle")}</p>
        <p
          className="flex flex-wrap items-center gap-2 text-lg"
          data-testid="presenter-as-of-value"
        >
          {t("executive.presenterAsOfValue", {
            date: summary ? new Date(summary.as_of).toLocaleString() : t("common.loading"),
          })}
        </p>
        <p className="text-sm text-muted-foreground">{t("executive.presenterReplayHelp")}</p>
      </header>

      {summary ? (
        <ExecutivePanels
          summary={summary}
          radar={radar}
          escalations={escalations}
          variant="presenter"
        />
      ) : (
        <p className="text-base text-muted-foreground">{t("common.loading")}</p>
      )}
    </div>
  );
}
