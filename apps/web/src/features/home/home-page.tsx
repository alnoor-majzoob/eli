import {
  Activity,
  Bot,
  CheckCircle2,
  Cpu,
  Database,
  HardDrive,
  KeyRound,
  ServerCog,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { SimBadge, SyntheticBadge } from "@/components/badges";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/lib/auth";
import { useHealth, usePlatformConfig, useReadiness } from "@/lib/platform";
import { cn } from "@/lib/utils";

const SYSTEM_LABELS: Record<string, string> = {
  m365: "Microsoft 365",
  p6: "Primavera P6",
  eam: "EAM / Maximo",
  erp: "ERP",
  hr: "HR",
};

const FOUNDATION_ITEMS = [
  "home.foundationIdentity",
  "home.foundationOutbox",
  "home.foundationObservability",
  "home.foundationClient",
  "home.foundationI18n",
] as const;

function StatCard({
  icon: Icon,
  label,
  value,
  detail,
  badge,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  detail: string;
  badge?: ReactNode;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex size-9 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <Icon className="size-4" />
          </div>
          {badge}
        </div>
        <p className="mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p className="mt-1 text-lg font-semibold">{value}</p>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{detail}</p>
      </CardContent>
    </Card>
  );
}

function StatusRow({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b py-2.5 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="flex items-center gap-2 text-sm font-medium">
        <span
          aria-hidden="true"
          className={cn("size-2 rounded-full", ok ? "bg-success" : "bg-warning")}
        />
        {value}
      </span>
    </div>
  );
}

export function HomePage() {
  const { principal } = useAuth();
  const { t, i18n } = useTranslation();
  const config = usePlatformConfig();
  const health = useHealth();
  const readiness = useReadiness();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const platform = config.data;
  const timeZone = platform?.tenant_timezone ?? "UTC";
  const asOf = new Intl.DateTimeFormat(i18n.resolvedLanguage === "ar" ? "ar" : "en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(now);

  const aiState = !platform
    ? t("status.checking")
    : !platform.ai_enabled
      ? t("home.aiOff")
      : platform.llm_mode === "replay"
        ? t("home.replay")
        : t("home.live");

  const databaseUp = readiness.data?.dependencies.database === "up";
  const apiHealthy = health.isSuccess && health.data?.status === "ok";

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-semibold tracking-tight" data-testid="home-title">
              {t("home.welcome", { name: principal?.name ?? "" })}
            </h2>
            <SyntheticBadge className="hidden sm:inline-flex" />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("home.subtitle")}</p>
        </div>
        <Badge variant="muted" className="w-fit">
          {t("home.asOf", { time: asOf })}
        </Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={Bot}
          label={t("home.aiModeTitle")}
          value={
            !platform
              ? t("status.checking")
              : platform.ai_enabled
                ? platform.llm_mode.toUpperCase()
                : t("status.unavailable")
          }
          detail={aiState}
          badge={
            platform && (!platform.ai_enabled || platform.llm_mode === "replay") ? (
              <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary">
                {platform.llm_mode.toUpperCase()}
              </Badge>
            ) : null
          }
        />
        <StatCard
          icon={Database}
          label={t("home.dataModeTitle")}
          value={platform ? platform.database.toUpperCase() : t("status.checking")}
          detail={`${platform?.object_store ?? ""} object store`}
          badge={<Badge variant="success">{t("badges.local")}</Badge>}
        />
        <StatCard
          icon={KeyRound}
          label={t("home.authModeTitle")}
          value={platform ? platform.auth_mode.toUpperCase() : t("status.checking")}
          detail={platform?.auth_mode === "oidc" ? t("home.authOidc") : t("home.authDev")}
          badge={<ShieldCheck className="size-4 text-success" />}
        />
        <StatCard
          icon={Cpu}
          label={t("home.phaseTitle")}
          value={t("common.phase", { number: 0 })}
          detail={t("home.nextBody")}
          badge={<Sparkles className="size-4 text-primary" />}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          <Card className="overflow-hidden">
            <div className="h-1 w-full bg-gradient-to-r from-primary via-teal-400 to-sky-400" />
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base">{t("home.phaseTitle")}</CardTitle>
                  <CardDescription className="mt-1">{t("home.phaseBody")}</CardDescription>
                </div>
                <Badge variant="success" className="shrink-0">
                  Online
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 sm:grid-cols-2">
                {FOUNDATION_ITEMS.map((item) => (
                  <div key={item} className="flex items-start gap-2.5 rounded-lg bg-muted/50 p-3">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
                    <span className="text-sm">{t(item)}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("home.systemsTitle")}</CardTitle>
              <CardDescription>{t("home.systemsBody")}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {platform?.simulated_systems.length ? (
                  platform.simulated_systems.map((system) => (
                    <div
                      key={system}
                      className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2 text-sm"
                    >
                      <ServerCog className="size-4 text-muted-foreground" />
                      <span>{SYSTEM_LABELS[system] ?? system}</span>
                      <SimBadge />
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">No simulated systems configured.</p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("home.statusTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <StatusRow
                label={t("home.apiStatus")}
                value={
                  health.isLoading
                    ? t("status.checking")
                    : apiHealthy
                      ? t("status.healthy")
                      : t("status.unavailable")
                }
                ok={apiHealthy}
              />
              <StatusRow
                label={t("home.databaseStatus")}
                value={
                  readiness.isLoading
                    ? t("status.checking")
                    : databaseUp
                      ? t("status.up")
                      : t("status.down")
                }
                ok={databaseUp}
              />
              <StatusRow
                label={t("home.objectStoreStatus")}
                value={platform?.object_store ?? t("status.checking")}
                ok={Boolean(platform)}
              />
              <StatusRow label={t("home.timezone")} value={timeZone} ok />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <HardDrive className="size-4 text-primary" />
                <CardTitle className="text-base">{t("home.nextTitle")}</CardTitle>
              </div>
              <CardDescription>{t("home.nextBody")}</CardDescription>
            </CardHeader>
          </Card>

          <Card className="bg-sidebar text-sidebar-foreground">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 text-xs text-sidebar-muted">
                <Activity className="size-3.5" />
                <span>{t("home.statusTitle")}</span>
              </div>
              <p className="mt-2 text-sm">
                {health.data?.app ?? "EIL"} · v{health.data?.version ?? "0.1.0"}
              </p>
              <p className="mt-1 text-xs text-sidebar-muted">
                {platform?.app_env ?? "local"} · {platform?.tenant_timezone ?? "UTC"}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
