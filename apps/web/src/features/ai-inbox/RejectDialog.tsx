import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

/** Reject dialog: a proper form (reason + validation + cancel), not a native prompt. */
export function RejectDialog({
  open,
  busy,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (reason: string) => void | Promise<unknown>;
}) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const value = reason.trim();
    if (!value) {
      setError(t("aiInbox.rejectReasonRequired"));
      return;
    }
    setError(null);
    try {
      await onSubmit(value);
      setReason("");
    } catch {
      /* error surfaced by parent; keep dialog open */
    }
  };

  return (
    <dialog open role="dialog" aria-modal="true" aria-label={t("aiInbox.reject")} className="fixed inset-0 z-50 m-auto h-max w-full max-w-md rounded-lg border bg-card p-4 shadow-xl">
      <form onSubmit={(e) => void submit(e)} className="space-y-3">
        <h3 className="text-sm font-semibold">{t("aiInbox.reject")}</h3>
        <label className="block space-y-1 text-xs">
          <span>{t("aiInbox.rejectReason")}</span>
          <textarea
            autoFocus
            className="min-h-20 w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={t("aiInbox.rejectReasonPlaceholder")}
            disabled={busy}
          />
        </label>
        {error ? <p role="alert" className="text-xs text-destructive">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={busy}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" variant="destructive" size="sm" disabled={busy || !reason.trim()}>
            {t("aiInbox.reject")}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
