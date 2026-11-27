"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  FlaskConical,
  Lock,
  Play,
  Plus,
  RefreshCw,
  Repeat,
  ShieldAlert,
  X,
} from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import {
  PaperTrade,
  PaperTradesResponse,
  formatINR,
} from "@/lib/types";
import { SortableTh, useTableSort } from "@/components/SortableTh";

export default function PaperLabPage() {
  const [data, setData] = useState<PaperTradesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // New Paper Trade Modal & Form state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [symbol, setSymbol] = useState("HDFCBANK");
  const [strike, setStrike] = useState("1600");
  const [optionType, setOptionType] = useState<"PE" | "CE">("PE");
  const [expiry, setExpiry] = useState("26DEC");
  const [entryPrice, setEntryPrice] = useState("32.5");
  const [lotSize, setLotSize] = useState("550");
  const [qty, setQty] = useState("550");
  const [marginBlocked, setMarginBlocked] = useState("185000");
  const [spreadPct, setSpreadPct] = useState("1.2");
  const [atoTriggerPrice, setAtoTriggerPrice] = useState("");
  const [isHedged, setIsHedged] = useState(false);
  const [isCoveredCall, setIsCoveredCall] = useState(false);

  // Modals state
  const [simTrade, setSimTrade] = useState<PaperTrade | null>(null);
  const [simOptionPrice, setSimOptionPrice] = useState("");
  const [simDaysHeld, setSimDaysHeld] = useState("15");
  const [simAutoBook, setSimAutoBook] = useState(false);

  const [rollTrade, setRollTrade] = useState<PaperTrade | null>(null);
  const [rollExpiry, setRollExpiry] = useState("30JAN");
  const [rollClosePrice, setRollClosePrice] = useState("");
  const [rollNewEntry, setRollNewEntry] = useState("");
  const [rollPivotFuture, setRollPivotFuture] = useState(false);

  const [closeTrade, setCloseTrade] = useState<PaperTrade | null>(null);
  const [closeExitPrice, setCloseExitPrice] = useState("");
  const [closeOverrideReason, setCloseOverrideReason] = useState("");

  const loadTrades = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch<PaperTradesResponse>("/api/paper/trades");
      setData(res);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to load Paper Lab trades."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTrades();
  }, [loadTrades]);

  async function handleCreateTrade(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setBanner(null);
    try {
      const payload: Record<string, unknown> = {
        symbol: symbol.trim().toUpperCase(),
        strike: Number(strike),
        option_type: optionType,
        expiry: expiry.trim().toUpperCase(),
        side: "SELL",
        qty: Number(qty),
        lot_size: Number(lotSize),
        order_type: "LIMIT",
        limit_price: Number(entryPrice),
        margin_blocked: Number(marginBlocked) || 0,
        spread_pct: spreadPct ? Number(spreadPct) : null,
        is_hedged: isHedged,
        is_covered_call: isCoveredCall,
      };
      if (atoTriggerPrice.trim()) {
        payload.ato_trigger_price = Number(atoTriggerPrice);
      }

      const res = await apiFetch<{ status: string; trade: PaperTrade }>(
        "/api/paper/trades",
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
      setBanner(
        `Created simulated trade #${res.trade.id} (${res.trade.symbol} ${res.trade.strike} ${res.trade.option_type}) [${res.status}].`
      );
      setShowCreateModal(false);
      await loadTrades();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to create paper trade."
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSimulateSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!simTrade) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch<{ trade: PaperTrade; target_hit: boolean }>(
        `/api/paper/trades/${simTrade.id}/simulate`,
        {
          method: "POST",
          body: JSON.stringify({
            simulated_option_price: Number(simOptionPrice),
            days_held: Number(simDaysHeld) || 15,
            auto_book_on_target: simAutoBook,
          }),
        }
      );
      setBanner(
        `Simulated #${simTrade.id}: Decay ${res.trade.decay_pct.toFixed(1)}%${
          res.target_hit ? " (Decay Target Hit!)" : ""
        }.`
      );
      setSimTrade(null);
      await loadTrades();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to simulate tick."
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRolloverSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!rollTrade) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch(`/api/paper/trades/${rollTrade.id}/rollover`, {
        method: "POST",
        body: JSON.stringify({
          new_expiry: rollExpiry.trim().toUpperCase(),
          new_strike: rollPivotFuture ? 0 : rollTrade.strike,
          close_current_price: Number(rollClosePrice),
          new_entry_price: Number(rollNewEntry),
          pivot_to_far_future: rollPivotFuture,
        }),
      });
      setBanner(
        rollPivotFuture
          ? `Pivoted #${rollTrade.id} to Far-Month Future (${rollExpiry.toUpperCase()}).`
          : `Rolled #${rollTrade.id} at exact same strike ${rollTrade.strike} -> ${rollExpiry.toUpperCase()}.`
      );
      setRollTrade(null);
      await loadTrades();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to rollover paper trade."
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCloseSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!closeTrade) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch<{
        realized_pnl: number;
        decay_pct: number;
        closed_before_target: boolean;
      }>(`/api/paper/trades/${closeTrade.id}/close`, {
        method: "POST",
        body: JSON.stringify({
          exit_price: Number(closeExitPrice),
          override_reason: closeOverrideReason,
        }),
      });
      setBanner(
        `Closed #${closeTrade.id} at ${res.decay_pct.toFixed(1)}% decay (${formatINR(
          res.realized_pnl,
          true
        )}).`
      );
      setCloseTrade(null);
      await loadTrades();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to close paper trade."
      );
    } finally {
      setSubmitting(false);
    }
  }

  const summary = data?.summary;
  const trades = data?.trades ?? [];

  const paperSort = useTableSort(trades, "id", "desc", {
    id: (r) => r.id,
    status: (r) => r.status,
    entry_price: (r) => r.entry_price,
    decay_pct: (r) => r.decay_pct,
    pnl: (r) => r.pnl,
  });

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-xl font-semibold tracking-tight text-[var(--hify-text)]">
            Paper / Strategy Lab
          </h1>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[#C8A951] bg-[var(--hify-gold-milestone)] px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#8E6C20] dark:bg-[var(--hify-surface)] dark:text-[#C8A951]">
            <ShieldAlert className="h-3 w-3 shrink-0" />
            SQLITE ONLY · NO KITE
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={loadTrades}
            disabled={loading}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3 text-xs font-medium text-[var(--hify-text)] transition-colors hover:bg-[var(--hify-bg)] disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>

          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg bg-[#C8A951] px-4 text-xs font-semibold text-[#18181B] transition-colors hover:bg-[#B6933A]"
          >
            <Plus className="h-4 w-4" />
            <span>New Paper Trade</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-[var(--hify-error)]/40 bg-[var(--hify-surface)] p-4 text-sm text-[var(--hify-error)]">
          {error}
        </div>
      )}

      {banner && (
        <div className="rounded-xl border border-[var(--hify-success)]/40 bg-[var(--hify-surface)] p-3 text-xs font-medium text-[var(--hify-success)]">
          {banner}
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--hify-text-secondary)]">
            Total Simulated P&amp;L
          </div>
          <div
            className={`mt-1 font-mono font-mono-num text-xl font-semibold ${
              (summary?.total_pnl ?? 0) >= 0
                ? "text-[var(--hify-success)]"
                : "text-[var(--hify-error)]"
            }`}
          >
            {summary ? formatINR(summary.total_pnl, true) : "—"}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--hify-text-secondary)]">
            Active / ATO Waiting
          </div>
          <div className="mt-1 font-mono font-mono-num text-xl font-semibold text-[var(--hify-text)]">
            {summary
              ? `${summary.open_count} / ${summary.ato_waiting_count}`
              : "—"}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--hify-text-secondary)]">
            Closed / Rolled
          </div>
          <div className="mt-1 font-mono font-mono-num text-xl font-semibold text-[var(--hify-text)]">
            {summary
              ? `${summary.closed_count} / ${summary.rolled_count}`
              : "—"}
          </div>
        </div>

        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--hify-text-secondary)]">
            Win Rate
          </div>
          <div className="mt-1 font-mono font-mono-num text-xl font-semibold text-[#8E6C20] dark:text-[#C8A951]">
            {summary ? `${summary.win_rate_pct.toFixed(1)}%` : "—"}
          </div>
        </div>
      </div>

      {/* Simulated Trades Table */}
      <section className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)]">
        <div className="flex items-center justify-between border-b border-[var(--hify-border)] px-4 py-3">
          <h2 className="text-sm font-semibold text-[var(--hify-text)]">
            Simulated Trades ({trades.length})
          </h2>
        </div>

        {!loading && trades.length === 0 ? (
          <div className="p-6 text-center text-xs text-[var(--hify-text-secondary)]">
            No simulated trades yet. Click &ldquo;+ New Paper Trade&rdquo; to test a Wheel entry.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-xs">
              <thead>
                <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                  <SortableTh label="#ID Contract" columnKey="id" activeKey={paperSort.sortKey} dir={paperSort.sortDir} onSort={paperSort.toggleSort} className="px-4 py-2.5" />
                  <SortableTh label="Status" columnKey="status" activeKey={paperSort.sortKey} dir={paperSort.sortDir} onSort={paperSort.toggleSort} className="px-3 py-2.5" />
                  <SortableTh label="Entry / LTP" columnKey="entry_price" activeKey={paperSort.sortKey} dir={paperSort.sortDir} onSort={paperSort.toggleSort} align="right" className="px-3 py-2.5" />
                  <SortableTh label="Decay / Target" columnKey="decay_pct" activeKey={paperSort.sortKey} dir={paperSort.sortDir} onSort={paperSort.toggleSort} align="right" className="px-3 py-2.5" />
                  <SortableTh label="P&L" columnKey="pnl" activeKey={paperSort.sortKey} dir={paperSort.sortDir} onSort={paperSort.toggleSort} align="right" className="px-3 py-2.5" />
                  <th className="px-4 py-2.5 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--hify-border)]/60">
                {paperSort.sortedRows.map((trade) => {
                  const isActive =
                    trade.status === "OPEN" || trade.status === "ATO_WAITING";
                  return (
                    <tr key={trade.id} className="hover:bg-[var(--hify-bg)]/60">
                      <td className="px-4 py-3">
                        <div className="font-mono font-mono-num font-semibold text-[var(--hify-text)]">
                          #{trade.id} {trade.symbol} {trade.strike > 0 ? trade.strike : ""}{" "}
                          {trade.option_type}
                        </div>
                        <div className="font-mono font-mono-num text-[11px] text-[var(--hify-text-secondary)]">
                          {trade.expiry} · Qty {trade.qty}
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <span className="inline-flex rounded-full border border-[var(--hify-border)] px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#8E6C20] dark:text-[#C8A951]">
                          {trade.status}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-right font-mono font-mono-num text-[var(--hify-text)]">
                        {trade.entry_price.toFixed(2)} / {trade.current_price.toFixed(2)}
                      </td>
                      <td className="px-3 py-3 text-right font-mono font-mono-num text-[var(--hify-text)]">
                        {trade.decay_pct.toFixed(1)}% / {trade.decay_target_pct.toFixed(0)}%
                      </td>
                      <td className="px-3 py-3 text-right">
                        <div
                          className={`font-mono font-mono-num font-semibold ${
                            trade.pnl >= 0
                              ? "text-[var(--hify-success)]"
                              : "text-[var(--hify-error)]"
                          }`}
                        >
                          {formatINR(trade.pnl, true)}
                        </div>
                        <div className="font-mono font-mono-num text-[10px] text-[var(--hify-text-secondary)]">
                          PPM {trade.ppm_pct.toFixed(1)}%
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {isActive ? (
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              onClick={() => {
                                setSimTrade(trade);
                                setSimOptionPrice(String(trade.current_price));
                              }}
                              className="inline-flex min-h-[44px] items-center justify-center gap-1 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface-raised)] px-2.5 text-xs font-medium text-[var(--hify-text)] hover:bg-[var(--hify-bg)]"
                            >
                              <Play className="h-3.5 w-3.5 text-[#8E6C20] dark:text-[#C8A951]" />
                              <span>Tick</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setRollTrade(trade);
                                setRollClosePrice(String(trade.current_price));
                                setRollNewEntry(String(trade.entry_price));
                                setRollPivotFuture(false);
                              }}
                              className="inline-flex min-h-[44px] items-center justify-center gap-1 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface-raised)] px-2.5 text-xs font-medium text-[var(--hify-text)] hover:bg-[var(--hify-bg)]"
                            >
                              <Repeat className="h-3.5 w-3.5" />
                              <span>Roll</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setCloseTrade(trade);
                                setCloseExitPrice(String(trade.current_price));
                                setCloseOverrideReason("");
                              }}
                              className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--hify-error)]/40 bg-[var(--hify-surface-raised)] px-2.5 text-xs font-medium text-[var(--hify-error)] hover:bg-[var(--hify-bg)]"
                            >
                              Close
                            </button>
                          </div>
                        ) : (
                          <div className="text-right font-mono text-[var(--hify-text-secondary)]">
                            —
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* New Paper Trade Modal */}
      {showCreateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-paper-modal-title"
        >
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5 shadow-xl">
            <div className="mb-4 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <FlaskConical className="h-4 w-4 text-[#8E6C20] dark:text-[#C8A951]" />
                <h2
                  id="create-paper-modal-title"
                  className="text-base font-semibold text-[var(--hify-text)]"
                >
                  New Paper Trade (LIMIT Locked)
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-bg)]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form
              onSubmit={handleCreateTrade}
              className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
            >
              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Symbol</span>
                <input
                  type="text"
                  required
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Strike</span>
                <input
                  type="number"
                  step="0.05"
                  required
                  value={strike}
                  onChange={(e) => setStrike(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Option Type</span>
                <select
                  value={optionType}
                  onChange={(e) => setOptionType(e.target.value as "PE" | "CE")}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm text-[var(--hify-text)]"
                >
                  <option value="PE">PE (Put Sell)</option>
                  <option value="CE">CE (Covered Call)</option>
                </select>
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Expiry</span>
                <input
                  type="text"
                  required
                  value={expiry}
                  onChange={(e) => setExpiry(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="flex items-center gap-1 text-[var(--hify-text-secondary)]">
                  <Lock className="h-3 w-3" /> Order Type
                </span>
                <input
                  type="text"
                  readOnly
                  value="LIMIT"
                  className="min-h-[44px] cursor-not-allowed rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface-raised)] px-3 font-mono text-sm font-semibold text-[var(--hify-text-secondary)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Entry Limit Price (₹)</span>
                <input
                  type="number"
                  step="0.05"
                  required
                  value={entryPrice}
                  onChange={(e) => setEntryPrice(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Lot Size</span>
                <input
                  type="number"
                  required
                  value={lotSize}
                  onChange={(e) => setLotSize(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Qty</span>
                <input
                  type="number"
                  required
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Margin Blocked (₹)</span>
                <input
                  type="number"
                  step="100"
                  value={marginBlocked}
                  onChange={(e) => setMarginBlocked(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">Bid-Ask Spread %</span>
                <input
                  type="number"
                  step="0.1"
                  value={spreadPct}
                  onChange={(e) => setSpreadPct(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
                />
              </label>

              <label className="flex flex-col gap-1 text-xs">
                <span className="text-[var(--hify-text-secondary)]">ATO Trigger Price (Optional)</span>
                <input
                  type="number"
                  step="0.05"
                  placeholder="Blank = immediate"
                  value={atoTriggerPrice}
                  onChange={(e) => setAtoTriggerPrice(e.target.value)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
                />
              </label>

              <div className="flex flex-col justify-center gap-2 text-xs">
                <label className="flex min-h-[22px] items-center gap-2 text-[var(--hify-text)]">
                  <input
                    type="checkbox"
                    checked={isHedged}
                    onChange={(e) => setIsHedged(e.target.checked)}
                    className="h-4 w-4"
                  />
                  <span>Hedged Position</span>
                </label>
                <label className="flex min-h-[22px] items-center gap-2 text-[var(--hify-text)]">
                  <input
                    type="checkbox"
                    checked={isCoveredCall}
                    onChange={(e) => setIsCoveredCall(e.target.checked)}
                    className="h-4 w-4"
                  />
                  <span>Covered Call (for CE)</span>
                </label>
              </div>

              <div className="flex flex-col-reverse gap-2 pt-2 sm:col-span-2 sm:flex-row sm:justify-end lg:col-span-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] px-4 text-xs font-medium text-[var(--hify-text)]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[#C8A951] px-5 text-xs font-semibold text-[#18181B] transition-colors hover:bg-[#B6933A] disabled:opacity-50"
                >
                  <Plus className="h-4 w-4" />
                  <span>{submitting ? "Creating..." : "Create Paper Trade"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Simulate Tick / ATO Modal */}
      {simTrade && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <form
            onSubmit={handleSimulateSubmit}
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--hify-text)]">
                Simulate Tick / ATO — #{simTrade.id} {simTrade.symbol}
              </h3>
              <button
                type="button"
                onClick={() => setSimTrade(null)}
                className="flex h-11 w-11 items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-bg)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--hify-text-secondary)]">
                Simulated Option Price (₹)
              </span>
              <input
                type="number"
                step="0.05"
                required
                value={simOptionPrice}
                onChange={(e) => setSimOptionPrice(e.target.value)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
              />
            </label>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--hify-text-secondary)]">Days Held</span>
              <input
                type="number"
                min="0"
                value={simDaysHeld}
                onChange={(e) => setSimDaysHeld(e.target.value)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
              />
            </label>

            <label className="flex min-h-[44px] items-center gap-2 text-xs text-[var(--hify-text)]">
              <input
                type="checkbox"
                checked={simAutoBook}
                onChange={(e) => setSimAutoBook(e.target.checked)}
                className="h-4 w-4"
              />
              <span>Auto-book if Decay Target hit</span>
            </label>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSimTrade(null)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] px-4 text-xs font-medium text-[var(--hify-text)]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="min-h-[44px] rounded-lg bg-[#C8A951] px-4 text-xs font-semibold text-[#18181B] hover:bg-[#B6933A]"
              >
                {submitting ? "Simulating..." : "Run Tick"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Same-Strike Rollover Modal */}
      {rollTrade && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <form
            onSubmit={handleRolloverSubmit}
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--hify-text)]">
                Same-Strike Rollover — #{rollTrade.id} {rollTrade.symbol} {rollTrade.strike}
              </h3>
              <button
                type="button"
                onClick={() => setRollTrade(null)}
                className="flex h-11 w-11 items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-bg)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--hify-text-secondary)]">New Expiry</span>
              <input
                type="text"
                required
                value={rollExpiry}
                onChange={(e) => setRollExpiry(e.target.value)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono text-sm text-[var(--hify-text)]"
              />
            </label>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--hify-text-secondary)]">
                Close Current Leg Price (₹)
              </span>
              <input
                type="number"
                step="0.05"
                required
                value={rollClosePrice}
                onChange={(e) => setRollClosePrice(e.target.value)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
              />
            </label>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--hify-text-secondary)]">
                New Leg Entry Price (₹)
              </span>
              <input
                type="number"
                step="0.05"
                required
                value={rollNewEntry}
                onChange={(e) => setRollNewEntry(e.target.value)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
              />
            </label>

            <label className="flex min-h-[44px] items-center gap-2 text-xs text-[var(--hify-text)]">
              <input
                type="checkbox"
                checked={rollPivotFuture}
                onChange={(e) => setRollPivotFuture(e.target.checked)}
                className="h-4 w-4"
              />
              <span>Pivot to Far-Month Future (if next-month Put illiquid)</span>
            </label>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setRollTrade(null)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] px-4 text-xs font-medium text-[var(--hify-text)]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="min-h-[44px] rounded-lg bg-[#C8A951] px-4 text-xs font-semibold text-[#18181B] hover:bg-[#B6933A]"
              >
                {submitting ? "Rolling..." : "Confirm Rollover"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Close Paper Trade Modal */}
      {closeTrade && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <form
            onSubmit={handleCloseSubmit}
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[var(--hify-text)]">
                Close Paper Trade — #{closeTrade.id} {closeTrade.symbol}
              </h3>
              <button
                type="button"
                onClick={() => setCloseTrade(null)}
                className="flex h-11 w-11 items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-bg)]"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--hify-text-secondary)]">Exit Price (₹)</span>
              <input
                type="number"
                step="0.05"
                required
                value={closeExitPrice}
                onChange={(e) => setCloseExitPrice(e.target.value)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 font-mono font-mono-num text-sm text-[var(--hify-text)]"
              />
            </label>

            <label className="flex flex-col gap-1 text-xs">
              <span className="text-[var(--hify-text-secondary)]">
                Override Reason (if closing before Decay Target)
              </span>
              <input
                type="text"
                placeholder="Optional thesis break note"
                value={closeOverrideReason}
                onChange={(e) => setCloseOverrideReason(e.target.value)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm text-[var(--hify-text)]"
              />
            </label>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCloseTrade(null)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] px-4 text-xs font-medium text-[var(--hify-text)]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="min-h-[44px] rounded-lg bg-[#C8A951] px-4 text-xs font-semibold text-[#18181B] hover:bg-[#B6933A]"
              >
                {submitting ? "Closing..." : "Confirm Close"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
