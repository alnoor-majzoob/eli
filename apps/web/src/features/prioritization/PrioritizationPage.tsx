import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/api";
import { getPrioritization, requestOverride, type PrioritizedItem } from "@/lib/api/prioritization";
import { listUsers, type UserRead } from "@/lib/api/users";
import { useAuth } from "@/lib/auth";

const TIER_VARIANTS: Record<number, BadgeProps["variant"]> = {
  1: "success",
  2: "secondary",
  3: "warning",
  4: "muted",
};

const TIERS = [1, 2, 3, 4] as const;

function formatScore(score: number): string {
  return Number.isFinite(score) ? score.toFixed(2) : "";
}

function rationaleSummary(rationale: PrioritizedItem["rationale"]): string | null {
  if (!rationale) return null;
  const entries = Object.entries(rationale)
    .filter((entry): entry is [string, number] => typeof entry[1] === "number")
    .map(([key, value]) => `${key}: ${value}`)
    .join(", ");
  return entries.length > 0 ? entries : null;
}

export function PrioritizationPage() {
  const { t } = useTranslation();
  const { principal } = useAuth();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [tier, setTier] = useState<string>("2");
  const [justification, setJustification] = useState("");
  const [approverId, setApproverId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [overriddenIds, setOverriddenIds] = useState<Set<string>>(new Set());

  const { data: users = [], isLoading: usersLoading } = useQuery({
    queryKey: ["users"],
    queryFn: () => listUsers(),
  });
  const {
    data,
    isLoading,
    refetch,
    error: boardError,
  } = useQuery({
    queryKey: ["prioritization"],
    queryFn: () => getPrioritization(),
  });
  const items: PrioritizedItem[] = data ?? [];

  const defaultApproverId = useMemo(
    () => users.find((user) => user.subject === principal?.subject)?.id ?? users[0]?.id ?? "",
    [users, principal?.subject],
  );
  const selectedApproverId = approverId || defaultApproverId;

  const submitOverride = (item: PrioritizedItem) => {
    setError(null);
    const approver = users.find((user) => user.id === selectedApproverId);
    if (!approver) {
      setError(t("prioritization.override.noApprover"));
      return;
    }
    void (async () => {
      try {
        await requestOverride(item.id, {
          tier: Number(tier),
          justification: justification.trim(),
          approver_id: approver.id,
        });
        setOverriddenIds((prev) => new Set(prev).add(item.id));
        setExpandedId(null);
        setJustification("");
        setApproverId("");
        await refetch();
      } catch (cause) {
        setError(problemMessage(cause, t("common.error")));
      }
    })();
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{t("prioritization.title")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("prioritization.subtitle")}</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => void refetch()} disabled={isLoading}>
          <RefreshCw className="size-3.5" />
          {t("common.refresh")}
        </Button>
      </div>

      {boardError ? (
        <p role="alert" className="text-sm text-destructive">
          {problemMessage(boardError, t("common.error"))}
        </p>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("prioritization.cutLineInfo")}</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm" data-testid="prioritization-table">
            <thead>
              <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2.5 pr-4 font-medium" />
                <th className="py-2.5 pr-4 font-medium">{t("prioritization.rank")}</th>
                <th className="py-2.5 pr-4 font-medium">{t("prioritization.type")}</th>
                <th className="py-2.5 pr-4 font-medium">{t("prioritization.title")}</th>
                <th className="py-2.5 pr-4 font-medium">{t("prioritization.score")}</th>
                <th className="py-2.5 pr-4 font-medium">{t("prioritization.tier")}</th>
                <th className="py-2.5 pr-4 font-medium">{t("prioritization.rationale")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => {
                const summary = rationaleSummary(item.rationale);
                const isExpanded = expandedId === item.id;
                return (
                  <tr
                    key={item.id}
                    data-testid="prioritization-row"
                    className="border-b last:border-b-0"
                  >
                    <td className="py-3 pr-4">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7"
                        onClick={() => {
                          setExpandedId(isExpanded ? null : item.id);
                          setError(null);
                        }}
                        aria-expanded={isExpanded}
                        aria-label={t("prioritization.toggleOverride", { title: item.title })}
                      >
                        {isExpanded ? (
                          <ChevronUp className="size-3.5" />
                        ) : (
                          <ChevronDown className="size-3.5" />
                        )}
                      </Button>
                    </td>
                    <td className="py-3 pr-4 text-muted-foreground">{index + 1}</td>
                    <td className="py-3 pr-4">
                      <Badge variant="outline">{item.type}</Badge>
                    </td>
                    <td className="py-3 pr-4">
                      <Link to={`/items/${item.id}`} className="font-medium hover:underline">
                        {item.title}
                      </Link>
                      {item.in_cut_line ? (
                        <Badge variant="warning" className="ms-2">
                          {t("prioritization.cutLineBadge")}
                        </Badge>
                      ) : null}
                      {overriddenIds.has(item.id) ? (
                        <Badge variant="outline" className="ms-2">
                          {t("prioritization.override.applied")}
                        </Badge>
                      ) : null}
                    </td>
                    <td className="py-3 pr-4 font-mono">{formatScore(item.score)}</td>
                    <td className="py-3 pr-4">
                      <Badge variant={TIER_VARIANTS[item.tier] ?? "muted"}>
                        {t("prioritization.tier", { n: item.tier })}
                      </Badge>
                    </td>
                    <td className="py-3 pr-4 text-muted-foreground">
                      {summary ? <span className="whitespace-nowrap">{summary}</span> : null}
                    </td>
                    {isExpanded ? (
                      <td colSpan={6} className="py-3">
                        <div
                          data-testid="prioritization-override-form"
                          className="space-y-3 rounded-md border bg-muted/30 p-4"
                        >
                          <div className="flex flex-wrap items-center gap-4">
                            <label className="flex items-center gap-2 text-xs font-medium">
                              {t("prioritization.override.tier")}
                              <select
                                value={tier}
                                onChange={(event) => setTier(event.target.value)}
                                className="h-8 rounded-md border bg-background px-2 text-xs"
                              >
                                {TIERS.map((value) => (
                                  <option key={value} value={value}>
                                    {t("prioritization.tier", { n: value })}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="flex items-center gap-2 text-xs font-medium">
                              {t("prioritization.override.approver")}
                              <select
                                value={selectedApproverId}
                                onChange={(event) => setApproverId(event.target.value)}
                                disabled={users.length === 0 || usersLoading}
                                className="h-8 rounded-md border bg-background px-2 text-xs"
                              >
                                {users.map((user: UserRead) => (
                                  <option key={user.id} value={user.id}>
                                    {user.name} ({user.subject})
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>
                          <input
                            value={justification}
                            onChange={(event) => setJustification(event.target.value)}
                            placeholder={t("prioritization.override.justificationPlaceholder")}
                            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                            aria-label={t("prioritization.override.justification")}
                          />
                          {error ? (
                            <p role="alert" className="text-sm text-destructive">
                              {error}
                            </p>
                          ) : null}
                          <div className="flex items-center gap-2">
                            <Button
                              size="sm"
                              disabled={!justification.trim() || users.length === 0}
                              onClick={() => submitOverride(item)}
                            >
                              {t("prioritization.override.submit")}
                            </Button>
                            <Button variant="ghost" size="sm" onClick={() => setExpandedId(null)}>
                              {t("prioritization.override.cancel")}
                            </Button>
                          </div>
                        </div>
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {items.length === 0 ? (
            <p
              data-testid="prioritization-empty"
              className="py-8 text-center text-sm text-muted-foreground"
            >
              {t("prioritization.noItems")}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
