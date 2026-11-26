/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listAudit, verifyAudit } from "@/lib/api/audit";
import { problemMessage } from "@/lib/api";

export function AuditPage() {
  const { t } = useTranslation();
  const [action, setAction] = useState("");
  const [entityId, setEntityId] = useState("");
  const [audit, setAudit] = useState<any[]>([]);
  const [verification, setVerification] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    setError(null);
    try {
      const rows = await listAudit({
        action: action || undefined,
        entity_id: entityId || undefined,
      });
      setAudit(rows);
      const check = await verifyAudit();
      setVerification(check);
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{t("nav.audit")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("common.refresh")}</p>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={action}
          onChange={(event) => setAction(event.target.value)}
          placeholder={t("common.filter")}
          className="h-9 w-full rounded-md border bg-background px-3 text-sm sm:w-48"
        />
        <input
          value={entityId}
          onChange={(event) => setEntityId(event.target.value)}
          placeholder={t("common.entity")}
          className="h-9 w-full rounded-md border bg-background px-3 text-sm sm:w-64"
        />
        <Button size="sm" disabled={busy} onClick={() => void load()}>
          {t("common.refresh")}
        </Button>
      </div>

      {verification ? (
        <Card>
          <CardContent className="flex items-center justify-between gap-3">
            <span className="text-sm">
              {t("audit.rows", { count: verification.rows })} ·{" "}
              {verification.ok
                ? t("audit.chainOk")
                : t("audit.chainBroken", { at: verification.broken_at })}
            </span>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => void load()}>
              {t("audit.verify")}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("common.recent")}</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="text-left">#</th>
                <th className="text-left">{t("common.created")}</th>
                <th className="text-left">{t("common.actor")}</th>
                <th className="text-left">{t("common.action")}</th>
                <th className="text-left">{t("common.status")}</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((entry) => (
                <tr key={entry.seq} className="border-b border-border">
                  <td className="py-2 pl-2">{entry.seq}</td>
                  <td className="py-2">{entry.ts}</td>
                  <td className="py-2">{entry.actor_id ?? "-"}</td>
                  <td className="py-2 font-medium">{entry.action}</td>
                  <td className="py-2">
                    <Badge variant="muted">{entry.entity_type ?? ""}</Badge>
                  </td>
                </tr>
              ))}
              {audit.length === 0 && !busy ? (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-sm text-muted-foreground">
                    {t("common.noItems")}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
          <div className="mt-3 text-xs text-muted-foreground">
            {audit.slice(0, 3).map((entry) => (
              <div key={entry.seq} className="mt-1">
                {entry.hash?.slice(0, 16)}…
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
