"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  FileSpreadsheet,
  FolderInput,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { ApiError, apiFetch, getApiBaseUrl } from "@/lib/api";
import {
  BackOfficeDeliveryAdjustment,
  BackOfficeImportLocalResponse,
  BackOfficeSummaryResponse,
  BackOfficeSyncKiteResponse,
  BackOfficeUploadResponse,
  formatINR,
  formatNum,
} from "@/lib/types";
import { SortableTh, useTableSort } from "@/components/SortableTh";

type BackOfficeTab = "ticker_pnl" | "symbol_pnl" | "fills" | "delivery_adj" | "charges";

export default function BackOfficePage() {
  const [data, setData] = useState<BackOfficeSummaryResponse | null>(null);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [appliedFilter, setAppliedFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<BackOfficeTab>("ticker_pnl");
  const [expandedTickers, setExpandedTickers] = useState<Record<string, boolean>>({});
  const [showDailyReview, setShowDailyReview] = useState(false);
  const autoSyncedRef = useRef(false);

  // Upload .xlsx Modal state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [tradebookFile, setTradebookFile] = useState<File | null>(null);
  const [pnlFile, setPnlFile] = useState<File | null>(null);

  // Delivery Equity Adjustment Modal state
  const [showDeliveryModal, setShowDeliveryModal] = useState(false);
  const [delivUnderlying, setDelivUnderlying] = useState("");
  const [delivContract, setDelivContract] = useState("");
  const [delivStrike, setDelivStrike] = useState("");
  const [delivExpiry, setDelivExpiry] = useState("");
  const [delivQty, setDelivQty] = useState("");
  const [delivSellPrice, setDelivSellPrice] = useState("");
  const [delivSellDate, setDelivSellDate] = useState("2026-11-25");
  const [delivOrderId, setDelivOrderId] = useState("");
  const [delivTradeIds, setDelivTradeIds] = useState("");
  const [delivCharges, setDelivCharges] = useState("0");
  const [delivConsoleFifoPnl, setDelivConsoleFifoPnl] = useState("");
  const [delivReason, setDelivReason] = useState("MISSED_ROLLOVER_DELIVERY");
  const [delivNotes, setDelivNotes] = useState("");

  const loadSummary = useCallback(async (filterVal = "") => {
    setLoading(true);
    setError(null);
    try {
      const qs = filterVal.trim()
        ? `?symbol=${encodeURIComponent(filterVal.trim())}`
        : "";
      const res = await apiFetch<BackOfficeSummaryResponse>(
        `/api/backoffice/summary${qs}`
      );
      setData(res);
      return res;
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to load Back Office summary."
      );
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSyncKiteTrades = useCallback(
    async (isAuto = false) => {
      setBusyAction("sync");
      setError(null);
      if (!isAuto) setBanner(null);
      try {
        const res = await apiFetch<BackOfficeSyncKiteResponse>(
          "/api/backoffice/sync-kite-trades",
          { method: "POST" }
        );
        if (res.is_dry_run) {
          setBanner(
            res.message ??
              "Kite is in dry-run mode. Connect live Kite session to sync today's trades."
          );
        } else {
          setBanner(
            `${isAuto ? "Auto-synced" : "Synced"} ${res.synced_fills} live fill(s) & ${res.open_positions_count ?? 0} open position(s) from Kite (${res.skipped_duplicates} duplicate(s) skipped).`
          );
          setShowDailyReview(true);
        }
        await loadSummary(appliedFilter);
      } catch (err) {
        setError(
          err instanceof ApiError ? err.message : "Failed to sync Kite trades."
        );
      } finally {
        setBusyAction(null);
      }
    },
    [appliedFilter, loadSummary]
  );

  useEffect(() => {
    loadSummary(appliedFilter).then((res) => {
      if (
        res &&
        !autoSyncedRef.current &&
        res.sync_status?.kite_connected &&
        !res.sync_status?.synced_today
      ) {
        autoSyncedRef.current = true;
        handleSyncKiteTrades(true);
      }
    });
  }, [loadSummary, appliedFilter, handleSyncKiteTrades]);

  async function handleImportLocal() {
    setBusyAction("local");
    setError(null);
    setBanner(null);
    try {
      const res = await apiFetch<BackOfficeImportLocalResponse>(
        "/api/backoffice/import-local",
        { method: "POST" }
      );
      const tbInserted = res.tradebook_files.reduce(
        (acc, item) => acc + item.inserted_fills,
        0
      );
      const tbSkipped = res.tradebook_files.reduce(
        (acc, item) => acc + item.skipped_duplicates,
        0
      );
      setBanner(
        `Imported ${res.tradebook_files.length} Tradebook(s) (+${tbInserted} fills, ${tbSkipped} skipped) and ${res.pnl_files.length} P&L statement(s) from Console_Reports/FY2627_FNO.`
      );
      await loadSummary(appliedFilter);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to import local Console_Reports/FY2627_FNO files."
      );
    } finally {
      setBusyAction(null);
    }
  }

  async function handleUploadSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!tradebookFile && !pnlFile) {
      setError("Select at least a Tradebook .xlsx or P&L .xlsx file.");
      return;
    }
    setBusyAction("upload");
    setError(null);
    setBanner(null);

    try {
      const formData = new FormData();
      if (tradebookFile) formData.append("tradebook_file", tradebookFile);
      if (pnlFile) formData.append("pnl_file", pnlFile);

      const response = await fetch(`${getApiBaseUrl()}/api/backoffice/upload`, {
        method: "POST",
        body: formData,
        cache: "no-store",
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Upload failed (${response.status})`);
      }
      const res = (await response.json()) as BackOfficeUploadResponse;
      const parts: string[] = [];
      if (res.tradebook) {
        parts.push(
          `Tradebook: +${res.tradebook.inserted_fills} fills (${res.tradebook.skipped_duplicates} duplicates skipped)`
        );
      }
      if (res.pnl) {
        parts.push(
          `P&L: Realized ${formatINR(res.pnl.realized_pnl, true)}, Charges ${formatINR(res.pnl.charges)}`
        );
      }
      setBanner(parts.join(" | ") || "Upload complete.");
      setTradebookFile(null);
      setPnlFile(null);
      setShowUploadModal(false);
      await loadSummary(appliedFilter);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to upload Console files."
      );
    } finally {
      setBusyAction(null);
    }
  }

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    setAppliedFilter(symbolSearch);
  }

  async function handleCreateDeliveryAdj(e: React.FormEvent) {
    e.preventDefault();
    setBusyAction("delivery");
    setError(null);
    setBanner(null);
    try {
      const payload = {
        underlying: delivUnderlying.trim().toUpperCase(),
        fno_contract: delivContract.trim().toUpperCase(),
        fno_strike: Number(delivStrike),
        fno_expiry: delivExpiry.trim(),
        qty: Number(delivQty),
        equity_sell_price: Number(delivSellPrice),
        equity_sell_date: delivSellDate.trim(),
        equity_order_id: delivOrderId.trim(),
        equity_trade_ids: delivTradeIds.trim(),
        charges: Number(delivCharges || 0),
        console_fifo_pnl:
          delivConsoleFifoPnl.trim() !== "" ? Number(delivConsoleFifoPnl) : null,
        reason: delivReason.trim() || "MISSED_ROLLOVER_DELIVERY",
        notes: delivNotes.trim(),
      };
      const res = await apiFetch<{ item: BackOfficeDeliveryAdjustment }>(
        "/api/backoffice/delivery-adjustments",
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
      setBanner(
        `Recorded ${res.item.underlying} delivery equity exit: ${formatINR(res.item.economic_pnl, true)} (Option A Strike-to-Sell).`
      );
      setShowDeliveryModal(false);
      setDelivUnderlying("");
      setDelivContract("");
      setDelivStrike("");
      setDelivExpiry("");
      setDelivQty("");
      setDelivSellPrice("");
      setDelivOrderId("");
      setDelivTradeIds("");
      setDelivCharges("0");
      setDelivConsoleFifoPnl("");
      setDelivNotes("");
      setActiveTab("delivery_adj");
      await loadSummary(appliedFilter);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to save delivery equity adjustment."
      );
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDeleteDeliveryAdj(id: number, underlying: string) {
    setBusyAction("delivery");
    setError(null);
    setBanner(null);
    try {
      await apiFetch(`/api/backoffice/delivery-adjustments/${id}`, {
        method: "DELETE",
      });
      setBanner(`Removed delivery equity adjustment for ${underlying}.`);
      await loadSummary(appliedFilter);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to delete delivery equity adjustment."
      );
    } finally {
      setBusyAction(null);
    }
  }

  const summary = data?.summary;
  const unified = data?.unified_summary;
  const syncStatus = data?.sync_status;
  const tickerRows = data?.ticker_pnl ?? [];
  const symbolRows = data?.symbol_pnl ?? [];
  const fillRows = data?.recent_fills ?? [];
  const deliveryRows = data?.delivery_adjustments ?? [];
  const chargeEntries = Object.entries(data?.charges_breakdown ?? {});

  const tickerSort = useTableSort(tickerRows, "net_pnl", "desc", {
    ticker: (r) => r.ticker,
    status: (r) => r.status,
    contracts_count: (r) => r.contracts_count,
    realized_pnl: (r) => r.realized_pnl,
    unrealized_pnl: (r) => r.unrealized_pnl,
    net_pnl: (r) => r.net_pnl,
  });

  const symbolSort = useTableSort(symbolRows, "realized_pnl", "desc", {
    symbol: (r) => r.symbol,
    quantity: (r) => r.quantity,
    buy_value: (r) => r.buy_value,
    sell_value: (r) => r.sell_value,
    realized_pnl: (r) => r.realized_pnl,
    open_quantity: (r) => r.open_quantity,
    unrealized_pnl: (r) => r.unrealized_pnl,
  });

  const fillsSort = useTableSort(fillRows, "execution_time", "desc", {
    execution_time: (r) => r.execution_time,
    symbol: (r) => r.symbol,
    trade_type: (r) => r.trade_type,
    quantity: (r) => r.quantity,
    price: (r) => r.price,
    expiry_date: (r) => r.expiry_date,
    source: (r) => r.source,
  });

  const totalRealized = unified?.total_realized_pnl ?? summary?.realized_pnl ?? 0;
  const kiteDeltaRealized = unified?.kite_live_delta_realized_pnl ?? 0;
  const totalCharges = unified?.charges ?? summary?.charges ?? 0;
  const netRealized = unified?.net_realized_pnl ?? summary?.net_realized_pnl ?? 0;
  const liveUnrealized = unified?.unrealized_pnl ?? summary?.unrealized_pnl ?? 0;
  const netTradingPnl = unified?.net_trading_pnl ?? totalRealized + liveUnrealized;
  const deliveryEquityPnl = unified?.delivery_equity_pnl ?? 0;
  const trueStrategyNetTradingPnl =
    unified?.true_strategy_net_trading_pnl ?? netTradingPnl + deliveryEquityPnl;
  const hasDeliveryAdj = (unified?.delivery_adjustments_count ?? deliveryRows.length) > 0;

  function toggleTicker(ticker: string) {
    setExpandedTickers((prev) => ({ ...prev, [ticker]: !prev[ticker] }));
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2.5">
          <FileSpreadsheet className="h-5 w-5 text-[var(--hify-gold-deep)] dark:text-[var(--hify-gold)]" />
          <h1 className="text-xl font-semibold tracking-tight text-[var(--hify-text)]">
            Back Office
          </h1>
          {summary?.period_label && (
            <span className="rounded-full border border-[var(--hify-border)] bg-[var(--hify-surface)] px-2.5 py-0.5 font-mono text-[11px] text-[var(--hify-text-secondary)]">
              {summary.period_label}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => handleSyncKiteTrades(false)}
            disabled={busyAction !== null}
            className="relative inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3.5 text-xs font-medium text-[var(--hify-text)] transition-colors hover:border-[var(--hify-gold)] disabled:opacity-50"
          >
            <RefreshCw
              className={`h-4 w-4 ${busyAction === "sync" ? "animate-spin" : ""}`}
            />
            <span>Sync &amp; Review</span>
            {syncStatus && !syncStatus.synced_today && (
              <span
                className="h-2 w-2 rounded-full bg-[var(--hify-warning)]"
                title="Today's Kite sync pending"
              />
            )}
          </button>

          <button
            type="button"
            onClick={() => setShowDeliveryModal(true)}
            disabled={busyAction !== null}
            className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3.5 text-xs font-medium text-[var(--hify-text)] transition-colors hover:border-[var(--hify-gold)] disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
            <span>Delivery Exit</span>
          </button>

          <button
            type="button"
            onClick={() => setShowUploadModal(true)}
            disabled={busyAction !== null}
            className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3.5 text-xs font-medium text-[var(--hify-text)] transition-colors hover:border-[var(--hify-gold)] disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            <span>Upload .xlsx</span>
          </button>

          <button
            type="button"
            onClick={handleImportLocal}
            disabled={busyAction !== null}
            className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--hify-gold)] px-4 text-xs font-semibold text-[#18181B] transition-colors hover:bg-[var(--hify-gold-hover)] disabled:opacity-50"
          >
            <FolderInput className="h-4 w-4" />
            <span>Import Local</span>
          </button>
        </div>
      </div>

      {/* Unified Source & Gap Status Strip */}
      {syncStatus && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3.5 py-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[var(--hify-text-secondary)]">
            <span>
              Console Baseline:{" "}
              <strong className="font-mono text-[var(--hify-text)]">
                {syncStatus.console_last_trade_date ?? "Not imported"}
              </strong>
            </span>
            <span>
              Kite Live Sync:{" "}
              <strong
                className={`font-mono ${
                  syncStatus.synced_today
                    ? "text-[var(--hify-success)]"
                    : "text-[var(--hify-warning)]"
                }`}
              >
                {syncStatus.synced_today
                  ? `Synced today (${syncStatus.kite_last_sync_date})`
                  : syncStatus.kite_last_sync_date
                  ? `Last: ${syncStatus.kite_last_sync_date}`
                  : "Pending"}
              </strong>
            </span>
            <span>
              Unrealized Source:{" "}
              <strong className="font-mono text-[var(--hify-text)]">
                {unified?.unrealized_source ?? "CONSOLE"}
              </strong>
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {syncStatus.gap_days_count > 0 && (
              <span
                className="inline-flex items-center gap-1 rounded-full border border-[var(--hify-warning)]/40 bg-[var(--hify-warning)]/10 px-2.5 py-0.5 font-mono text-[11px] font-medium text-[var(--hify-warning)]"
                title={`Missed weekdays: ${syncStatus.gap_days.join(", ")}`}
              >
                <AlertTriangle className="h-3 w-3" />
                {syncStatus.gap_days_count} day gap — upload Console .xlsx
              </span>
            )}
            {syncStatus.synced_today && (
              <button
                type="button"
                onClick={() => setShowDailyReview((v) => !v)}
                className="font-medium text-[var(--hify-gold-deep)] hover:underline dark:text-[var(--hify-gold)]"
              >
                {showDailyReview ? "Hide Daily Review" : "Show Daily Review"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Daily Sync Reminder (when not connected & not synced today) */}
      {syncStatus && !syncStatus.synced_today && !syncStatus.kite_connected && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--hify-warning)]/40 bg-[var(--hify-warning)]/10 p-3 text-xs text-[var(--hify-warning)]">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 shrink-0" />
            <span>
              <strong>Daily Sync Reminder:</strong> Kite is not connected yet
              today. Connect <strong>Kite Login</strong> to auto-sync today&apos;s
              trades and live unrealized MTM.
            </span>
          </div>
        </div>
      )}

      {/* Daily Review Card */}
      {showDailyReview && syncStatus?.today_review && (
        <div className="rounded-xl border border-[var(--hify-gold)]/40 bg-[var(--hify-surface)] p-4">
          <div className="mb-2.5 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--hify-gold-deep)] dark:text-[var(--hify-gold)]">
              Daily Sync &amp; Review ({syncStatus.kite_last_sync_date ?? "Today"})
            </h2>
            <button
              type="button"
              onClick={() => setShowDailyReview(false)}
              className="text-xs text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
            >
              Dismiss
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <p className="text-[11px] text-[var(--hify-text-secondary)]">
                Fills Today
              </p>
              <p className="font-mono font-mono-num text-sm font-semibold text-[var(--hify-text)]">
                {syncStatus.today_review.fills_today}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-[var(--hify-text-secondary)]">
                Closed Round-Trips
              </p>
              <p className="font-mono font-mono-num text-sm font-semibold text-[var(--hify-text)]">
                {syncStatus.today_review.closed_trades_today}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-[var(--hify-text-secondary)]">
                Realized Today
              </p>
              <p
                className={`font-mono font-mono-num text-sm font-semibold ${
                  syncStatus.today_review.realized_today >= 0
                    ? "text-[var(--hify-success)]"
                    : "text-[var(--hify-error)]"
                }`}
              >
                {formatINR(syncStatus.today_review.realized_today, true)}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-[var(--hify-text-secondary)]">
                Open Positions ({syncStatus.today_review.open_positions_count})
              </p>
              <p
                className={`font-mono font-mono-num text-sm font-semibold ${
                  syncStatus.today_review.live_unrealized_pnl >= 0
                    ? "text-[var(--hify-success)]"
                    : "text-[var(--hify-error)]"
                }`}
              >
                {formatINR(syncStatus.today_review.live_unrealized_pnl, true)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Feedback Banners */}
      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-[var(--hify-error)]/40 bg-[var(--hify-error)]/10 p-3 text-sm text-[var(--hify-error)]">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {banner && (
        <div className="flex items-start gap-2 rounded-xl border border-[var(--hify-gold)]/40 bg-[var(--hify-gold-milestone)] p-3 text-sm text-[var(--hify-gold-deep)] dark:bg-[var(--hify-surface-raised)] dark:text-[var(--hify-gold)]">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{banner}</span>
        </div>
      )}

      {/* Unified KPI Cards (Console Baseline + Kite Live Delta) */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard
          label={
            kiteDeltaRealized !== 0
              ? `Realized (Kite ${formatINR(kiteDeltaRealized, true)})`
              : "Gross Realized P&L"
          }
          value={formatINR(totalRealized, true)}
          tone={totalRealized >= 0 ? "success" : "error"}
        />
        <KpiCard
          label="Total Charges"
          value={formatINR(totalCharges)}
          tone="warning"
        />
        <KpiCard
          label="Net Realized (After Tax)"
          value={formatINR(netRealized, true)}
          tone={netRealized >= 0 ? "success" : "error"}
        />
        <KpiCard
          label={`Unrealized (${unified?.unrealized_source === "KITE_LIVE" ? "Live" : "Console"})`}
          value={formatINR(liveUnrealized, true)}
          tone={liveUnrealized >= 0 ? "success" : "error"}
        />
        <KpiCard
          label="Net Trading P&L (R+U)"
          value={formatINR(netTradingPnl, true)}
          tone={netTradingPnl >= 0 ? "success" : "error"}
        />
      </div>

      {/* True Strategy Accountability Strip (when Delivery Equity Exits exist) */}
      {hasDeliveryAdj && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <KpiCard
            label={`Delivery Eq Price P&L (${deliveryRows.length} Exit${deliveryRows.length === 1 ? "" : "s"})`}
            value={formatINR(unified?.delivery_equity_price_pnl ?? deliveryEquityPnl, true)}
            tone={(unified?.delivery_equity_price_pnl ?? deliveryEquityPnl) >= 0 ? "success" : "error"}
          />
          <KpiCard
            label="Delivery & Eq Exit Charges (CNT)"
            value={formatINR(unified?.delivery_equity_charges ?? 0)}
            tone="warning"
          />
          <KpiCard
            label="True Strategy Net P&L (After All Charges)"
            value={formatINR(trueStrategyNetTradingPnl, true)}
            tone={trueStrategyNetTradingPnl >= 0 ? "success" : "error"}
          />
        </div>
      )}

      {/* Symbol / Ticker Filter Bar */}
      <form
        onSubmit={handleSearchSubmit}
        className="flex flex-col gap-2 sm:flex-row sm:items-center"
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--hify-text-secondary)]" />
          <input
            type="text"
            value={symbolSearch}
            onChange={(e) => setSymbolSearch(e.target.value)}
            placeholder="Filter by ticker or contract (e.g. TMPV, COLPAL, TCS, DABUR)..."
            className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] pl-9 pr-3 text-sm text-[var(--hify-text)] placeholder:text-[var(--hify-text-secondary)] focus:border-[var(--hify-gold)] focus:outline-none"
          />
        </div>
        <button
          type="submit"
          className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-4 text-sm font-medium text-[var(--hify-text)] hover:border-[var(--hify-gold)]"
        >
          Filter
        </button>
        {appliedFilter && (
          <button
            type="button"
            onClick={() => {
              setSymbolSearch("");
              setAppliedFilter("");
            }}
            className="min-h-[44px] rounded-lg border border-[var(--hify-border)] px-4 text-sm text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
          >
            Clear
          </button>
        )}
      </form>

      {/* Tabbed Data Card */}
      <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)]">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--hify-border)] px-4 py-2">
          <div className="flex flex-wrap gap-1" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "ticker_pnl"}
              onClick={() => setActiveTab("ticker_pnl")}
              className={`min-h-[44px] rounded-lg px-3.5 text-xs font-semibold transition-colors ${
                activeTab === "ticker_pnl"
                  ? "bg-[var(--hify-gold-milestone)] text-[var(--hify-gold-deep)] dark:bg-[var(--hify-surface-raised)] dark:text-[var(--hify-gold)]"
                  : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
              }`}
            >
              Ticker P&amp;L ({tickerRows.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "symbol_pnl"}
              onClick={() => setActiveTab("symbol_pnl")}
              className={`min-h-[44px] rounded-lg px-3.5 text-xs font-semibold transition-colors ${
                activeTab === "symbol_pnl"
                  ? "bg-[var(--hify-gold-milestone)] text-[var(--hify-gold-deep)] dark:bg-[var(--hify-surface-raised)] dark:text-[var(--hify-gold)]"
                  : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
              }`}
            >
              Contracts ({data?.symbol_pnl.length ?? 0})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "fills"}
              onClick={() => setActiveTab("fills")}
              className={`min-h-[44px] rounded-lg px-3.5 text-xs font-semibold transition-colors ${
                activeTab === "fills"
                  ? "bg-[var(--hify-gold-milestone)] text-[var(--hify-gold-deep)] dark:bg-[var(--hify-surface-raised)] dark:text-[var(--hify-gold)]"
                  : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
              }`}
            >
              Fills ({data?.recent_fills.length ?? 0} /{" "}
              {data?.total_fills_count ?? 0})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "delivery_adj"}
              onClick={() => setActiveTab("delivery_adj")}
              className={`min-h-[44px] rounded-lg px-3.5 text-xs font-semibold transition-colors ${
                activeTab === "delivery_adj"
                  ? "bg-[var(--hify-gold-milestone)] text-[var(--hify-gold-deep)] dark:bg-[var(--hify-surface-raised)] dark:text-[var(--hify-gold)]"
                  : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
              }`}
            >
              Delivery Adj. ({deliveryRows.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "charges"}
              onClick={() => setActiveTab("charges")}
              className={`min-h-[44px] rounded-lg px-3.5 text-xs font-semibold transition-colors ${
                activeTab === "charges"
                  ? "bg-[var(--hify-gold-milestone)] text-[var(--hify-gold-deep)] dark:bg-[var(--hify-surface-raised)] dark:text-[var(--hify-gold)]"
                  : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
              }`}
            >
              Charges ({chargeEntries.length})
            </button>
          </div>
          {loading && (
            <span className="text-xs text-[var(--hify-text-secondary)]">
              Loading...
            </span>
          )}
        </div>

        <div className="p-4">
          {activeTab === "ticker_pnl" && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[680px] text-left text-xs">
                <thead>
                  <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                    <SortableTh label="Ticker" columnKey="ticker" activeKey={tickerSort.sortKey} dir={tickerSort.sortDir} onSort={tickerSort.toggleSort} className="py-2 pr-3" />
                    <SortableTh label="Status" columnKey="status" activeKey={tickerSort.sortKey} dir={tickerSort.sortDir} onSort={tickerSort.toggleSort} className="py-2 pr-3" />
                    <SortableTh label="Contracts" columnKey="contracts_count" activeKey={tickerSort.sortKey} dir={tickerSort.sortDir} onSort={tickerSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Cumulative Realized" columnKey="realized_pnl" activeKey={tickerSort.sortKey} dir={tickerSort.sortDir} onSort={tickerSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Unrealized" columnKey="unrealized_pnl" activeKey={tickerSort.sortKey} dir={tickerSort.sortDir} onSort={tickerSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Net P&L (R+U)" columnKey="net_pnl" activeKey={tickerSort.sortKey} dir={tickerSort.sortDir} onSort={tickerSort.toggleSort} align="right" className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--hify-border)]/60">
                  {tickerSort.sortedRows.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        className="py-6 text-center text-[var(--hify-text-secondary)]"
                      >
                        No ticker P&amp;L rows found. Import Console P&amp;L or sync Kite trades.
                      </td>
                    </tr>
                  ) : (
                    tickerSort.sortedRows.map((tRow) => {
                      const isExpanded = !!expandedTickers[tRow.ticker];
                      return (
                        <React.Fragment key={tRow.ticker}>
                          <tr
                            onClick={() => toggleTicker(tRow.ticker)}
                            className="cursor-pointer hover:bg-[var(--hify-bg)]/60"
                          >
                            <td className="py-2.5 pr-3 font-mono font-semibold text-[var(--hify-text)]">
                              <span className="inline-flex items-center gap-1.5">
                                {isExpanded ? (
                                  <ChevronDown className="h-3.5 w-3.5 text-[var(--hify-text-secondary)]" />
                                ) : (
                                  <ChevronRight className="h-3.5 w-3.5 text-[var(--hify-text-secondary)]" />
                                )}
                                {tRow.ticker}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3">
                              <span
                                className={`inline-flex rounded px-2 py-0.5 text-[11px] font-semibold ${
                                  tRow.status === "PROFIT"
                                    ? "bg-[var(--hify-success)]/15 text-[var(--hify-success)]"
                                    : "bg-[var(--hify-error)]/15 text-[var(--hify-error)]"
                                }`}
                              >
                                {tRow.status}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-right font-mono font-mono-num text-[var(--hify-text-secondary)]">
                              {tRow.contracts_count}
                              {tRow.open_contracts_count > 0
                                ? ` (${tRow.open_contracts_count} open)`
                                : ""}
                            </td>
                            <td
                              className={`py-2.5 pr-3 text-right font-mono font-mono-num font-medium ${
                                tRow.realized_pnl >= 0
                                  ? "text-[var(--hify-success)]"
                                  : "text-[var(--hify-error)]"
                              }`}
                            >
                              {formatINR(tRow.realized_pnl, true)}
                            </td>
                            <td
                              className={`py-2.5 pr-3 text-right font-mono font-mono-num font-medium ${
                                tRow.unrealized_pnl >= 0
                                  ? "text-[var(--hify-success)]"
                                  : "text-[var(--hify-error)]"
                              }`}
                            >
                              {formatINR(tRow.unrealized_pnl, true)}
                            </td>
                            <td
                              className={`py-2.5 text-right font-mono font-mono-num font-semibold ${
                                tRow.net_pnl >= 0
                                  ? "text-[var(--hify-success)]"
                                  : "text-[var(--hify-error)]"
                              }`}
                            >
                              {formatINR(tRow.net_pnl, true)}
                            </td>
                          </tr>
                          {isExpanded &&
                            tRow.contracts.map((c) => (
                              <tr
                                key={`${tRow.ticker}-${c.symbol}`}
                                className="bg-[var(--hify-bg)]/40 text-[11px]"
                              >
                                <td className="py-2 pl-7 pr-3 font-mono text-[var(--hify-text-secondary)]">
                                  {c.symbol}
                                </td>
                                <td className="py-2 pr-3 font-mono text-[10px] text-[var(--hify-text-secondary)]">
                                  {c.source}
                                </td>
                                <td className="py-2 pr-3 text-right font-mono font-mono-num text-[var(--hify-text-secondary)]">
                                  {c.open_qty !== 0 ? `Open ${c.open_qty}` : "Closed"}
                                </td>
                                <td
                                  className={`py-2 pr-3 text-right font-mono font-mono-num ${
                                    c.realized_pnl >= 0
                                      ? "text-[var(--hify-success)]"
                                      : "text-[var(--hify-error)]"
                                  }`}
                                >
                                  {formatINR(c.realized_pnl, true)}
                                </td>
                                <td
                                  className={`py-2 pr-3 text-right font-mono font-mono-num ${
                                    c.unrealized_pnl >= 0
                                      ? "text-[var(--hify-success)]"
                                      : "text-[var(--hify-error)]"
                                  }`}
                                >
                                  {formatINR(c.unrealized_pnl, true)}
                                </td>
                                <td
                                  className={`py-2 text-right font-mono font-mono-num font-medium ${
                                    c.net_pnl >= 0
                                      ? "text-[var(--hify-success)]"
                                      : "text-[var(--hify-error)]"
                                  }`}
                                >
                                  {formatINR(c.net_pnl, true)}
                                </td>
                              </tr>
                            ))}
                        </React.Fragment>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
          {activeTab === "symbol_pnl" && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-xs">
                <thead>
                  <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                    <SortableTh label="Symbol" columnKey="symbol" activeKey={symbolSort.sortKey} dir={symbolSort.sortDir} onSort={symbolSort.toggleSort} className="py-2 pr-3" />
                    <SortableTh label="Qty" columnKey="quantity" activeKey={symbolSort.sortKey} dir={symbolSort.sortDir} onSort={symbolSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Buy Value" columnKey="buy_value" activeKey={symbolSort.sortKey} dir={symbolSort.sortDir} onSort={symbolSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Sell Value" columnKey="sell_value" activeKey={symbolSort.sortKey} dir={symbolSort.sortDir} onSort={symbolSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Realized P&L" columnKey="realized_pnl" activeKey={symbolSort.sortKey} dir={symbolSort.sortDir} onSort={symbolSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Open Qty" columnKey="open_quantity" activeKey={symbolSort.sortKey} dir={symbolSort.sortDir} onSort={symbolSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Unrealized P&L" columnKey="unrealized_pnl" activeKey={symbolSort.sortKey} dir={symbolSort.sortDir} onSort={symbolSort.toggleSort} align="right" className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--hify-border)]/60">
                  {symbolSort.sortedRows.length === 0 ? (
                    <tr>
                      <td
                        colSpan={7}
                        className="py-6 text-center text-[var(--hify-text-secondary)]"
                      >
                        No symbol P&amp;L rows found. Import Console P&amp;L to populate.
                      </td>
                    </tr>
                  ) : (
                    symbolSort.sortedRows.map((row) => (
                      <tr key={row.symbol} className="hover:bg-[var(--hify-bg)]/60">
                        <td className="py-2.5 pr-3 font-mono font-mono-num font-medium text-[var(--hify-text)]">
                          {row.symbol}
                        </td>
                        <td className="py-2.5 pr-3 text-right font-mono font-mono-num">
                          {row.quantity}
                        </td>
                        <td className="py-2.5 pr-3 text-right font-mono font-mono-num">
                          {formatINR(row.buy_value)}
                        </td>
                        <td className="py-2.5 pr-3 text-right font-mono font-mono-num">
                          {formatINR(row.sell_value)}
                        </td>
                        <td
                          className={`py-2.5 pr-3 text-right font-mono font-mono-num font-semibold ${
                            row.realized_pnl >= 0
                              ? "text-[var(--hify-success)]"
                              : "text-[var(--hify-error)]"
                          }`}
                        >
                          {formatINR(row.realized_pnl, true)}
                        </td>
                        <td className="py-2.5 pr-3 text-right font-mono font-mono-num">
                          {row.open_quantity}{" "}
                          {row.open_quantity_type
                            ? `(${row.open_quantity_type.toUpperCase()})`
                            : ""}
                        </td>
                        <td
                          className={`py-2.5 text-right font-mono font-mono-num font-semibold ${
                            row.unrealized_pnl >= 0
                              ? "text-[var(--hify-success)]"
                              : "text-[var(--hify-error)]"
                          }`}
                        >
                          {formatINR(row.unrealized_pnl, true)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === "fills" && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-xs">
                <thead>
                  <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                    <SortableTh label="Execution Time" columnKey="execution_time" activeKey={fillsSort.sortKey} dir={fillsSort.sortDir} onSort={fillsSort.toggleSort} className="py-2 pr-3" />
                    <SortableTh label="Symbol" columnKey="symbol" activeKey={fillsSort.sortKey} dir={fillsSort.sortDir} onSort={fillsSort.toggleSort} className="py-2 pr-3" />
                    <SortableTh label="Side" columnKey="trade_type" activeKey={fillsSort.sortKey} dir={fillsSort.sortDir} onSort={fillsSort.toggleSort} className="py-2 pr-3" />
                    <SortableTh label="Qty" columnKey="quantity" activeKey={fillsSort.sortKey} dir={fillsSort.sortDir} onSort={fillsSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Price" columnKey="price" activeKey={fillsSort.sortKey} dir={fillsSort.sortDir} onSort={fillsSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Expiry" columnKey="expiry_date" activeKey={fillsSort.sortKey} dir={fillsSort.sortDir} onSort={fillsSort.toggleSort} className="py-2 pr-3" />
                    <SortableTh label="Source" columnKey="source" activeKey={fillsSort.sortKey} dir={fillsSort.sortDir} onSort={fillsSort.toggleSort} className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--hify-border)]/60">
                  {fillsSort.sortedRows.length === 0 ? (
                    <tr>
                      <td
                        colSpan={7}
                        className="py-6 text-center text-[var(--hify-text-secondary)]"
                      >
                        No fills recorded yet. Import a Tradebook or sync Kite trades.
                      </td>
                    </tr>
                  ) : (
                    fillsSort.sortedRows.map((fill) => (
                      <tr key={fill.id} className="hover:bg-[var(--hify-bg)]/60">
                        <td className="py-2 pr-3 font-mono font-mono-num text-[var(--hify-text-secondary)]">
                          {fill.execution_time}
                        </td>
                        <td className="py-2 pr-3 font-mono font-mono-num font-medium text-[var(--hify-text)]">
                          {fill.symbol}
                        </td>
                        <td className="py-2 pr-3">
                          <span
                            className={`inline-flex rounded px-2 py-0.5 text-[11px] font-semibold ${
                              fill.trade_type === "SELL"
                                ? "bg-[var(--hify-gold-milestone)] text-[var(--hify-gold-deep)] dark:bg-[var(--hify-surface-raised)] dark:text-[var(--hify-gold)]"
                                : "bg-[var(--hify-bg)] text-[var(--hify-text-secondary)]"
                            }`}
                          >
                            {fill.trade_type}
                          </span>
                        </td>
                        <td className="py-2 pr-3 text-right font-mono font-mono-num">
                          {fill.quantity}
                        </td>
                        <td className="py-2 pr-3 text-right font-mono font-mono-num">
                          {formatNum(fill.price, 2)}
                        </td>
                        <td className="py-2 pr-3 font-mono font-mono-num text-[var(--hify-text-secondary)]">
                          {fill.expiry_date || "—"}
                        </td>
                        <td className="py-2 font-mono text-[11px] text-[var(--hify-text-secondary)]">
                          {fill.source}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === "delivery_adj" && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--hify-text-secondary)]">
                <span>
                  Option A (Strike-to-Sell):{" "}
                  <span className="font-mono text-[var(--hify-text)]">
                    (Equity Sell Price − F&amp;O Strike) × Qty − Charges
                  </span>
                  . Tagged <code className="font-mono">BOOKED_IN_OPTIONS</code> to avoid double-counting in the future Equity Log.
                </span>
                <button
                  type="button"
                  onClick={() => setShowDeliveryModal(true)}
                  className="inline-flex min-h-[36px] items-center gap-1.5 rounded-lg bg-[var(--hify-gold)] px-3 text-xs font-semibold text-[#18181B] hover:bg-[var(--hify-gold-hover)]"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Add Delivery Exit</span>
                </button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[780px] text-left text-xs">
                  <thead>
                    <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                      <th className="py-2 pr-3 font-medium">Ticker</th>
                      <th className="py-2 pr-3 font-medium">F&amp;O Contract / Strike</th>
                      <th className="py-2 pr-3 text-right font-medium">Qty</th>
                      <th className="py-2 pr-3 text-right font-medium">Eq Sell</th>
                      <th className="py-2 pr-3 font-medium">Sell Date / Order</th>
                      <th className="py-2 pr-3 text-right font-medium">Economic P&amp;L</th>
                      <th className="py-2 pr-3 text-right font-medium">FIFO Ref</th>
                      <th className="py-2 pr-3 font-medium">Handoff</th>
                      <th className="py-2 text-right font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--hify-border)]/60">
                    {deliveryRows.length === 0 ? (
                      <tr>
                        <td
                          colSpan={9}
                          className="py-6 text-center text-[var(--hify-text-secondary)]"
                        >
                          No physical-delivery equity exits logged yet.
                        </td>
                      </tr>
                    ) : (
                      deliveryRows.map((adj) => (
                        <tr key={adj.id} className="hover:bg-[var(--hify-bg)]/60">
                          <td className="py-2.5 pr-3 font-mono font-semibold text-[var(--hify-text)]">
                            {adj.underlying}
                          </td>
                          <td className="py-2.5 pr-3 font-mono text-[var(--hify-text-secondary)]">
                            {adj.fno_contract || `${adj.underlying} @ ₹${formatNum(adj.fno_strike, 2)}`}
                            <span className="ml-1.5 text-[11px]">
                              (Strike ₹{formatNum(adj.fno_strike, 2)})
                            </span>
                          </td>
                          <td className="py-2.5 pr-3 text-right font-mono font-mono-num">
                            {adj.qty}
                          </td>
                          <td className="py-2.5 pr-3 text-right font-mono font-mono-num">
                            ₹{formatNum(adj.equity_sell_price, 2)}
                          </td>
                          <td className="py-2.5 pr-3 font-mono text-[11px] text-[var(--hify-text-secondary)]">
                            <div>{adj.equity_sell_date}</div>
                            {adj.equity_order_id && <div>Ord: {adj.equity_order_id}</div>}
                          </td>
                          <td
                            className={`py-2.5 pr-3 text-right font-mono font-mono-num font-semibold ${
                              adj.economic_pnl >= 0
                                ? "text-[var(--hify-success)]"
                                : "text-[var(--hify-error)]"
                            }`}
                          >
                            {formatINR(adj.economic_pnl, true)}
                          </td>
                          <td className="py-2.5 pr-3 text-right font-mono font-mono-num text-[var(--hify-text-secondary)]">
                            {adj.console_fifo_pnl !== null
                              ? formatINR(adj.console_fifo_pnl, true)
                              : "—"}
                          </td>
                          <td className="py-2.5 pr-3">
                            <span className="inline-flex rounded bg-[var(--hify-gold-milestone)] px-2 py-0.5 font-mono text-[10px] font-semibold text-[var(--hify-gold-deep)] dark:bg-[var(--hify-surface-raised)] dark:text-[var(--hify-gold)]">
                              {adj.equity_handoff_status}
                            </span>
                          </td>
                          <td className="py-2.5 text-right">
                            <button
                              type="button"
                              onClick={() => handleDeleteDeliveryAdj(adj.id, adj.underlying)}
                              disabled={busyAction !== null}
                              className="inline-flex min-h-[36px] min-w-[36px] items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-error)]/10 hover:text-[var(--hify-error)]"
                              title="Remove adjustment"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === "charges" && (
            <div>
              {chargeEntries.length === 0 ? (
                <p className="py-6 text-center text-xs text-[var(--hify-text-secondary)]">
                  Import a Console P&amp;L statement to view statutory charges.
                </p>
              ) : (
                <dl className="divide-y divide-[var(--hify-border)]/60 text-xs">
                  {chargeEntries.map(([head, amount]) => (
                    <div
                      key={head}
                      className="flex items-center justify-between gap-2 py-2.5"
                    >
                      <dt className="truncate text-[var(--hify-text-secondary)]">
                        {head}
                      </dt>
                      <dd className="font-mono font-mono-num font-medium text-[var(--hify-text)]">
                        {formatINR(amount)}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Upload Console .xlsx Modal */}
      {showUploadModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="upload-xlsx-modal-title"
        >
          <form
            onSubmit={handleUploadSubmit}
            className="w-full max-w-lg space-y-4 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5 shadow-xl"
          >
            <div className="flex items-center justify-between gap-2">
              <h2
                id="upload-xlsx-modal-title"
                className="text-base font-semibold text-[var(--hify-text)]"
              >
                Upload Console .xlsx
              </h2>
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-bg)]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5 text-xs font-medium text-[var(--hify-text-secondary)]">
                Tradebook (.xlsx)
                <input
                  type="file"
                  accept=".xlsx"
                  onChange={(e) =>
                    setTradebookFile(e.target.files?.[0] ?? null)
                  }
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-xs text-[var(--hify-text)] file:mr-3 file:rounded file:border-0 file:bg-[var(--hify-gold-light)] file:px-2.5 file:py-1 file:text-xs file:font-semibold file:text-[var(--hify-gold-deep)]"
                />
              </label>

              <label className="flex flex-col gap-1.5 text-xs font-medium text-[var(--hify-text-secondary)]">
                P&amp;L Statement (.xlsx)
                <input
                  type="file"
                  accept=".xlsx"
                  onChange={(e) => setPnlFile(e.target.files?.[0] ?? null)}
                  className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-xs text-[var(--hify-text)] file:mr-3 file:rounded file:border-0 file:bg-[var(--hify-gold-light)] file:px-2.5 file:py-1 file:text-xs file:font-semibold file:text-[var(--hify-gold-deep)]"
                />
              </label>
            </div>

            <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] px-4 text-xs font-medium text-[var(--hify-text)]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busyAction !== null || (!tradebookFile && !pnlFile)}
                className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--hify-gold)] px-4 text-xs font-semibold text-[#18181B] transition-colors hover:bg-[var(--hify-gold-hover)] disabled:opacity-50"
              >
                <Upload className="h-4 w-4" />
                <span>
                  {busyAction === "upload" ? "Uploading..." : "Upload & Reconcile"}
                </span>
              </button>
            </div>
          </form>
        </div>
      )}
      {/* Add Delivery Equity Exit Modal */}
      {showDeliveryModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delivery-adj-modal-title"
        >
          <form
            onSubmit={handleCreateDeliveryAdj}
            className="max-h-[90vh] w-full max-w-xl space-y-3 overflow-y-auto rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5 shadow-xl"
          >
            <div className="flex items-center justify-between gap-2">
              <h2
                id="delivery-adj-modal-title"
                className="text-base font-semibold text-[var(--hify-text)]"
              >
                Log Physical-Delivery Equity Exit (Option A)
              </h2>
              <button
                type="button"
                onClick={() => setShowDeliveryModal(false)}
                className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-bg)]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  Underlying Ticker *
                </label>
                <input
                  type="text"
                  required
                  value={delivUnderlying}
                  onChange={(e) => setDelivUnderlying(e.target.value)}
                  placeholder="e.g. TMPV or DABUR"
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm font-mono uppercase text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  F&amp;O Contract
                </label>
                <input
                  type="text"
                  value={delivContract}
                  onChange={(e) => setDelivContract(e.target.value)}
                  placeholder="e.g. TMPV26NOV320PE"
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm font-mono uppercase text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  Delivery Strike Price (₹) *
                </label>
                <input
                  type="number"
                  step="0.05"
                  required
                  value={delivStrike}
                  onChange={(e) => setDelivStrike(e.target.value)}
                  placeholder="e.g. 320"
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm font-mono text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  Delivered Qty Sold *
                </label>
                <input
                  type="number"
                  required
                  value={delivQty}
                  onChange={(e) => setDelivQty(e.target.value)}
                  placeholder="e.g. 1600"
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm font-mono text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  Equity Sell Price (₹) *
                </label>
                <input
                  type="number"
                  step="0.05"
                  required
                  value={delivSellPrice}
                  onChange={(e) => setDelivSellPrice(e.target.value)}
                  placeholder="e.g. 258.15"
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm font-mono text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  Equity Sell Date *
                </label>
                <input
                  type="date"
                  required
                  value={delivSellDate}
                  onChange={(e) => setDelivSellDate(e.target.value)}
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm font-mono text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  Console Order ID
                </label>
                <input
                  type="text"
                  value={delivOrderId}
                  onChange={(e) => setDelivOrderId(e.target.value)}
                  placeholder="e.g. 1300000002889418"
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm font-mono text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  Delivery Charges / STT (₹)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={delivCharges}
                  onChange={(e) => setDelivCharges(e.target.value)}
                  placeholder="0"
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm font-mono text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  Console FIFO P&amp;L Ref (Optional)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={delivConsoleFifoPnl}
                  onChange={(e) => setDelivConsoleFifoPnl(e.target.value)}
                  placeholder="e.g. -109417.61"
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm font-mono text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                  Reason Tag
                </label>
                <select
                  value={delivReason}
                  onChange={(e) => setDelivReason(e.target.value)}
                  className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
                >
                  <option value="MISSED_ROLLOVER_DELIVERY">Missed Rollover → Delivery</option>
                  <option value="INSUFFICIENT_CASH_LIQUIDATION">Insufficient Cash Liquidation</option>
                  <option value="EXCEPTIONAL_EQUITY_EXIT">Exceptional Equity Exit</option>
                </select>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-[var(--hify-text-secondary)]">
                Notes / Trade IDs
              </label>
              <input
                type="text"
                value={delivNotes}
                onChange={(e) => setDelivNotes(e.target.value)}
                placeholder="e.g. Physical delivery on 2026-11-23 expiry; sold for wallet cash"
                className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 text-sm text-[var(--hify-text)] focus:border-[var(--hify-gold)] focus:outline-none"
              />
            </div>

            {delivStrike && delivQty && delivSellPrice && (
              <div className="rounded-lg border border-[var(--hify-gold)]/40 bg-[var(--hify-bg)] p-3 text-xs">
                <span className="text-[var(--hify-text-secondary)]">
                  Option A Economic P&amp;L Preview:{" "}
                </span>
                <strong className="font-mono text-[var(--hify-text)]">
                  {formatINR(
                    (Number(delivSellPrice) - Number(delivStrike)) * Number(delivQty) -
                      Number(delivCharges || 0),
                    true
                  )}
                </strong>
              </div>
            )}

            <div className="flex flex-wrap justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowDeliveryModal(false)}
                className="min-h-[44px] rounded-lg border border-[var(--hify-border)] px-4 text-xs font-medium text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={busyAction !== null}
                className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--hify-gold)] px-4 text-xs font-semibold text-[#18181B] transition-colors hover:bg-[var(--hify-gold-hover)] disabled:opacity-50"
              >
                <Plus className="h-4 w-4" />
                <span>{busyAction === "delivery" ? "Saving..." : "Save Delivery Exit"}</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

function KpiCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "error" | "warning";
}) {
  const toneClass =
    tone === "success"
      ? "text-[var(--hify-success)]"
      : tone === "error"
      ? "text-[var(--hify-error)]"
      : "text-[var(--hify-warning)]";

  return (
    <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
      <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--hify-text-secondary)]">
        {label}
      </p>
      <p className={`mt-1 font-mono font-mono-num text-lg font-semibold ${toneClass}`}>
        {value}
      </p>
    </div>
  );
}
