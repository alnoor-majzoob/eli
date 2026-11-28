/* eslint-disable @typescript-eslint/no-explicit-any */
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, Link } from "react-router-dom";

import { Can } from "@/components/permission";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/api";
import { createItem, listItemsPage, submitItem, updateItemStatus } from "@/lib/api/items";
import { PERMISSIONS, usePermissions } from "@/lib/permissions";

export interface ItemsPageProps {
  type: string;
  titleKey: string;
  createTitleKey: string;
}

export function ItemsPage({ type, titleKey, createTitleKey }: ItemsPageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { can } = usePermissions();
  const canEdit = can(PERMISSIONS.WORK_EDIT);
  const canSubmit = can(PERMISSIONS.WORK_EDIT) || can(PERMISSIONS.DEMAND_CREATE);
  // Demand-type creation needs demand.create; everything else needs work.edit.
  const createPermission =
    type === "demand" ? PERMISSIONS.DEMAND_CREATE : PERMISSIONS.WORK_EDIT;
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [parentId, setParentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["items", type],
    queryFn: () => listItemsPage({ type }),
  });
  const items: any[] = data?.items ?? [];
  const total = data?.total ?? 0;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refetch();
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    await run(async () => {
      const response = await createItem({
        type,
        title: title.trim(),
        description: description.trim() || null,
        parent_id: parentId || null,
      });
      if (response.id) {
        setTitle("");
        setDescription("");
        setParentId("");
        void navigate(`/items/${response.id}`);
      } else if (response.detail) {
        throw new Error(String(response.detail));
      }
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{t(titleKey)}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t(createTitleKey)}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isLoading}>
          <RefreshCw className="size-3.5" />
          {t("common.refresh")}
        </Button>
      </div>

      <Can permission={createPermission}>
        <Card>
        <CardHeader>
          <CardTitle className="text-base">{t(createTitleKey)}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={t("common.createItemTitle")}
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
          />
          <input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder={t("common.description")}
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
          />
          <input
            value={parentId}
            onChange={(event) => setParentId(event.target.value)}
            placeholder={t("common.parentId")}
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
          />
          <Button size="sm" disabled={busy || !title.trim()} onClick={() => void create()}>
            {t("common.create")}
          </Button>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
        </CardContent>
        </Card>
      </Can>

      <div className="space-y-3">
        {items.map((item: any) => (
          <WorkItemSummaryCard
            key={item.id}
            item={item}
            canEdit={canEdit}
            canSubmit={canSubmit}
            onStatus={(item, status) =>
              run(async () => {
                await updateItemStatus(item.id, status);
              })
            }
            onSubmit={(item) =>
              run(async () => {
                const response = await submitItem(item.id);
                if (response.code) throw new Error(String(response.detail));
              })
            }
          />
        ))}
        {items.length === 0 && !isLoading ? <EmptyItems /> : null}
      </div>

      <p className="text-xs text-muted-foreground">{t("common.totalItems", { count: total })}</p>
    </div>
  );
}

function WorkItemSummaryCard({
  item,
  canEdit = false,
  canSubmit = false,
  onStatus,
  onSubmit,
}: {
  item: any;
  canEdit?: boolean;
  canSubmit?: boolean;
  onStatus: (item: any, status: string) => void;
  onSubmit: (item: any) => void;
}) {
  const { t } = useTranslation();
  const writable = (canEdit || canSubmit) && ["draft", "submitted", "active", "on_hold"].includes(item.status);
  return (
    <Card className="overflow-hidden">
      <div className="h-1 w-full bg-gradient-to-r from-border via-primary/40 to-border" />
      <CardContent className="pt-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0 space-y-1">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-semibold">{item.title}</span>
              <Badge variant={statusVariant(item.status)}>{item.status}</Badge>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{item.type}</span>
              {item.planned_end ? <span>{item.planned_end}</span> : null}
              <Link
                to={`/items/${item.id}`}
                className="inline-flex items-center gap-1 rounded text-primary hover:underline"
              >
                <ExternalLink className="size-3" />
                {t("common.view")}
              </Link>
            </div>
          </div>
          {writable ? (
            <div className="flex items-center gap-2">
              {item.status === "submitted" ? (
                canSubmit ? (
                <Button size="sm" variant="outline" onClick={() => onSubmit(item)}>
                  {t("common.submit")}
                </Button>
                ) : null
              ) : (
                canEdit &&
                item.status !== "approved" &&
                item.status !== "completed" && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onStatus(item, nextStatus(item.status))}
                  >
                    {nextStatus(item.status)}
                  </Button>
                )
              )}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyItems() {
  const { t } = useTranslation();
  return <p className="py-6 text-sm text-muted-foreground">{t("common.noItems")}</p>;
}

function nextStatus(status: string): string {
  if (status === "draft") return "active";
  if (status === "active" || status === "on_hold" || status === "submitted") return "completed";
  return status;
}

function statusVariant(status: string): BadgeProps["variant"] {
  if (status === "active" || status === "approved" || status === "completed") return "success";
  if (status === "completed") return "success";
  if (status === "draft") return "muted";
  if (status === "rejected" || status === "cancelled") return "destructive";
  return "warning";
}
