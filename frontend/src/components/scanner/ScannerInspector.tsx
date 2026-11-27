"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  ShieldAlert,
  X,
} from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import {
  formatINR,
  formatNum,
  type ScannerFundamentalsRefreshResponse,
  type ScannerResultItem,
} from "@/lib/types";

interface ScannerInspectorProps {
  candidate: ScannerResultItem | null;
  canOpenNew: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onStageOrder: (item: ScannerResultItem) => void;
  onFundamentalsUpdated: (
    symbol: string,
    res: ScannerFundamentalsRefreshResponse
  ) => void;
}

function formatNullableNum(
  value: number | string | null | undefined,
  decimals = 1,
  suffix = ""
): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num)) return "—";
  return `${formatNum(num, decimals)}${suffix}`;
}

function CheckBadge({ status }: { status: boolean | null | undefined }) {
  if (status === true) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[#10B981]/10 px-2 py-0.5 text-[10px] font-semibold text-[#10B981]">
        OK
      </span>
    );
  }
  if (status === false) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[#F43F5E]/10 px-2 py-0.5 text-[10px] font-semibold text-[#F43F5E]">
        FAIL
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-[var(--hify-surface-raised)] px-2 py-0.5 text-[10px] font-medium text-[var(--hify-text-secondary)]">
      —
    </span>
  );
}

export function ScannerInspector({
  candidate,
  canOpenNew,
  mobileOpen,
  onCloseMobile,
  onStageOrder,
  onFundamentalsUpdated,
}: ScannerInspectorProps) {
  const [refreshingScreener, setRefreshingScreener] = useState(false);
  const [screenerError, setScreenerError] = useState<string | null>(null);

  async function handleRefreshScreener(symbol: string) {
    setRefreshingScreener(true);
    setScreenerError(null);
    try {
      const res = await apiFetch<ScannerFundamentalsRefreshResponse>(
        `/api/scanner/fundamentals/${encodeURIComponent(symbol)}`,
        { method: "POST" }
      );
      onFundamentalsUpdated(symbol, res);
    } catch (err) {
      setScreenerError(
        err instanceof ApiError
          ? err.message
          : "Failed to refresh Screener.in fundamentals."
      );
    } finally {
      setRefreshingScreener(false);
    }
  }

  const renderContent = (item: ScannerResultItem, isMobileDrawer: boolean) => {
    const f = item.fundamentals ?? {};
    const checks = item.fundamental_checks ?? {};
    const universeLabel =
      item.universe_tags && item.universe_tags.length > 0
        ? item.universe_tags.join(", ")
        : item.instrument_type || "EQ";

    return (
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-[var(--hify-text)]">
                {item.symbol} — {item.company_name}
              </h2>
              {item.passed ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-[#10B981]/10 px-2.5 py-0.5 text-xs font-semibold text-[#10B981]">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  PASS
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-[#F43F5E]/10 px-2.5 py-0.5 text-xs font-semibold text-[#F43F5E]">
                  <ShieldAlert className="h-3.5 w-3.5" />
                  FAIL
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-[var(--hify-text-secondary)]">
              {item.sector} · {item.cap_tier.toUpperCase()} Cap · {universeLabel}
            </p>
          </div>

          {isMobileDrawer && (
            <button
              type="button"
              onClick={onCloseMobile}
              aria-label="Close inspector"
              className="inline-flex min-h-[44px] min-w-[44px] shrink-0 items-center justify-center rounded-lg border border-[var(--hify-border)] text-[var(--hify-text-secondary)] hover:bg-[var(--hify-surface-raised)]"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!canOpenNew}
            onClick={() => onStageOrder(item)}
            className="inline-flex min-h-[44px] flex-1 items-center justify-center rounded-lg bg-[#C8A951] px-4 py-2 text-sm font-semibold text-[#18181B] transition-colors hover:bg-[#B6933A] disabled:cursor-not-allowed disabled:opacity-40"
          >
            Stage Limit Put
          </button>

          <button
            type="button"
            disabled={refreshingScreener}
            onClick={() => void handleRefreshScreener(item.symbol)}
            className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3 py-2 text-xs font-medium text-[var(--hify-text)] transition-colors hover:bg-[var(--hify-surface-raised)] disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${refreshingScreener ? "animate-spin" : ""}`}
            />
            <span>Refresh Screener</span>
          </button>
        </div>

        {screenerError && (
          <div className="rounded-lg border border-[var(--hify-error)] bg-[var(--hify-bg)] p-2.5 text-xs text-[var(--hify-error)]">
            {screenerError}
          </div>
        )}

        {/* Technical Envelope 2x2 KPI Grid */}
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--hify-text-secondary)]">
            Technical Envelope
          </p>
          <div className="grid grid-cols-2 gap-2.5 text-xs">
            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-3">
              <p className="text-[var(--hify-text-secondary)]">CMP · Intraday</p>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                ₹{formatNum(item.current_price)}{" "}
                <span
                  className={
                    item.is_red_candle
                      ? "text-[#F43F5E]"
                      : "text-[#10B981]"
                  }
                >
                  ({item.is_red_candle ? "-" : "+"}
                  {formatNum(Math.abs(item.intraday_drop_pct), 2)}%)
                </span>
              </p>
            </div>

            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-3">
              <p className="text-[var(--hify-text-secondary)]">
                Lower Blue Line (SMA200×0.86)
              </p>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                ₹{formatNum(item.lower_blue_line)} (
                {formatNum(item.lower_blue_line_distance_pct, 1)}%)
              </p>
            </div>

            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-3">
              <p className="text-[var(--hify-text-secondary)]">
                Moneyness · Strike · Lot / Margin
              </p>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {item.suggested_moneyness} · {item.option_strike ?? "—"} ·{" "}
                {item.lot_size} / {formatINR(item.margin_required)}
              </p>
            </div>

            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-3">
              <p className="text-[var(--hify-text-secondary)]">IV% · HV Spike</p>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {item.iv_pct !== undefined
                  ? `${formatNum(item.iv_pct, 1)}%`
                  : "—"}{" "}
                ·{" "}
                {item.hv_spike_ratio !== undefined
                  ? `${formatNum(item.hv_spike_ratio, 2)}x`
                  : "—"}
              </p>
            </div>
          </div>
        </div>

        {/* Full Screener.in Fundamental Pointers (2-column grid, never auto-hide) */}
        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--hify-text-secondary)]">
              Screener.in Fundamentals
            </p>
            {item.fundamental_passed !== undefined &&
              item.fundamental_passed !== null && (
                <CheckBadge status={item.fundamental_passed} />
              )}
          </div>

          <div className="grid grid-cols-2 gap-2.5 text-xs">
            {/* 1. Public % (< 30%) */}
            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-2.5">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[var(--hify-text-secondary)]">
                  Public % (&lt; 30%)
                </span>
                <CheckBadge status={checks.public_lt_30} />
              </div>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {formatNullableNum(f.public_holding_pct, 1, "%")}
              </p>
            </div>

            {/* 2. Pledge % (< 5%) */}
            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-2.5">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[var(--hify-text-secondary)]">
                  Pledge % (&lt; 5%)
                </span>
                <CheckBadge status={checks.pledge_lt_5} />
              </div>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {formatNullableNum(f.promoter_pledge_pct, 1, "%")}
              </p>
            </div>

            {/* 3. PE vs 3Y/5Y/10Y Median */}
            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-2.5">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[var(--hify-text-secondary)]">
                  PE vs 3Y/5Y/10Y
                </span>
                <CheckBadge
                  status={
                    checks.pe_lt_70 === false || checks.pe_lt_5y_median === false
                      ? false
                      : checks.pe_lt_5y_median ?? checks.pe_lt_70
                  }
                />
              </div>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {formatNullableNum(f.current_pe ?? item.current_pe, 1)} /{" "}
                {formatNullableNum(f.pe_median_3y, 1)}·
                {formatNullableNum(f.pe_median_5y ?? item.median_pe, 1)}·
                {formatNullableNum(f.pe_median_10y, 1)}
              </p>
            </div>

            {/* 4. ROCE % (>= 12%) */}
            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-2.5">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[var(--hify-text-secondary)]">
                  ROCE % (≥ 12%)
                </span>
                <CheckBadge status={checks.roce_or_roe_ok} />
              </div>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {formatNullableNum(f.roce_pct, 1, "%")}
              </p>
            </div>

            {/* 5. ROE % (>= 10%) */}
            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-2.5">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[var(--hify-text-secondary)]">
                  ROE % (≥ 10%)
                </span>
                <CheckBadge status={checks.roce_or_roe_ok} />
              </div>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {formatNullableNum(f.roe_pct, 1, "%")}
              </p>
            </div>

            {/* 6. D/E (<= 0.25) */}
            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-2.5">
              <div className="flex items-center justify-between gap-1">
                <span className="text-[var(--hify-text-secondary)]">
                  D/E (≤ 0.25)
                </span>
                <CheckBadge status={checks.de_le_025} />
              </div>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {formatNullableNum(f.debt_to_equity, 2)}
              </p>
            </div>

            {/* 7. 10Y Peak vs Latest Sales & PAT */}
            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-2.5">
              <span className="text-[var(--hify-text-secondary)]">
                10Y Peak vs Latest (S / PAT)
              </span>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {formatNullableNum(f.peak_sales_10y, 0)}→
                {formatNullableNum(f.latest_sales, 0)} /{" "}
                {formatNullableNum(f.peak_pat_10y, 0)}→
                {formatNullableNum(f.latest_pat, 0)}
              </p>
            </div>

            {/* 8. Interest Coverage */}
            <div className="rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-2.5">
              <span className="text-[var(--hify-text-secondary)]">
                Interest Coverage
              </span>
              <p className="font-mono font-mono-num mt-1 font-semibold text-[var(--hify-text)]">
                {formatNullableNum(f.interest_coverage, 2, "x")}
              </p>
            </div>

            {/* 9. PSU Hedge Note (full-width row) */}
            <div className="col-span-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-2.5">
              <div className="flex items-center gap-1.5 text-[var(--hify-text-secondary)]">
                {item.is_psu && (
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-[var(--hify-warning)]" />
                )}
                <span>PSU Hedge Note</span>
              </div>
              <p className="mt-1 text-xs font-medium text-[var(--hify-text)]">
                {item.hedge_note ??
                  (item.is_psu
                    ? "PSU stock — hedge required when selling puts."
                    : "—")}
              </p>
            </div>
          </div>
        </div>

        {/* Conditional compact Rule Rejections list */}
        {item.rejection_reasons.length > 0 && (
          <div className="rounded-lg border border-[var(--hify-error)] bg-[var(--hify-bg)] p-3 text-xs text-[var(--hify-error)]">
            <p className="font-semibold">Rule Rejections</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {item.rejection_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      {/* Persistent Right-Pane Inspector on lg+ */}
      <aside className="hidden lg:block">
        <div className="sticky top-4 max-h-[calc(100vh-6rem)] overflow-y-auto rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          {candidate ? (
            renderContent(candidate, false)
          ) : (
            <div className="py-12 text-center text-xs text-[var(--hify-text-secondary)]">
              Select a candidate from the scanner table to inspect technicals and
              Screener.in fundamentals.
            </div>
          )}
        </div>
      </aside>

      {/* Slide-Over Drawer on < lg */}
      {mobileOpen && candidate && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/50 lg:hidden"
          onClick={onCloseMobile}
        >
          <div
            className="h-full w-full max-w-md overflow-y-auto border-l border-[var(--hify-border)] bg-[var(--hify-surface)] p-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {renderContent(candidate, true)}
          </div>
        </div>
      )}
    </>
  );
}
