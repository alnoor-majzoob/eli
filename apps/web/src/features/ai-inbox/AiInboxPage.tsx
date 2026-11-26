import { useEffect, useMemo, useState } from "react";
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

const EXTRACTED_KINDS = ["task", "commitment", "risk", "decision", "milestone"] as const;

type EditDraft = {
  title: string;
  summary: string;
  kind: string;
  priority: string;
  ownerHint: string;
  duePhrase: string;
  reason: string;
};

export function AiInboxPage() {
  const { t } = useTranslation();
  const [statusFilter, setStatusFilter] = useState("pending");
  const [kindFilter, setKindFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

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

  useEffect(() => {
    setEditingId(null);
    setDraft(null);
    setRejectingId(null);
    setRejectReason("");
  }, [selectedId]);

  const refresh = async (id?: string) => {
    await refetch();
    if (id) await detailQuery.refetch();
  };

  const accept = async (suggestion: AiSuggestion) => {
    setBusyId(suggestion.id);
    setError(null);
    try {
      await acceptAiSuggestion(suggestion.id);
      setSelectedId(suggestion.id);
      setEditingId(null);
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    } finally {
      setBusyId(null);
      await refresh(suggestion.id);
    }
  };

  const openEdit = (suggestion: AiSuggestion) => {
    setSelectedId(suggestion.id);
    setRejectingId(null);
    setEditingId(suggestion.id);
    setDraft(toDraft(suggestion.payload));
  };

  const submitEdit = async (suggestion: AiSuggestion) => {
    if (!draft) return;
    setBusyId(suggestion.id);
    setError(null);
    try {
      await acceptAiSuggestion(suggestion.id, draftToPayload(draft, suggestion.payload), draft.reason || undefined);
      setEditingId(null);
      setDraft(null);
      setSelectedId(suggestion.id);
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    } finally {
      setBusyId(null);
      await refresh(suggestion.id);
    }
  };

  const submitReject = async (suggestion: AiSuggestion) => {
    const reason = rejectReason.trim();
    if (!reason) return;
    setBusyId(suggestion.id);
    setError(null);
    try {
      await rejectAiSuggestion(suggestion.id, reason);
      setRejectingId(null);
      setRejectReason("");
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    } finally {
      setBusyId(null);
      await refresh(suggestion.id);
    }
  };

  const bulkReject = async () => {
    const ids = [...checked];
    if (!ids.length) return;
    setBusyId("bulk");
    setError(null);
    try {
      await bulkAiSuggestions(ids.map((id) => ({ suggestion_id: id, action: "reject" as const, reason: "Bulk rejected" })));
      setChecked(new Set());
    } catch (cause) {
      setError(problemMessage(cause, t("common.error")));
    } finally {
      setBusyId(null);
      await refresh();
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
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-8 rounded-md border bg-background px-2 text-xs" aria-label={t("aiInbox.filters")}>
            <option value="pending">{t("aiInbox.pending")}</option>
            <option value="accepted">{t("aiInbox.accepted")}</option>
            <option value="rejected">{t("aiInbox.rejected")}</option>
            <option value="">{t("aiInbox.all")}</option>
          </select>
          <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} className="h-8 rounded-md border bg-background px-2 text-xs" aria-label={t("aiInbox.kindFilter")}>
            <option value="">{t("aiInbox.all")}</option>
            {["extracted_item", "link", "duplicate", "classification", "owner"].map((kind) => <option key={kind} value={kind}>{kind}</option>)}
          </select>
          <Button variant="outline" size="sm" onClick={() => void refresh(selectedId ?? undefined)}>{t("common.refresh")}</Button>
        </div>
      </div>

      {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">{t("aiInbox.suggestions")}</CardTitle></CardHeader>
          <CardContent className="space-y-2 pt-0">
            <Button size="sm" variant="outline" onClick={() => void bulkReject()} disabled={checked.size === 0 || busyId !== null}>
              {t("aiInbox.bulkReject")} ({checked.size})
            </Button>
            {visible.length === 0 ? <p className="py-4 text-sm text-muted-foreground">{t("aiInbox.noSuggestions")}</p> : null}
            <div className="space-y-2">
              {visible.map((suggestion) => (
                <SuggestionCard
                  key={suggestion.id}
                  suggestion={suggestion}
                  selected={selectedId === suggestion.id}
                  checked={checked.has(suggestion.id)}
                  busy={busyId === suggestion.id}
                  onClick={() => setSelectedId(suggestion.id)}
                  onAccept={() => void accept(suggestion)}
                  onReject={() => { setSelectedId(suggestion.id); setRejectingId(suggestion.id); setEditingId(null); }}
                  onEditAndAccept={() => openEdit(suggestion)}
                  onToggle={() => setChecked((prev) => { const next = new Set(prev); next.has(suggestion.id) ? next.delete(suggestion.id) : next.add(suggestion.id); return next; })}
                />
              ))}
            </div>
          </CardContent>
        </Card>

        {selectedId && detailQuery.data ? (
          <SuggestionDetail
            detail={detailQuery.data}
            busy={busyId === detailQuery.data.id}
            editing={editingId === detailQuery.data.id}
            draft={editingId === detailQuery.data.id ? draft : null}
            rejecting={rejectingId === detailQuery.data.id}
            rejectReason={rejectReason}
            onClose={() => setSelectedId(null)}
            onAccept={() => {
              const s = suggestions.find((x) => x.id === detailQuery.data?.id);
              if (s) void accept(s);
            }}
            onEdit={() => {
              const s = suggestions.find((x) => x.id === detailQuery.data?.id);
              if (s) openEdit(s);
            }}
            onDraftChange={setDraft}
            onSubmitEdit={() => {
              const s = suggestions.find((x) => x.id === detailQuery.data?.id);
              if (s) void submitEdit(s);
            }}
            onCancelEdit={() => { setEditingId(null); setDraft(null); }}
            onRejectStart={() => { setRejectingId(detailQuery.data!.id); setEditingId(null); }}
            onRejectReasonChange={setRejectReason}
            onSubmitReject={() => {
              const s = suggestions.find((x) => x.id === detailQuery.data?.id);
              if (s) void submitReject(s);
            }}
            onCancelReject={() => { setRejectingId(null); setRejectReason(""); }}
          />
        ) : null}
      </div>
    </div>
  );
}

function toDraft(payload: Record<string, unknown>): EditDraft {
  const p = payload as Record<string, unknown>;
  return {
    title: String(p.title ?? ""),
    summary: String(p.summary ?? ""),
    kind: String(p.kind ?? "task"),
    priority: p.priority == null ? "" : String(p.priority),
    ownerHint: String(p.owner_hint ?? ""),
    duePhrase: String(p.due_phrase ?? ""),
    reason: "",
  };
}

function draftToPayload(draft: EditDraft, original: Record<string, unknown>): Record<string, unknown> {
  const priority = draft.priority.trim() ? Number(draft.priority) : undefined;
  return {
    ...original,
    title: draft.title.trim(),
    summary: draft.summary.trim(),
    kind: draft.kind,
    priority: Number.isFinite(priority) ? priority : undefined,
    owner_hint: draft.ownerHint.trim() || undefined,
    due_phrase: draft.duePhrase.trim() || undefined,
  };
}

function SuggestionCard({ suggestion, selected, checked, busy, onClick, onAccept, onReject, onEditAndAccept, onToggle }: {
  suggestion: AiSuggestion; selected: boolean; checked: boolean; busy: boolean;
  onClick: () => void; onAccept: () => void; onReject: () => void; onEditAndAccept: () => void; onToggle: () => void;
}) {
  const { t } = useTranslation();
  const payload = suggestion.payload as Record<string, unknown>;
  return (
    <div role="button" tabIndex={0} aria-label={String(payload?.title ?? t("aiInbox.suggestions"))}
      className={cn("cursor-pointer rounded-lg border p-3 transition-colors", selected ? "border-primary bg-primary/5" : "hover:bg-muted/40")}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } }}>
      <div className="flex items-center gap-2">
        <input type="checkbox" aria-label={t("aiInbox.selectForBulk")} checked={checked} onChange={onToggle} onClick={(e) => e.stopPropagation()} className="size-3.5" />
        <Badge variant={KIND_BADGE[suggestion.kind] ?? "muted"}>{suggestion.kind}</Badge>
        <span className="truncate font-medium">{String(payload?.title ?? "")}</span>
        {suggestion.confidence != null ? <span className="text-[10px] text-muted-foreground">{Math.round(Number(suggestion.confidence) * 100)}%</span> : null}
      </div>
      <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{String(payload?.summary ?? "")}</p>
      {suggestion.status === "pending" ? (
        <div className="mt-2 flex flex-wrap gap-1">
          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); onAccept(); }} disabled={busy}>{t("common.approve")}</Button>
          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); onEditAndAccept(); }} disabled={busy}>{t("aiInbox.editAndAccept")}</Button>
          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); onReject(); }} disabled={busy}>{t("aiInbox.reject")}</Button>
        </div>
      ) : null}
    </div>
  );
}

function SuggestionDetail({ detail, busy, editing, draft, rejecting, rejectReason, onClose, onAccept, onEdit, onDraftChange, onSubmitEdit, onCancelEdit, onRejectStart, onRejectReasonChange, onSubmitReject, onCancelReject }: {
  detail: AiSuggestionDetail; busy: boolean; editing: boolean; draft: EditDraft | null; rejecting: boolean; rejectReason: string;
  onClose: () => void; onAccept: () => void; onEdit: () => void; onDraftChange: (d: EditDraft) => void; onSubmitEdit: () => void; onCancelEdit: () => void;
  onRejectStart: () => void; onRejectReasonChange: (v: string) => void; onSubmitReject: () => void; onCancelReject: () => void;
}) {
  const { t } = useTranslation();
  const payload = detail.payload as Record<string, unknown>;
  const pending = detail.status === "pending";
  return (
    <Card className="max-h-[75vh] overflow-y-auto">
      <CardHeader className="space-y-1 pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm">{String(payload?.title ?? "")}</CardTitle>
          <Button variant="ghost" size="sm" onClick={onClose}>{t("common.close")}</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-0 text-xs">
        <div className="flex flex-wrap gap-1">
          <Badge variant={KIND_BADGE[detail.kind] ?? "muted"}>{detail.kind}</Badge>
          <Badge variant="muted">{detail.status}</Badge>
          {detail.confidence != null ? <Badge variant="outline">{Math.round(Number(detail.confidence) * 100)}%</Badge> : null}
        </div>

        {detail.evidence?.quote ? <QuoteBlock text={String(detail.evidence.quote)} label={t("aiInbox.evidence")} /> : null}
        {detail.source_excerpt ? <QuoteBlock text={detail.source_excerpt} label={t("aiInbox.sourceExcerpt")} /> : null}

        {editing && draft ? (
          <div className="space-y-2 rounded-md border p-3">
            <div className="text-[11px] font-semibold uppercase text-muted-foreground">{t("aiInbox.editAndAccept")}</div>
            <label className="block space-y-1"><span>{t("aiInbox.fieldTitle")}</span><input className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={draft.title} onChange={(e) => onDraftChange({ ...draft, title: e.target.value })} /></label>
            <label className="block space-y-1"><span>{t("aiInbox.fieldSummary")}</span><textarea className="min-h-20 w-full rounded-md border bg-background px-3 py-2 text-sm" value={draft.summary} onChange={(e) => onDraftChange({ ...draft, summary: e.target.value })} /></label>
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block space-y-1"><span>{t("aiInbox.fieldKind")}</span>
                <select className="h-9 w-full rounded-md border bg-background px-2 text-sm" value={draft.kind} onChange={(e) => onDraftChange({ ...draft, kind: e.target.value })}>
                  {EXTRACTED_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                </select>
              </label>
              <label className="block space-y-1"><span>{t("aiInbox.fieldPriority")}</span><input className="h-9 w-full rounded-md border bg-background px-3 text-sm" type="number" min={1} max={5} value={draft.priority} onChange={(e) => onDraftChange({ ...draft, priority: e.target.value })} /></label>
              <label className="block space-y-1"><span>{t("aiInbox.fieldOwnerHint")}</span><input className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={draft.ownerHint} onChange={(e) => onDraftChange({ ...draft, ownerHint: e.target.value })} /></label>
              <label className="block space-y-1"><span>{t("aiInbox.fieldDuePhrase")}</span><input className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={draft.duePhrase} onChange={(e) => onDraftChange({ ...draft, duePhrase: e.target.value })} /></label>
            </div>
            <label className="block space-y-1"><span>{t("aiInbox.reviewReason")}</span><input className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={draft.reason} onChange={(e) => onDraftChange({ ...draft, reason: e.target.value })} placeholder={t("aiInbox.reviewReasonPlaceholder")} /></label>
            <div className="flex gap-2">
              <Button size="sm" onClick={onSubmitEdit} disabled={busy || !draft.title.trim()}>{t("aiInbox.saveAndAccept")}</Button>
              <Button size="sm" variant="outline" onClick={onCancelEdit} disabled={busy}>{t("common.cancel")}</Button>
            </div>
          </div>
        ) : (
          <div className="grid gap-1.5 sm:grid-cols-2">
            <MetaRow label={t("aiInbox.fieldKind")} value={String(payload?.kind ?? "—")} />
            <MetaRow label={t("aiInbox.fieldPriority")} value={payload?.priority == null ? "—" : String(payload.priority)} />
            <MetaRow label={t("aiInbox.fieldOwnerHint")} value={String(payload?.owner_hint ?? "—")} />
            <MetaRow label={t("aiInbox.fieldDuePhrase")} value={String(payload?.due_phrase ?? "—")} />
            <MetaRow label={t("aiInbox.model")} value={detail.model} />
            <MetaRow label={t("aiInbox.promptVersion")} value={detail.prompt_version} />
          </div>
        )}

        {rejecting ? (
          <div className="space-y-2 rounded-md border p-3">
            <label className="block space-y-1"><span>{t("aiInbox.rejectReason")}</span><input className="h-9 w-full rounded-md border bg-background px-3 text-sm" value={rejectReason} onChange={(e) => onRejectReasonChange(e.target.value)} placeholder={t("aiInbox.rejectReasonPlaceholder")} /></label>
            <div className="flex gap-2">
              <Button size="sm" variant="destructive" onClick={onSubmitReject} disabled={busy || !rejectReason.trim()}>{t("aiInbox.reject")}</Button>
              <Button size="sm" variant="outline" onClick={onCancelReject} disabled={busy}>{t("common.cancel")}</Button>
            </div>
          </div>
        ) : null}

        {pending && !editing && !rejecting ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={onAccept} disabled={busy}>{t("common.approve")}</Button>
            <Button size="sm" variant="outline" onClick={onEdit} disabled={busy}>{t("aiInbox.editAndAccept")}</Button>
            <Button size="sm" variant="outline" onClick={onRejectStart} disabled={busy}>{t("aiInbox.reject")}</Button>
          </div>
        ) : null}

        {!pending && detail.review_reason ? <QuoteBlock text={detail.review_reason} label={t("aiInbox.rejectReason")} /> : null}
      </CardContent>
    </Card>
  );
}

function QuoteBlock({ text, label }: { text: string; label?: string }) {
  return (
    <div className="rounded-md border bg-muted/30 p-2">
      {label ? <div className="mb-1 text-[10px] font-semibold uppercase text-muted-foreground">{label}</div> : null}
      <p className="whitespace-pre-wrap text-xs text-muted-foreground">{text}</p>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return <div className="flex gap-2"><span className="min-w-[8rem] shrink-0 text-muted-foreground">{label}</span><span className="break-words">{value}</span></div>;
}
