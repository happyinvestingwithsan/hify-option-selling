"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Lock,
  RefreshCw,
  Repeat,
  ShieldAlert,
  Unlock,
  X,
} from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import {
  formatINR,
  formatNum,
  type ActiveTrade,
  type DecayLockResult,
  type KiteTradesResponse,
  type StagedOrdersResponse,
} from "@/lib/types";
import { KillSwitchButton } from "@/components/KillSwitchModal";
import { SortableTh, useTableSort } from "@/components/SortableTh";
import { StagedOrdersList } from "@/components/StagedOrdersList";

const DECAY_TIERS = [
  { label: "1 Day", target: "30%" },
  { label: "2–3 Days", target: "45%" },
  { label: "15-Day GTT", target: "50%" },
  { label: "Expiry Week", target: "70–80%" },
];

export default function PositionsPage() {
  const [tradesData, setTradesData] = useState<KiteTradesResponse | null>(null);
  const [stagedData, setStagedData] = useState<StagedOrdersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Decay Check Modal State
  const [decayTrade, setDecayTrade] = useState<ActiveTrade | null>(null);
  const [daysHeld, setDaysHeld] = useState("2");
  const [decayPctInput, setDecayPctInput] = useState("0");
  const [isExpiryWeek, setIsExpiryWeek] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  const [decayResult, setDecayResult] = useState<DecayLockResult | null>(null);
  const [checkingDecay, setCheckingDecay] = useState(false);
  const [decayError, setDecayError] = useState<string | null>(null);

  // Same-Strike Rollover Modal State
  const [rollTrade, setRollTrade] = useState<ActiveTrade | null>(null);
  const [newStrike, setNewStrike] = useState("");
  const [newExpiry, setNewExpiry] = useState("26JUN");
  const [rollLimitPrice, setRollLimitPrice] = useState("");
  const [rollSpreadPct, setRollSpreadPct] = useState("1.5");
  const [pivotFarFuture, setPivotFarFuture] = useState(false);
  const [rollingOver, setRollingOver] = useState(false);
  const [rollError, setRollError] = useState<string | null>(null);
  const [rollSuccess, setRollSuccess] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tradesRes, stagedRes] = await Promise.all([
        apiFetch<KiteTradesResponse>("/api/kite/trades"),
        apiFetch<StagedOrdersResponse>("/api/orders/staged"),
      ]);
      setTradesData(tradesRes);
      setStagedData(stagedRes);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Failed to load positions and staged orders."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  function openDecayModal(trade: ActiveTrade) {
    setDecayTrade(trade);
    setDaysHeld("2");
    setDecayPctInput(String(trade.decay_pct));
    setIsExpiryWeek(false);
    setOverrideReason("");
    setDecayResult(null);
    setDecayError(null);
  }

  async function handleDecayCheck(e: React.FormEvent) {
    e.preventDefault();
    setCheckingDecay(true);
    setDecayError(null);
    try {
      const res = await apiFetch<DecayLockResult>("/api/orders/decay-check", {
        method: "POST",
        body: JSON.stringify({
          days_held: Number(daysHeld),
          decay_pct: Number(decayPctInput),
          is_expiry_week: isExpiryWeek,
          override_reason: overrideReason.trim() || null,
        }),
      });
      setDecayResult(res);
    } catch (err) {
      setDecayError(
        err instanceof ApiError ? err.message : "Failed to evaluate Decay Lock."
      );
    } finally {
      setCheckingDecay(false);
    }
  }

  function openRolloverModal(trade: ActiveTrade) {
    setRollTrade(trade);
    setNewStrike(String(trade.strike));
    setNewExpiry("26JUN");
    setRollLimitPrice(String(Math.max(1, trade.current_price)));
    setRollSpreadPct("1.5");
    setPivotFarFuture(false);
    setRollError(null);
    setRollSuccess(null);
  }

  async function handleRolloverSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!rollTrade) return;
    setRollingOver(true);
    setRollError(null);
    setRollSuccess(null);

    try {
      const res = await apiFetch<{ status: string; order: { id: number } }>(
        "/api/orders/rollover",
        {
          method: "POST",
          body: JSON.stringify({
            symbol: rollTrade.symbol,
            old_strike: rollTrade.strike,
            new_strike: pivotFarFuture ? 0 : Number(newStrike),
            option_type: pivotFarFuture ? "FUT" : rollTrade.option_type,
            new_expiry: newExpiry.trim().toUpperCase(),
            side: "SELL",
            qty: rollTrade.qty,
            order_type: "LIMIT",
            limit_price: Number(rollLimitPrice),
            spread_pct: rollSpreadPct ? Number(rollSpreadPct) : null,
            pivot_to_far_future: pivotFarFuture,
          }),
        }
      );
      setRollSuccess(
        `Staged ${pivotFarFuture ? "Far-Month Future Pivot" : "Same-Strike Rollover"} #${res.order.id}.`
      );
      await loadData();
    } catch (err) {
      setRollError(
        err instanceof ApiError ? err.message : "Rollover rejected by strategy guardrails."
      );
    } finally {
      setRollingOver(false);
    }
  }

  const activeTrades = tradesData?.active_trades ?? [];
  const stagedOrders = stagedData?.orders ?? [];

  const positionsSort = useTableSort(activeTrades, "unrealized_pnl", "desc", {
    tradingsymbol: (r) => r.tradingsymbol,
    qty: (r) => r.qty,
    entry_price: (r) => r.entry_price,
    decay_pct: (r) => r.decay_pct,
    unrealized_pnl: (r) => r.unrealized_pnl,
  });

  return (
    <section className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight text-[var(--hify-text)]">
          Positions ({activeTrades.length})
        </h1>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void loadData()}
            disabled={loading}
            className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3 py-2 text-xs font-medium text-[var(--hify-text)] hover:bg-[var(--hify-surface-raised)] disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          <KillSwitchButton onTriggered={() => void loadData()} />
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-[var(--hify-error)] bg-[var(--hify-surface)] p-4 text-sm text-[var(--hify-error)]">
          {error}
        </div>
      )}

      {/* Active Positions Table */}
      <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)]">
        {activeTrades.length === 0 ? (
          <div className="p-6 text-center text-sm text-[var(--hify-text-secondary)]">
            {loading ? "Loading positions..." : "No active positions found."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead>
                <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                  <SortableTh label="Contract" columnKey="tradingsymbol" activeKey={positionsSort.sortKey} dir={positionsSort.sortDir} onSort={positionsSort.toggleSort} className="px-4 py-3" />
                  <SortableTh label="Qty" columnKey="qty" activeKey={positionsSort.sortKey} dir={positionsSort.sortDir} onSort={positionsSort.toggleSort} align="right" className="px-3 py-3" />
                  <SortableTh label="Entry → LTP" columnKey="entry_price" activeKey={positionsSort.sortKey} dir={positionsSort.sortDir} onSort={positionsSort.toggleSort} align="right" className="px-3 py-3" />
                  <SortableTh label="Decay % (Actual/Target)" columnKey="decay_pct" activeKey={positionsSort.sortKey} dir={positionsSort.sortDir} onSort={positionsSort.toggleSort} align="right" className="px-3 py-3" />
                  <SortableTh label="MTM" columnKey="unrealized_pnl" activeKey={positionsSort.sortKey} dir={positionsSort.sortDir} onSort={positionsSort.toggleSort} align="right" className="px-3 py-3" />
                  <th className="px-4 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--hify-border)]/60">
                {positionsSort.sortedRows.map((trade) => (
                  <tr
                    key={trade.tradingsymbol}
                    className="hover:bg-[var(--hify-bg)]/60"
                  >
                    <td className="px-4 py-3">
                      <div className="font-mono font-mono-num text-sm font-semibold text-[var(--hify-text)]">
                        {trade.tradingsymbol}
                      </div>
                      <div className="font-mono font-mono-num text-[11px] text-[var(--hify-text-secondary)]">
                        {trade.side} · {trade.strike} {trade.option_type} · {trade.expiry}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right font-mono font-mono-num text-sm text-[var(--hify-text)]">
                      {trade.qty}
                    </td>
                    <td className="px-3 py-3 text-right font-mono font-mono-num text-xs text-[var(--hify-text)]">
                      ₹{formatNum(trade.entry_price)} → ₹{formatNum(trade.current_price)}
                    </td>
                    <td className="px-3 py-3 text-right font-mono font-mono-num font-semibold text-[#8E6C20] dark:text-[#C8A951]">
                      {formatNum(trade.decay_pct, 1)}% / 50%
                    </td>
                    <td
                      className={`px-3 py-3 text-right font-mono font-mono-num text-sm font-semibold ${
                        trade.unrealized_pnl >= 0
                          ? "text-[var(--hify-success)]"
                          : "text-[var(--hify-error)]"
                      }`}
                    >
                      {formatINR(trade.unrealized_pnl, true)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => openDecayModal(trade)}
                          className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-xs font-semibold text-[var(--hify-text)] hover:border-[var(--hify-warning)]"
                        >
                          <Lock className="h-3.5 w-3.5 text-[var(--hify-warning)]" />
                          <span>Decay</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => openRolloverModal(trade)}
                          className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-xs font-semibold text-[#8E6C20] hover:border-[var(--hify-gold)] dark:text-[#C8A951]"
                        >
                          <Repeat className="h-3.5 w-3.5" />
                          <span>Roll</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Staged Orders */}
      <StagedOrdersList orders={stagedOrders} onApproved={() => void loadData()} />

      {/* Decay Check / Early Exit Modal */}
      {decayTrade && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="decay-modal-title"
        >
          <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5 shadow-xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 id="decay-modal-title" className="text-base font-semibold text-[var(--hify-text)]">
                  Decay Lock Check — {decayTrade.tradingsymbol}
                </h2>
                <p className="mt-0.5 text-xs text-[var(--hify-text-secondary)]">
                  Blocks impulsive early exits below rulebook decay targets.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDecayTrade(null)}
                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-surface-raised)]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Decay Tier Reference inside Modal */}
            <div className="mt-3 grid grid-cols-2 gap-2">
              {DECAY_TIERS.map((tier) => (
                <div
                  key={tier.label}
                  className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-2.5 py-1.5"
                >
                  <p className="text-[10px] uppercase text-[var(--hify-text-secondary)]">
                    {tier.label}
                  </p>
                  <p className="font-mono font-mono-num text-xs font-semibold text-[#8E6C20] dark:text-[#C8A951]">
                    Target {tier.target}
                  </p>
                </div>
              ))}
            </div>

            {decayError && (
              <div className="mt-3 rounded-lg border border-[var(--hify-error)] bg-[var(--hify-surface-raised)] p-3 text-xs text-[var(--hify-error)]">
                {decayError}
              </div>
            )}

            {decayResult && (
              <div
                className={`mt-3 rounded-lg border p-3 text-xs ${
                  decayResult.locked
                    ? "border-[var(--hify-warning)] text-[var(--hify-warning)]"
                    : "border-[var(--hify-success)] text-[var(--hify-success)]"
                } bg-[var(--hify-surface-raised)]`}
              >
                <div className="flex items-start gap-2">
                  {decayResult.locked ? (
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  ) : (
                    <Unlock className="mt-0.5 h-4 w-4 shrink-0" />
                  )}
                  <div>
                    <p className="font-semibold">
                      {decayResult.locked ? "DECAY LOCKED — Early Exit Warning" : "Decay Unlocked"}
                    </p>
                    <p className="font-mono font-mono-num mt-1">
                      Actual: {formatNum(decayResult.decay_pct, 1)}% · Required:{" "}
                      {formatNum(decayResult.required_target_pct, 1)}% ({decayResult.tier_label})
                    </p>
                    <p className="mt-1">{decayResult.message}</p>
                    {decayResult.override_logged && (
                      <p className="mt-1 font-semibold">
                        Override reason logged to lessons_log.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}

            <form onSubmit={handleDecayCheck} className="mt-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Days Held
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={daysHeld}
                    onChange={(e) => setDaysHeld(e.target.value)}
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                    required
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Current Decay %
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    max="100"
                    value={decayPctInput}
                    onChange={(e) => setDecayPctInput(e.target.value)}
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                    required
                  />
                </div>
              </div>

              <label className="flex min-h-[44px] cursor-pointer items-center gap-2 text-xs text-[var(--hify-text)]">
                <input
                  type="checkbox"
                  checked={isExpiryWeek}
                  onChange={(e) => setIsExpiryWeek(e.target.checked)}
                  className="h-4 w-4 accent-[var(--hify-gold)]"
                />
                <span>Expiry Week (70–80% Decay Target)</span>
              </label>

              <div>
                <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                  Override Reason {decayResult?.locked ? "(Required to Unlock)" : "(Optional)"}
                </label>
                <textarea
                  rows={2}
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder="Why are you exiting before the Decay Lock target? Logged to lessons_log."
                  className="mt-1 w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-3 text-xs text-[var(--hify-text)]"
                />
              </div>

              <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={() => setDecayTrade(null)}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-4 py-2 text-sm font-medium text-[var(--hify-text)]"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={checkingDecay}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-[var(--hify-gold)] px-4 py-2 text-sm font-semibold text-[#18181B] hover:bg-[var(--hify-gold-hover)] disabled:opacity-50"
                >
                  {checkingDecay ? "Checking..." : "Evaluate Decay Lock"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Same-Strike Rollover Modal */}
      {rollTrade && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rollover-modal-title"
        >
          <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5 shadow-xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2
                  id="rollover-modal-title"
                  className="text-base font-semibold text-[var(--hify-text)]"
                >
                  Same-Strike Rollover — {rollTrade.symbol}
                </h2>
                <p className="mt-0.5 text-xs text-[var(--hify-text-secondary)]">
                  Rolling down a Put strike is hard-blocked. Keep strike &ge;{" "}
                  {rollTrade.strike} or pivot to Far-Month Future.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setRollTrade(null)}
                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-surface-raised)]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {rollError && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-[var(--hify-error)] bg-[var(--hify-surface-raised)] p-3 text-xs text-[var(--hify-error)]">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{rollError}</span>
              </div>
            )}

            {rollSuccess && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-[var(--hify-success)] bg-[var(--hify-surface-raised)] p-3 text-xs text-[var(--hify-success)]">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{rollSuccess}</span>
              </div>
            )}

            <form onSubmit={handleRolloverSubmit} className="mt-4 space-y-3">
              <label className="flex min-h-[44px] cursor-pointer items-center gap-2.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-xs font-semibold text-[var(--hify-text)]">
                <input
                  type="checkbox"
                  checked={pivotFarFuture}
                  onChange={(e) => setPivotFarFuture(e.target.checked)}
                  className="h-4 w-4 accent-[var(--hify-gold)]"
                />
                <span>Pivot to Far-Month Future (if option illiquid)</span>
              </label>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Old Strike
                  </label>
                  <input
                    type="number"
                    value={rollTrade.strike}
                    readOnly
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text-secondary)]"
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    New Strike
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    disabled={pivotFarFuture}
                    value={pivotFarFuture ? 0 : newStrike}
                    onChange={(e) => setNewStrike(e.target.value)}
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)] disabled:opacity-50"
                    required={!pivotFarFuture}
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    New Expiry
                  </label>
                  <input
                    type="text"
                    value={newExpiry}
                    onChange={(e) => setNewExpiry(e.target.value)}
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                    required
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Limit Price (₹)
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    min="0.05"
                    value={rollLimitPrice}
                    onChange={(e) => setRollLimitPrice(e.target.value)}
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                    required
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Spread %
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={rollSpreadPct}
                    onChange={(e) => setRollSpreadPct(e.target.value)}
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Order Type
                  </label>
                  <input
                    type="text"
                    value="LIMIT"
                    readOnly
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm font-semibold text-[#8E6C20] dark:text-[#C8A951]"
                  />
                </div>
              </div>

              <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={() => setRollTrade(null)}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-4 py-2 text-sm font-medium text-[var(--hify-text)]"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={rollingOver}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-[var(--hify-gold)] px-4 py-2 text-sm font-semibold text-[#18181B] hover:bg-[var(--hify-gold-hover)] disabled:opacity-50"
                >
                  {rollingOver ? "Staging..." : "Stage Rollover"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
