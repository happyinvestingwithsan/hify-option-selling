"use client";

import { useState } from "react";
import { AlertTriangle, ShieldAlert, X } from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import type { KillSwitchResponse } from "@/lib/types";

interface KillSwitchButtonProps {
  onTriggered?: (result: KillSwitchResponse) => void;
  className?: string;
}

export function KillSwitchButton({ onTriggered, className = "" }: KillSwitchButtonProps) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<KillSwitchResponse | null>(null);

  async function handleConfirm() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch<KillSwitchResponse>("/api/orders/kill-switch", {
        method: "POST",
        body: JSON.stringify({ confirm_kill: true }),
      });
      setResult(res);
      onTriggered?.(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to trigger Kill Switch.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setError(null);
          setResult(null);
          setOpen(true);
        }}
        className={`inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--hify-error)] bg-[var(--hify-surface)] px-4 py-2 text-sm font-semibold text-[var(--hify-error)] transition-colors hover:bg-[var(--hify-error)] hover:text-white ${className}`}
      >
        <ShieldAlert className="h-4 w-4 shrink-0" />
        <span>Kill Switch</span>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="kill-switch-title"
        >
          <div className="w-full max-w-md rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5 shadow-xl">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5 text-[var(--hify-error)]">
                <AlertTriangle className="h-5 w-5 shrink-0" />
                <h2 id="kill-switch-title" className="text-base font-semibold">
                  Confirm Emergency Kill Switch
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-surface-raised)]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="mt-3 text-sm text-[var(--hify-text-secondary)]">
              This will immediately cancel all active staged ATO/GTT orders in SQLite and cancel
              pending Kite orders &amp; active GTT triggers if live-connected.
            </p>

            {error && (
              <div className="mt-3 rounded-lg border border-[var(--hify-error)] bg-[var(--hify-surface-raised)] p-3 text-xs text-[var(--hify-error)]">
                {error}
              </div>
            )}

            {result && (
              <div className="mt-3 rounded-lg border border-[var(--hify-success)] bg-[var(--hify-surface-raised)] p-3 text-xs text-[var(--hify-text)]">
                <p className="font-semibold text-[var(--hify-success)]">Kill Switch Executed</p>
                <p className="font-mono font-mono-num mt-1">
                  Staged cancelled: {result.cancelled_staged_count} · Live orders:{" "}
                  {result.live_cancelled_orders} · Live GTTs: {result.live_cancelled_gtts}
                </p>
              </div>
            )}

            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-4 py-2 text-sm font-medium text-[var(--hify-text)] hover:bg-[var(--hify-surface-raised)]"
              >
                {result ? "Close" : "Cancel"}
              </button>
              {!result && (
                <button
                  type="button"
                  disabled={submitting}
                  onClick={handleConfirm}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-[var(--hify-error)] px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {submitting ? "Cancelling All..." : "Confirm Kill Switch"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
