/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { decideApproval, listInbox } from "@/lib/api/approvals";
import { problemMessage } from "@/lib/api";

export function ApprovalsPage() {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["approvals", "inbox"],
    queryFn: () => listInbox(),
  });
  const approvals: any[] = data?.items ?? data?.data ?? [];

  const decide = async (approval: any, decision: "approved" | "rejected") => {
    setBusy(true);
    setError(null);
    try {
      const errorData = await decideApproval(approval.id, decision, comment || undefined);
      if (errorData) throw new Error(String(errorData));
      setComment("");
      await refetch();
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{t("nav.approvals")}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t("common.actions")}</p>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("common.recent")}</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="text-left">{t("common.title")}</th>
                <th className="text-left">{t("common.status")}</th>
                <th className="text-left">{t("common.type")}</th>
                <th className="text-right">{t("common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((approval) => (
                <tr key={approval.id} className="border-b border-border">
                  <td className="py-2 text-sm font-medium">{approval.work_item_id ?? "-"}</td>
                  <td className="py-2">
                    <Badge variant="warning">{approval.status}</Badge>
                  </td>
                  <td className="py-2">{approval.approver_role}</td>
                  <td className="py-2 text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => decide(approval, "approved")}
                    >
                      {t("common.approve")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      onClick={() => decide(approval, "rejected")}
                    >
                      {t("common.reject")}
                    </Button>
                  </td>
                </tr>
              ))}
              {approvals.length === 0 && !isLoading ? (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-sm text-muted-foreground">
                    {t("common.noItems")}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
          <input
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder={t("common.comment")}
            className="mt-3 h-9 w-full rounded-md border bg-background px-3 text-sm"
          />
          <div className="mt-3">
            <Button
              size="sm"
              variant="outline"
              disabled={busy || approvals.length === 0}
              onClick={() => void refetch()}
            >
              {t("common.refresh")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
