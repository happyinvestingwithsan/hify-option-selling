"use client";

import { useState } from "react";
import { CheckCircle2, Clock } from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import { formatNum, type StagedOrder } from "@/lib/types";

interface StagedOrdersListProps {
  orders: StagedOrder[];
  onApproved?: () => void;
}

export function StagedOrdersList({ orders, onApproved }: StagedOrdersListProps) {
  const [approvingId, setApprovingId] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);

  async function handleApprove(orderId: number) {
    setApprovingId(orderId);
    setFeedback(null);
    try {
      const res = await apiFetch<{ mode: string; auto_fired: boolean }>(
        `/api/orders/${orderId}/approve`,
        {
          method: "POST",
          body: JSON.stringify({
            confirm_manual_approval: true,
            execute_live: false,
          }),
        }
      );
      setFeedback({
        type: "success",
        text: `Order #${orderId} approved (${res.mode}). Auto-fire is disabled.`,
      });
      onApproved?.();
    } catch (err) {
      setFeedback({
        type: "error",
        text: err instanceof ApiError ? err.message : `Failed to approve order #${orderId}.`,
      });
    } finally {
      setApprovingId(null);
    }
  }

  return (
    <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4 sm:p-5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-[#8E6C20] dark:text-[#C8A951]" />
          <h2 className="text-sm font-semibold text-[var(--hify-text)]">
            Staged ATO / GTT Orders
          </h2>
        </div>
        <span className="font-mono font-mono-num rounded-full border border-[var(--hify-border)] px-2.5 py-0.5 text-xs text-[var(--hify-text-secondary)]">
          {orders.length}
        </span>
      </div>

      {feedback && (
        <div
          className={`mt-3 rounded-lg border p-3 text-xs ${
            feedback.type === "success"
              ? "border-[var(--hify-success)] text-[var(--hify-success)]"
              : "border-[var(--hify-error)] text-[var(--hify-error)]"
          } bg-[var(--hify-surface-raised)]`}
        >
          {feedback.text}
        </div>
      )}

      {orders.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--hify-text-secondary)]">
          No staged ATO/GTT orders yet. Stage a Limit order from the Dhool Chaat Scanner.
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {orders.map((order) => {
            const canApprove = order.status === "STAGED" || order.status === "PENDING";
            const contractLabel =
              order.option_type === "FUT"
                ? `${order.symbol} ${order.expiry} FUT`
                : `${order.symbol} ${order.expiry} ${order.strike} ${order.option_type}`;

            return (
              <div
                key={order.id}
                className="flex flex-col gap-3 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-3.5 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-[var(--hify-text)]">
                      {contractLabel}
                    </span>
                    <span className="rounded border border-[var(--hify-border)] px-2 py-0.5 text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                      {order.side} · {order.order_type}
                    </span>
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase ${
                        order.status.includes("CANCELLED")
                          ? "border border-[var(--hify-error)] text-[var(--hify-error)]"
                          : order.status.includes("APPROVED")
                          ? "border border-[var(--hify-success)] text-[var(--hify-success)]"
                          : "border border-[var(--hify-border)] text-[#8E6C20] dark:text-[#C8A951]"
                      }`}
                    >
                      {order.status}
                    </span>
                  </div>

                  <div className="font-mono font-mono-num flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--hify-text-secondary)]">
                    <span>Qty: {order.qty}</span>
                    <span>Limit: ₹{formatNum(order.limit_price)}</span>
                    {order.gtt_target_price !== null && (
                      <span>GTT Target: ₹{formatNum(order.gtt_target_price)}</span>
                    )}
                    {order.spread_pct !== null && (
                      <span>Spread: {formatNum(order.spread_pct)}%</span>
                    )}
                  </div>
                </div>

                {canApprove && (
                  <button
                    type="button"
                    disabled={approvingId === order.id}
                    onClick={() => handleApprove(order.id)}
                    className="inline-flex min-h-[44px] shrink-0 items-center justify-center gap-1.5 rounded-lg bg-[var(--hify-gold)] px-4 py-2 text-xs font-semibold text-[#18181B] transition-colors hover:bg-[var(--hify-gold-hover)] disabled:opacity-50"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    <span>{approvingId === order.id ? "Approving..." : "Approve (Manual)"}</span>
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
