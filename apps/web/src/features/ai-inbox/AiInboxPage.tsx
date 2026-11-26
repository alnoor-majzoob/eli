import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { problemMessage } from "@/lib/api";
import {
  acceptAiSuggestion,
  bulkAiSuggestions,
  getAiSuggestionDetail,
  listAiSuggestions,
  rejectAiSuggestion,
  type AiSuggestion,
  type AiSuggestionDetail,
} from "@/lib/api/ai";
import { cn } from "@/lib/utils";

const KIND_BADGE: Record<string, BadgeProps["variant"]> = {
  extracted_item: "muted",
  link: "outline",
  duplicate: "outline",
  classification: "muted",
  owner: "muted",
};

export function AiInboxPage() {
  const { t } = useTranslation();
  const [statusFilter, setStatusFilter] = useState("pending");
  const [kindFilter, setKindFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: suggestions = [], refetch } = useQuery({
    queryKey: ["ai", "suggestions", statusFilter, kindFilter],
    queryFn: () =>
      listAiSuggestions({ status: statusFilter || undefined, kind: kindFilter || undefined }),
  });

  const detailQuery = useQuery({
    queryKey: ["ai", "detail", selectedId],
    queryFn: () => getAiSuggestionDetail(selectedId!),
    enabled: !!selectedId,
  });

  const visible = useMemo(
    () => suggestions.filter((suggestion) => !kindFilter || suggestion.kind === kindFilter),
    [suggestions, kindFilter],
  );

  const guarded = async (fn: () => Promise<unknown>, onError: (message: string) => void) => {
    setError(null);
    try {
      await fn();
    } catch (cause) {
      onError(problemMessage(cause, t("common.error")));
    }
    await refetch();
  };

  const accept = (suggestion: AiSuggestion) =>
    void guarded(async () => {
      await acceptAiSuggestion(suggestion.id);
      setSelectedId(suggestion.id);
    }, setError);

  const reject = (suggestion: AiSuggestion) =>
    void guarded(async () => {
      const reason = window.prompt(t("aiInbox.rejectReason"));
      if (reason !== null && reason.trim()) {
        await rejectAiSuggestion(suggestion.id, reason);
      }
    }, setError);

  const editAndAccept = (suggestion: AiSuggestion) =>
    void guarded(async () => {
      const edits = window.prompt(
        t("aiInbox.editAndAccept"),
        JSON.stringify(suggestion.payload, null, 2),
      );
      if (edits !== null) {
        await acceptAiSuggestion(suggestion.id, parseEdits(edits));
        setSelectedId(suggestion.id);
      }
    }, setError);

  const bulkReject = async () => {
    const ids = [...checked];
    if (!ids.length) return;
    setBusyId("bulk");
    try {
      await bulkAiSuggestions(ids.map((id) => ({ suggestion_id: id, action: "reject" as const })));
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    } finally {
      setBusyId(null);
      setChecked(new Set());
      await refetch();
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">{t("aiInbox.title")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{t("aiInbox.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="h-8 rounded-md border bg-background px-2 text-xs"
            aria-label={t("aiInbox.filters")}
          >
            <option value="pending">{t("aiInbox.pending")}</option>
            <option value="accepted">{t("aiInbox.accepted")}</option>
            <option value="rejected">{t("aiInbox.rejected")}</option>
            <option value="">{t("aiInbox.all")}</option>
          </select>
          <select
            value={kindFilter}
            onChange={(event) => setKindFilter(event.target.value)}
            className="h-8 rounded-md border bg-background px-2 text-xs"
            aria-label={t("aiInbox.kindFilter")}
          >
            <option value="">{t("aiInbox.all")}</option>
            {["extracted_item", "link", "duplicate", "classification", "owner"].map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            {t("common.refresh")}
          </Button>
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("aiInbox.suggestions")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            <Button
              size="sm"
              variant="outline"
              onClick={() => void bulkReject()}
              disabled={checked.size === 0 || busyId !== null}
            >
              {t("aiInbox.bulkReject")} ({checked.size})
            </Button>
            {visible.length === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">{t("aiInbox.noSuggestions")}</p>
            ) : null}
            <div className="space-y-2">
              {visible.map((suggestion) => (
                <SuggestionCard
                  key={suggestion.id}
                  suggestion={suggestion}
                  selected={selectedId === suggestion.id}
                  checked={checked.has(suggestion.id)}
                  busy={busyId === suggestion.id}
                  onClick={() => setSelectedId(suggestion.id)}
                  onAccept={() => accept(suggestion)}
                  onReject={() => reject(suggestion)}
                  onEditAndAccept={() => editAndAccept(suggestion)}
                  onToggle={() =>
                    setChecked((prev) => {
                      const next = new Set(prev);
                      if (next.has(suggestion.id)) next.delete(suggestion.id);
                      else next.add(suggestion.id);
                      return next;
                    })
                  }
                />
              ))}
            </div>
          </CardContent>
        </Card>

        {selectedId && detailQuery.data ? (
          <SuggestionDetail detail={detailQuery.data} onClose={() => setSelectedId(null)} />
        ) : null}
      </div>
    </div>
  );
}

function parseEdits(edits: string): Record<string, unknown> | undefined {
  try {
    const parsed = JSON.parse(edits) as Record<string, unknown>;
    return Object.keys(parsed).length ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function SuggestionCard({
  suggestion,
  selected,
  checked,
  busy,
  onClick,
  onAccept,
  onReject,
  onEditAndAccept,
  onToggle,
}: {
  suggestion: AiSuggestion;
  selected: boolean;
  checked: boolean;
  busy: boolean;
  onClick: () => void;
  onAccept: () => void;
  onReject: () => void;
  onEditAndAccept: () => void;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const payload = suggestion.payload as Record<string, string | null>;
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={payload?.title ? payload.title : t("aiInbox.suggestions")}
      className={cn(
        "cursor-pointer rounded-lg border p-3 transition-colors",
        selected ? "border-primary bg-primary/5" : "hover:bg-muted/40",
      )}
      onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      }}
    >
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          aria-label={t("aiInbox.selectForBulk")}
          checked={checked}
          onChange={() => onToggle()}
          onClick={(event) => event.stopPropagation()}
          className="size-3.5"
        />
        <Badge variant={KIND_BADGE[suggestion.kind] ?? "muted"}>{suggestion.kind}</Badge>
        <span className="truncate font-medium">{payload?.title ?? ""}</span>
        {suggestion.confidence != null ? (
          <span className="text-[10px] text-muted-foreground">
            {Math.round(suggestion.confidence * 100)}%
          </span>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        <Button
          size="sm"
          variant="outline"
          onClick={(event) => {
            event.stopPropagation();
            onAccept();
          }}
          disabled={busy}
        >
          {t("common.approve")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={(event) => {
            event.stopPropagation();
            onEditAndAccept();
          }}
          disabled={busy}
        >
          {t("aiInbox.editAndAccept")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={(event) => {
            event.stopPropagation();
            onReject();
          }}
          disabled={busy}
        >
          {t("aiInbox.reject")}
        </Button>
      </div>
      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{payload?.summary ?? ""}</p>
    </div>
  );
}

function SuggestionDetail({
  detail,
  onClose,
}: {
  detail: AiSuggestionDetail;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Card className="max-h-[70vh] overflow-y-auto">
      <CardHeader className="space-y-1 pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm">
            {(detail.payload as Record<string, string>)?.title ?? ""}
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t("common.close")}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-0 text-xs">
        <div className="flex flex-wrap gap-1">
          <Badge variant={KIND_BADGE[detail.kind] ?? "muted"}>{detail.kind}</Badge>
          <Badge variant="muted">{detail.status}</Badge>
          {detail.confidence != null ? (
            <Badge variant="outline">{Math.round(detail.confidence * 100)}%</Badge>
          ) : null}
          {detail.evidence?.quote ? (
            <Badge variant="outline" title={String(detail.evidence.quote)}>
              {t("aiInbox.evidence")}
            </Badge>
          ) : null}
        </div>
        {detail.evidence?.quote ? (
          <QuoteBlock text={String(detail.evidence.quote)} label={t("aiInbox.evidence")} />
        ) : null}
        {detail.source_excerpt ? (
          <QuoteBlock text={detail.source_excerpt} label={t("aiInbox.sourceExcerpt")} />
        ) : null}
        <div className="grid gap-1.5 sm:grid-cols-2">
          <MetaRow label={t("aiInbox.model")} value={detail.model} />
          <MetaRow label={t("aiInbox.promptVersion")} value={detail.prompt_version} />
          <MetaRow label={t("aiInbox.acceptedBy")} value={detail.reviewer_name ?? "—"} />
          <MetaRow label={t("aiInbox.created")} value={detail.created_at} />
          {detail.review_reason ? (
            <MetaRow label={t("aiInbox.rejectReason")} value={detail.review_reason} />
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function QuoteBlock({ text, label }: { text: string; label?: string }) {
  return (
    <div className="rounded-md border bg-muted/30 p-2">
      {label ? (
        <div className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">
          {label}
        </div>
      ) : null}
      <p className="text-xs text-muted-foreground">{text}</p>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="min-w-[9rem] shrink-0 text-muted-foreground">{label}</span>
      <span className="truncate">{value}</span>
    </div>
  );
}
