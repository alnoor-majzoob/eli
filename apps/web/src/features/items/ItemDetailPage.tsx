/* eslint-disable @typescript-eslint/no-explicit-any */
import { Pencil, Trash2, TriangleAlert, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { Can } from "@/components/permission";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/api";
import { getItem, updateItem, deleteItem, submitItem, listLinks, deleteLink } from "@/lib/api/items";
import { listAudit } from "@/lib/api/audit";
import { PERMISSIONS, usePermissions } from "@/lib/permissions";

export function ItemDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { can } = usePermissions();
  const canEdit = can(PERMISSIONS.WORK_EDIT);
  const canViewAudit = can(PERMISSIONS.AUDIT_VIEW);
  const [item, setItem] = useState<any>(null);
  const [links, setLinks] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const displayTitle = item ? item.title : title;

  useEffect(() => {
    let active = true;
    if (!id) return;
    void (async () => {
      const [itemData, linksData, auditData] = await Promise.allSettled([
        getItem(id),
        listLinks(id),
        canViewAudit
          ? listAudit({ entity_id: id, entity_type: "work_item" })
          : Promise.resolve([]),
      ]);
      if (!active) return;
      setItem(itemData.status === "fulfilled" ? itemData.value : null);
      setLinks(linksData.status === "fulfilled" ? linksData.value : []);
      setAudit(auditData.status === "fulfilled" ? auditData.value : []);
      if (itemData.status === "fulfilled" && itemData.value) setTitle(itemData.value.title);
    });
    return () => {
      active = false;
    };
  }, [id, canViewAudit]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      const next = await getItem(id!);
      setItem(next);
      setTitle(next.title);
      setLinks(await listLinks(id!));
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    } finally {
      setBusy(false);
    }
  };

  if (!item) {
    return (
      <div className="py-16 text-center text-sm text-muted-foreground">
        {error ?? t("common.loading")}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{displayTitle}</h2>
          <div className="flex items-center gap-2">
            <Badge variant="muted">{item.type}</Badge>
            <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
          </div>
        </div>
        <Button variant="outline" onClick={() => void navigate(-1)}>
          {t("common.actions")}
        </Button>
      </div>

      {error ? (
        <p role="alert" className="flex items-center gap-2 text-sm text-destructive">
          <TriangleAlert className="size-4" />
          {error}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("common.title")}</CardTitle>
            </CardHeader>
            <CardContent>
              {canEdit ? (
                <>
                  <input
                    value={displayTitle}
                    onChange={(event) => setTitle(event.target.value)}
                    className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                  />
                  <Button
                    size="sm"
                    className="mt-3"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        await updateItem(id!, { title: title.trim() });
                      })
                    }
                  >
                    <Pencil className="size-3.5" />
                    {t("common.edit")}
                  </Button>
                </>
              ) : (
                <p className="text-sm">{displayTitle}</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("common.links")}</CardTitle>
            </CardHeader>
            <CardContent>
              {links.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("common.noItems")}</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {links.map((link) => (
                    <li
                      key={link.id}
                      className="flex items-center justify-between rounded-md border p-2"
                    >
                      <span className="text-xs uppercase tracking-wide text-muted-foreground">
                        {link.link_type}
                      </span>
                      <span className="text-sm">{link.dst_id}</span>
                      {canEdit ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t("common.delete")}
                          disabled={busy}
                          onClick={() =>
                            void run(async () => {
                              await deleteLink(id!, link.id);
                            })
                          }
                        >
                          <X className="size-3.5" />
                        </Button>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("common.status")}</CardTitle>
            </CardHeader>
            <CardContent>
              {canEdit ? (
                <>
                  <div className="flex flex-wrap gap-2">
                    {["active", "on_hold", "completed", "cancelled"].map((next) => (
                      <Button
                        key={next}
                        variant="outline"
                        size="sm"
                        disabled={busy || next === item.status}
                        onClick={() =>
                          void run(async () => {
                            await updateItem(id!, { status: next });
                          })
                        }
                      >
                        {next}
                      </Button>
                    ))}
                  </div>
                  <div className="mt-3">
                    <Button
                      size="sm"
                      disabled={busy || item.status !== "draft"}
                      onClick={() => void run(() => submitItem(id!))}
                    >
                      {t("common.submit")}
                    </Button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{t("forbidden.readOnly")}</p>
              )}
            </CardContent>
          </Card>

          {canViewAudit ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("common.recent")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm">
                {audit.map((entry) => (
                  <li key={entry.seq} className="rounded-md border p-2 text-xs">
                    <span className="font-semibold">{entry.action}</span>
                    {entry.reason ? <span className="ml-2">{entry.reason}</span> : null}
                  </li>
                ))}
                {audit.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t("common.noItems")}</p>
                ) : null}
              </ul>
            </CardContent>
          </Card>
          ) : null}
        </div>

        <Can permission={PERMISSIONS.WORK_EDIT}>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("common.actions")}</CardTitle>
            </CardHeader>
            <CardContent>
              <Button
                variant="destructive"
                size="sm"
                disabled={busy}
                onClick={() => {
                  if (!window.confirm(t("common.confirmDelete"))) return;
                  void run(async () => {
                    const errorData = await deleteItem(id!);
                    if (errorData) throw new Error(String(errorData));
                    void navigate("/");
                  });
                }}
              >
                <Trash2 className="size-3.5" />
                {t("common.delete")}
              </Button>
            </CardContent>
          </Card>
        </Can>
      </div>
    </div>
  );
}

function statusVariant(status: string): BadgeProps["variant"] {
  if (status === "active" || status === "approved" || status === "completed") return "success";
  if (status === "rejected" || status === "cancelled") return "destructive";
  if (status === "draft") return "muted";
  return "warning";
}
