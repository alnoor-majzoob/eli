/* eslint-disable @typescript-eslint/no-explicit-any */
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getDashboard } from "@/lib/api/dashboard";
import { listInbox } from "@/lib/api/approvals";
import { cn } from "@/lib/utils";

function StatCard({
  label,
  value,
  className,
}: {
  label: string;
  value: number | string;
  className?: string;
}) {
  return (
    <Card className="transition-colors hover:border-primary/40">
      <CardContent className={cn("flex flex-col gap-1 p-5", className)}>
        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p className="text-2xl font-bold">{value}</p>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: () => getDashboard(),
  });
  const { data: inbox, isLoading: approvalsLoading } = useQuery({
    queryKey: ["approvals", "inbox"],
    queryFn: () => listInbox(),
  });

  const byType: Record<string, number> = data?.by_type ?? {};
  const rag: Record<string, number> = data?.rag ?? {};
  const pendingApprovals = inbox?.items?.length ?? 0;

  if (isLoading) {
    return (
      <div className="py-16 text-center text-sm text-muted-foreground">{t("common.loading")}</div>
    );
  }
  if (error) {
    return <div className="py-16 text-center text-sm text-destructive">{t("common.error")}</div>;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-2xl font-semibold tracking-tight" data-testid="overview-title">
          {t("home.title")}
        </h2>
        <Badge variant="muted">{t("common.asOf", { time: data?.as_of ?? "" })}</Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label={t("home.total")} value={data?.total ?? 0} />
        <StatCard label={t("home.overdue")} value={data?.overdue ?? 0} />
        <StatCard label={t("home.pendingApprovals")} value={pendingApprovals} />
        <StatCard
          label={t("home.rag")}
          value={`G${rag.green ?? 0} A${rag.amber ?? 0} R${rag.red ?? 0}`}
        />
        <StatCard label={t("nav.objectives")} value={byType.objective ?? 0} />
        <StatCard label={t("nav.demand")} value={byType.demand ?? 0} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("nav.demands")}</CardTitle>
          </CardHeader>
          <CardContent>
            {data?.pending_demands?.length ? (
              <ul className="space-y-2">
                {data.pending_demands.slice(0, 10).map((item: any) => (
                  <li key={item.id} className="flex items-center justify-between text-sm">
                    <span>{item.title}</span>
                    <Badge variant="warning">{item.status}</Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t("common.noItems")}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("home.upcoming")}</CardTitle>
          </CardHeader>
          <CardContent>
            {data?.upcoming_milestones?.length ? (
              <ul className="space-y-2">
                {data.upcoming_milestones.slice(0, 10).map((item: any) => (
                  <li key={item.id} className="text-sm">
                    {item.title} · {item.planned_end}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t("common.noItems")}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("nav.approvals")}</CardTitle>
          </CardHeader>
          <CardContent>
            {approvalsLoading ? <p className="text-sm">{t("common.loading")}</p> : null}
            {inbox?.items?.length ? (
              <ul className="space-y-2">
                {inbox.items.slice(0, 10).map((approval: any) => (
                  <li key={approval.id} className="text-sm">
                    {approval.work_item_id} · {approval.approver_role}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t("common.noItems")}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("home.recent")}</CardTitle>
        </CardHeader>
        <CardContent>
          {data?.recent_items?.length ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  <th className="text-left">{t("common.type")}</th>
                  <th className="text-left">{t("common.title")}</th>
                  <th className="text-right">{t("common.status")}</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_items.slice(0, 20).map((item: any) => (
                  <tr key={item.id} className="border-b border-border">
                    <td className="py-2">{item.type}</td>
                    <td className="py-2">
                      <Link to={`/items/${item.id}`} className="text-primary hover:underline">
                        {item.title}
                      </Link>
                    </td>
                    <td className="py-2 text-right">
                      <Badge variant="muted">{item.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">{t("common.noItems")}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
