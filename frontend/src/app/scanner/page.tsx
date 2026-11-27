"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CheckCircle2,
  Database,
  Filter,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  SlidersHorizontal,
  WifiOff,
  X,
} from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import {
  formatNum,
  type ScannerFundamentalsRefreshResponse,
  type ScannerResponse,
  type ScannerResultItem,
} from "@/lib/types";
import { ScannerInspector } from "@/components/scanner/ScannerInspector";

interface StageFormState {
  symbol: string;
  strike: string;
  option_type: "PE" | "CE" | "FUT";
  expiry: string;
  side: "SELL" | "BUY";
  qty: string;
  limit_price: string;
  bid_price: string;
  ask_price: string;
  spread_pct: string;
  gtt_target_price: string;
  gtt_decay_pct: string;
  is_hedged: boolean;
  is_covered_call: boolean;
  override_reason: string;
}

function formatISTTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    return `${dt.toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })} IST`;
  } catch {
    return iso;
  }
}

export default function ScannerPage() {
  const [data, setData] = useState<ScannerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [hydrating, setHydrating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hydrateNotice, setHydrateNotice] = useState<string | null>(null);

  // Tier 1 & Slicers (defaulting to All Stocks)
  const [includeRejected, setIncludeRejected] = useState(true);
  const [universeType, setUniverseType] = useState<string>("");
  const [capTier, setCapTier] = useState<string>("");
  const [ppmTier, setPpmTier] = useState<string>("");
  const [refreshLiveQuotes, setRefreshLiveQuotes] = useState(false);

  // Compact Technical Filter Bar
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [minAthDropPct, setMinAthDropPct] = useState<string>("");
  const [min52wDropPct, setMin52wDropPct] = useState<string>("");
  const [minDma200DropPct, setMinDma200DropPct] = useState<string>("");
  const [redCandleOnly, setRedCandleOnly] = useState(false);
  const [maxSpreadPct, setMaxSpreadPct] = useState<string>("");

  // Master-Detail Selection
  const [inspectedSymbol, setInspectedSymbol] = useState<string | null>(null);
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false);

  type SortKey =
    | "symbol"
    | "current_price"
    | "ath_drop_pct"
    | "high_52w_drop_pct"
    | "dma200_pct"
    | "ppm_pct"
    | "bid_ask_spread_pct"
    | "theta_opportunity_score";
  const [sortKey, setSortKey] = useState<SortKey>("theta_opportunity_score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  // Stage Limit Put Modal
  const [selectedCandidate, setSelectedCandidate] =
    useState<ScannerResultItem | null>(null);
  const [stageForm, setStageForm] = useState<StageFormState | null>(null);
  const [staging, setStaging] = useState(false);
  const [stageError, setStageError] = useState<string | null>(null);
  const [stageSuccess, setStageSuccess] = useState<string | null>(null);

  const activeTechFilterCount = useMemo(() => {
    let count = 0;
    if (minAthDropPct.trim() !== "") count += 1;
    if (min52wDropPct.trim() !== "") count += 1;
    if (minDma200DropPct.trim() !== "") count += 1;
    if (redCandleOnly) count += 1;
    if (maxSpreadPct.trim() !== "") count += 1;
    if (ppmTier !== "") count += 1;
    return count;
  }, [
    minAthDropPct,
    min52wDropPct,
    minDma200DropPct,
    redCandleOnly,
    maxSpreadPct,
    ppmTier,
  ]);

  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("include_rejected", String(includeRejected));
      if (universeType) params.set("universe_type", universeType);
      if (capTier) params.set("cap_tier", capTier);
      if (ppmTier) params.set("ppm_tier", ppmTier);
      if (minAthDropPct.trim() !== "")
        params.set("min_ath_drop_pct", minAthDropPct.trim());
      if (min52wDropPct.trim() !== "")
        params.set("min_52w_drop_pct", min52wDropPct.trim());
      if (minDma200DropPct.trim() !== "")
        params.set("min_dma200_drop_pct", minDma200DropPct.trim());
      if (redCandleOnly) params.set("red_candle_only", "true");
      if (maxSpreadPct.trim() !== "")
        params.set("max_spread_pct", maxSpreadPct.trim());
      if (refreshLiveQuotes) params.set("refresh_live_quotes", "true");

      const res = await apiFetch<ScannerResponse>(
        `/api/scanner/candidates?${params.toString()}`
      );
      setData(res);
      setInspectedSymbol((prev) => {
        if (res.items.length === 0) return null;
        if (prev && res.items.some((i) => i.symbol === prev)) return prev;
        return res.items[0].symbol;
      });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to load Dhool Chaat scanner candidates."
      );
    } finally {
      setLoading(false);
    }
  }, [
    includeRejected,
    universeType,
    capTier,
    ppmTier,
    minAthDropPct,
    min52wDropPct,
    minDma200DropPct,
    redCandleOnly,
    maxSpreadPct,
    refreshLiveQuotes,
  ]);

  useEffect(() => {
    void fetchCandidates();
  }, [fetchCandidates]);

  async function handleHydrateNow() {
    setHydrating(true);
    setError(null);
    setHydrateNotice(null);
    try {
      const res = await apiFetch<{
        hydrated_count?: number;
        total_symbols?: number;
      }>("/api/scanner/hydrate", {
        method: "POST",
        body: JSON.stringify({
          include_indices: true,
          fetch_fundamentals: false,
        }),
      });
      const count = res.hydrated_count ?? res.total_symbols ?? 0;
      setHydrateNotice(
        `Hydrated ${count} symbols into local technicals cache.`
      );
      await fetchCandidates();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Failed to hydrate scanner cache."
      );
    } finally {
      setHydrating(false);
    }
  }

  function handleResetFilters() {
    setUniverseType("");
    setCapTier("");
    setPpmTier("");
    setMinAthDropPct("");
    setMin52wDropPct("");
    setMinDma200DropPct("");
    setRedCandleOnly(false);
    setMaxSpreadPct("");
    setIncludeRejected(true);
  }

  function handleFundamentalsUpdated(
    symbol: string,
    res: ScannerFundamentalsRefreshResponse
  ) {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((item) =>
          item.symbol === symbol
            ? {
                ...item,
                fundamentals: res.fundamentals,
                fundamental_checks: res.fundamental_checks,
                fundamental_passed: res.fundamental_passed,
              }
            : item
        ),
      };
    });
  }

  function openStageModal(item: ScannerResultItem) {
    const limitPrice = item.option_bid > 0 ? item.option_bid : item.premium;
    const gttTarget = Number((limitPrice * 0.5).toFixed(2));
    setSelectedCandidate(item);
    setStageError(null);
    setStageSuccess(null);
    setStageForm({
      symbol: item.symbol,
      strike: String(item.option_strike ?? Math.round(item.current_price)),
      option_type: "PE",
      expiry: "25MAY",
      side: "SELL",
      qty: String(item.lot_size),
      limit_price: String(limitPrice),
      bid_price: String(item.option_bid),
      ask_price: String(item.option_ask),
      spread_pct: String(item.bid_ask_spread_pct),
      gtt_target_price: String(gttTarget),
      gtt_decay_pct: "50",
      is_hedged: item.requires_hedge,
      is_covered_call: false,
      override_reason: "",
    });
  }

  async function handleStageSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!stageForm) return;
    setStaging(true);
    setStageError(null);
    setStageSuccess(null);

    try {
      const payload = {
        symbol: stageForm.symbol.trim().toUpperCase(),
        strike: Number(stageForm.strike),
        option_type: stageForm.option_type,
        expiry: stageForm.expiry.trim().toUpperCase(),
        side: stageForm.side,
        qty: Number(stageForm.qty),
        order_type: "LIMIT",
        limit_price: Number(stageForm.limit_price),
        bid_price: stageForm.bid_price ? Number(stageForm.bid_price) : null,
        ask_price: stageForm.ask_price ? Number(stageForm.ask_price) : null,
        spread_pct: stageForm.spread_pct ? Number(stageForm.spread_pct) : null,
        gtt_target_price: stageForm.gtt_target_price
          ? Number(stageForm.gtt_target_price)
          : null,
        gtt_decay_pct: stageForm.gtt_decay_pct
          ? Number(stageForm.gtt_decay_pct)
          : null,
        is_hedged: stageForm.is_hedged,
        is_covered_call: stageForm.is_covered_call,
        override_reason: stageForm.override_reason.trim(),
      };

      const res = await apiFetch<{ status: string; order: { id: number } }>(
        "/api/orders/stage",
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
      setStageSuccess(
        `Staged Limit order #${res.order.id} for ${payload.symbol}. Approve manually in Cockpit or Positions.`
      );
    } catch (err) {
      setStageError(
        err instanceof ApiError ? err.message : "Guardrail rejected staged order."
      );
    } finally {
      setStaging(false);
    }
  }

  const items = data?.items ?? [];
  const sortedItems = useMemo(() => {
    const copy = [...items];
    copy.sort((a, b) => {
      if (sortKey === "symbol") {
        return sortDir === "asc"
          ? a.symbol.localeCompare(b.symbol)
          : b.symbol.localeCompare(a.symbol);
      }
      const va = Number(a[sortKey] ?? 0);
      const vb = Number(b[sortKey] ?? 0);
      return sortDir === "asc" ? va - vb : vb - va;
    });
    return copy;
  }, [items, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir(key === "symbol" || key === "bid_ask_spread_pct" ? "asc" : "desc");
    }
  }

  function renderSortIcon(key: SortKey) {
    if (sortKey !== key) {
      return <ArrowUpDown className="h-3 w-3 opacity-45" />;
    }
    return sortDir === "asc" ? (
      <ArrowUp className="h-3 w-3 text-[#8E6C20] dark:text-[#C8A951]" />
    ) : (
      <ArrowDown className="h-3 w-3 text-[#8E6C20] dark:text-[#C8A951]" />
    );
  }

  const inspectedCandidate = useMemo(
    () => sortedItems.find((i) => i.symbol === inspectedSymbol) ?? sortedItems[0] ?? null,
    [sortedItems, inspectedSymbol]
  );

  const freshness = (data?.freshness ?? "cached").toLowerCase();
  const freshnessLabel =
    freshness === "live"
      ? "Live"
      : freshness === "dry_run"
      ? "Dry-Run"
      : freshness === "offline"
      ? "Offline"
      : "Cached";
  const freshnessClass =
    freshness === "live"
      ? "border-[#10B981] text-[#10B981]"
      : freshness === "offline"
      ? "border-[#F43F5E] text-[#F43F5E]"
      : "border-[#EA580C] text-[#EA580C]";

  const canOpenNew = data?.aukaat_summary?.can_open_new ?? false;

  return (
    <section className="space-y-4">
      {/* Tier 1: Slim Header + Slicers + Technical Filter Bar */}
      <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-lg font-semibold tracking-tight text-[var(--hify-text)]">
              Dhool Chaat Scanner
            </h1>

            {data?.aukaat_summary && (
              <span
                className={`font-mono font-mono-num rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                  data.aukaat_summary.can_open_new
                    ? "border-[#10B981] text-[#10B981]"
                    : "border-[#F43F5E] text-[#F43F5E]"
                }`}
              >
                {data.aukaat_summary.naked_free} /{" "}
                {data.aukaat_summary.naked_max} Naked Slots Open
              </span>
            )}

            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${freshnessClass}`}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
              {freshnessLabel}
              {data?.synced_at && (
                <span className="font-mono font-mono-num text-[10px] opacity-85">
                  · {formatISTTimestamp(data.synced_at)}
                </span>
              )}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* All Stocks / Passed Only Toggle */}
            <div className="flex items-center rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-0.5">
              <button
                type="button"
                onClick={() => setIncludeRejected(true)}
                className={`min-h-[44px] rounded-md px-3 text-xs font-semibold transition-colors ${
                  includeRejected
                    ? "bg-[var(--hify-gold)] text-[#18181B]"
                    : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
                }`}
              >
                All Stocks ({data?.total_evaluated ?? 0})
              </button>
              <button
                type="button"
                onClick={() => setIncludeRejected(false)}
                className={`min-h-[44px] rounded-md px-3 text-xs font-semibold transition-colors ${
                  !includeRejected
                    ? "bg-[var(--hify-gold)] text-[#18181B]"
                    : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
                }`}
              >
                Passed Only ({data?.passed_count ?? 0})
              </button>
            </div>

            <button
              type="button"
              onClick={() => setRefreshLiveQuotes((p) => !p)}
              className={`min-h-[44px] rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${
                refreshLiveQuotes
                  ? "border-[#C8A951] text-[#8E6C20] dark:text-[#C8A951]"
                  : "border-[var(--hify-border)] text-[var(--hify-text-secondary)]"
              }`}
            >
              Live Quotes: {refreshLiveQuotes ? "ON" : "OFF"}
            </button>

            <button
              type="button"
              onClick={() => void handleHydrateNow()}
              disabled={hydrating || loading}
              className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3 py-2 text-xs font-semibold text-[var(--hify-text)] transition-colors hover:bg-[var(--hify-surface-raised)] disabled:opacity-50"
            >
              <Database
                className={`h-3.5 w-3.5 ${hydrating ? "animate-pulse" : ""}`}
              />
              <span>{hydrating ? "Hydrating..." : "Hydrate Now"}</span>
            </button>

            <button
              type="button"
              onClick={() => void fetchCandidates()}
              disabled={loading}
              className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg bg-[#C8A951] px-4 py-2 text-xs font-semibold text-[#18181B] transition-colors hover:bg-[#B6933A] disabled:opacity-50"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
              />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Slicer Row: Universe + Cap + Mobile Filter Toggle */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--hify-border)] pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap items-center gap-1 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-1">
              {[
                { val: "", label: "All Lists" },
                { val: "NSE_FNO", label: "All F&O" },
                { val: "F40", label: "F40" },
                { val: "E40", label: "E40" },
                { val: "INDICES", label: "Indices" },
              ].map((opt) => (
                <button
                  key={opt.val || "all"}
                  type="button"
                  onClick={() => setUniverseType(opt.val)}
                  className={`min-h-[44px] rounded-md px-3 text-xs font-semibold transition-colors ${
                    universeType === opt.val
                      ? "bg-[#C8A951] text-[#18181B]"
                      : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] p-1">
              {[
                { val: "", label: "All" },
                { val: "large", label: "Large" },
                { val: "mid", label: "Mid" },
                { val: "small", label: "Small" },
              ].map((opt) => (
                <button
                  key={opt.val || "allcaps"}
                  type="button"
                  onClick={() => setCapTier(opt.val)}
                  className={`min-h-[44px] rounded-md px-3 text-xs font-semibold transition-colors ${
                    capTier === opt.val
                      ? "bg-[#C8A951] text-[#18181B]"
                      : "text-[var(--hify-text-secondary)] hover:text-[var(--hify-text)]"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            onClick={() => setFiltersOpen((prev) => !prev)}
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-xs font-semibold text-[var(--hify-text)] md:hidden"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            <span>Filters ({activeTechFilterCount})</span>
          </button>
        </div>

        {/* Compact Technical Filter Bar */}
        <div
          className={`mt-3 grid grid-cols-2 gap-2 border-t border-[var(--hify-border)] pt-3 sm:grid-cols-3 lg:grid-cols-7 ${
            filtersOpen ? "grid" : "hidden md:grid"
          }`}
        >
          <div>
            <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
              Min ATH Drop %
            </label>
            <input
              type="number"
              min="0"
              step="1"
              placeholder="e.g. 15"
              value={minAthDropPct}
              onChange={(e) => setMinAthDropPct(e.target.value)}
              className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-2.5 text-xs text-[var(--hify-text)]"
            />
          </div>

          <div>
            <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
              Min 52W Drop %
            </label>
            <input
              type="number"
              min="0"
              step="1"
              placeholder="e.g. 10"
              value={min52wDropPct}
              onChange={(e) => setMin52wDropPct(e.target.value)}
              className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-2.5 text-xs text-[var(--hify-text)]"
            />
          </div>

          <div>
            <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
              Min 200DMA Drop %
            </label>
            <input
              type="number"
              min="0"
              step="1"
              placeholder="e.g. 5"
              value={minDma200DropPct}
              onChange={(e) => setMinDma200DropPct(e.target.value)}
              className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-2.5 text-xs text-[var(--hify-text)]"
            />
          </div>

          <div>
            <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
              Max Spread %
            </label>
            <div className="mt-1 flex items-center gap-1">
              <input
                type="number"
                min="0"
                step="0.5"
                placeholder="5.0"
                value={maxSpreadPct}
                onChange={(e) => setMaxSpreadPct(e.target.value)}
                className="font-mono font-mono-num min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-2.5 text-xs text-[var(--hify-text)]"
              />
              <button
                type="button"
                onClick={() =>
                  setMaxSpreadPct((prev) => (prev === "5" ? "" : "5"))
                }
                className={`min-h-[44px] shrink-0 rounded-lg border px-2.5 text-[10px] font-semibold ${
                  maxSpreadPct === "5"
                    ? "border-[#C8A951] bg-[#C8A951]/15 text-[#8E6C20] dark:text-[#C8A951]"
                    : "border-[var(--hify-border)] text-[var(--hify-text-secondary)]"
                }`}
              >
                ≤5%
              </button>
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
              PPM Tier
            </label>
            <div className="relative mt-1 flex items-center">
              <Filter className="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-[var(--hify-text-secondary)]" />
              <select
                value={ppmTier}
                onChange={(e) => setPpmTier(e.target.value)}
                aria-label="Filter by PPM Tier"
                className="min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] pl-8 pr-2 text-xs text-[var(--hify-text)]"
              >
                <option value="">All PPM</option>
                <option value="Aggressive">Aggressive (&gt;6%)</option>
                <option value="Normal">Normal (3–6%)</option>
                <option value="Conservative">Conservative (&lt;3%)</option>
              </select>
            </div>
          </div>

          <div className="flex items-end">
            <button
              type="button"
              onClick={() => setRedCandleOnly((prev) => !prev)}
              className={`min-h-[44px] w-full rounded-lg border px-3 text-xs font-semibold transition-colors ${
                redCandleOnly
                  ? "border-[#F43F5E] bg-[#F43F5E]/10 text-[#F43F5E]"
                  : "border-[var(--hify-border)] bg-[var(--hify-bg)] text-[var(--hify-text-secondary)]"
              }`}
            >
              Red Candle Only
            </button>
          </div>

          <div className="flex items-end">
            <button
              type="button"
              onClick={handleResetFilters}
              className="inline-flex min-h-[44px] w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3 text-xs font-medium text-[var(--hify-text)] hover:bg-[var(--hify-surface-raised)]"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>Reset</span>
            </button>
          </div>
        </div>
      </div>

      {/* Offline / Cached Status Strip */}
      {data && freshness !== "live" && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] px-4 py-2.5 text-xs text-[var(--hify-text-secondary)]">
          <div className="flex items-center gap-2">
            <WifiOff className="h-4 w-4 shrink-0 text-[#EA580C]" />
            <span>
              {freshness === "offline"
                ? "Offline mode: showing local cached/sample scanner snapshot."
                : freshness === "dry_run"
                ? "Dry-Run mode: synthetic Kite quotes active (connect Kite for live prices)."
                : "Cached technicals snapshot active."}
              {data.synced_at
                ? ` Last synced ${formatISTTimestamp(data.synced_at)}.`
                : ""}
            </span>
          </div>
          <button
            type="button"
            onClick={() => void handleHydrateNow()}
            disabled={hydrating}
            className="min-h-[44px] shrink-0 rounded-lg border border-[var(--hify-border)] px-3 text-xs font-semibold text-[#8E6C20] hover:border-[#C8A951] dark:text-[#C8A951]"
          >
            {hydrating ? "Hydrating..." : "Hydrate"}
          </button>
        </div>
      )}

      {hydrateNotice && (
        <div className="flex items-center justify-between rounded-xl border border-[#10B981] bg-[var(--hify-surface)] px-4 py-2.5 text-xs text-[#10B981]">
          <span>{hydrateNotice}</span>
          <button
            type="button"
            onClick={() => setHydrateNotice(null)}
            className="min-h-[44px] px-2 text-xs font-semibold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Error Banner with Retry */}
      {error && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--hify-error)] bg-[var(--hify-surface)] p-3 text-sm text-[var(--hify-error)]">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void fetchCandidates()}
            className="min-h-[44px] rounded-lg border border-[var(--hify-error)] px-3 text-xs font-semibold hover:bg-[#F43F5E]/10"
          >
            Retry
          </button>
        </div>
      )}

      {/* Tier 2: Master-Detail Split */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
        {/* Left Pane: Master Table (md+) & Mobile Cards (< md) */}
        <div className="min-w-0">
          {loading && items.length === 0 ? (
            <div className="space-y-2 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
              {Array.from({ length: 6 }).map((_, idx) => (
                <div
                  key={idx}
                  className="h-12 animate-pulse rounded-lg bg-[var(--hify-bg)]"
                />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-8 text-center">
              <p className="text-sm text-[var(--hify-text-secondary)]">
                No scanner candidates match the current filters.
              </p>
              <button
                type="button"
                onClick={handleResetFilters}
                className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-[#C8A951] px-4 py-2 text-xs font-semibold text-[#18181B] hover:bg-[#B6933A]"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span>Reset Filters</span>
              </button>
            </div>
          ) : (
            <>
              {/* Desktop / Tablet Master Table (md+) */}
              <div className="hidden overflow-x-auto rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] md:block">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                      <th className="px-4 py-3 font-medium">
                        <button
                          type="button"
                          onClick={() => toggleSort("symbol")}
                          className="inline-flex items-center gap-1 hover:text-[var(--hify-text)]"
                        >
                          <span>Symbol / Cap</span>
                          {renderSortIcon("symbol")}
                        </button>
                      </th>
                      <th className="px-3 py-3 text-right font-medium">
                        <button
                          type="button"
                          onClick={() => toggleSort("current_price")}
                          className="inline-flex items-center justify-end gap-1 hover:text-[var(--hify-text)]"
                        >
                          <span>CMP &amp; Intraday%</span>
                          {renderSortIcon("current_price")}
                        </button>
                      </th>
                      <th className="px-3 py-3 text-right font-medium">
                        <button
                          type="button"
                          onClick={() => toggleSort("ath_drop_pct")}
                          className="inline-flex items-center justify-end gap-1 hover:text-[var(--hify-text)]"
                        >
                          <span>ATH%</span>
                          {renderSortIcon("ath_drop_pct")}
                        </button>
                      </th>
                      <th className="px-3 py-3 text-right font-medium">
                        <button
                          type="button"
                          onClick={() => toggleSort("high_52w_drop_pct")}
                          className="inline-flex items-center justify-end gap-1 hover:text-[var(--hify-text)]"
                        >
                          <span>52W%</span>
                          {renderSortIcon("high_52w_drop_pct")}
                        </button>
                      </th>
                      <th className="px-3 py-3 text-right font-medium">
                        <button
                          type="button"
                          onClick={() => toggleSort("dma200_pct")}
                          className="inline-flex items-center justify-end gap-1 hover:text-[var(--hify-text)]"
                        >
                          <span>200DMA%</span>
                          {renderSortIcon("dma200_pct")}
                        </button>
                      </th>
                      <th className="px-3 py-3 text-right font-medium">
                        <button
                          type="button"
                          onClick={() => toggleSort("ppm_pct")}
                          className="inline-flex items-center justify-end gap-1 hover:text-[var(--hify-text)]"
                        >
                          <span>Strike / PPM%</span>
                          {renderSortIcon("ppm_pct")}
                        </button>
                      </th>
                      <th className="px-3 py-3 text-right font-medium">
                        <button
                          type="button"
                          onClick={() => toggleSort("bid_ask_spread_pct")}
                          className="inline-flex items-center justify-end gap-1 hover:text-[var(--hify-text)]"
                        >
                          <span>Spread%</span>
                          {renderSortIcon("bid_ask_spread_pct")}
                        </button>
                      </th>
                      <th className="px-4 py-3 text-right font-medium">
                        <button
                          type="button"
                          onClick={() => toggleSort("theta_opportunity_score")}
                          className="inline-flex items-center justify-end gap-1 hover:text-[var(--hify-text)]"
                        >
                          <span>Theta Score</span>
                          {renderSortIcon("theta_opportunity_score")}
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--hify-border)]">
                    {sortedItems.map((item) => {
                      const isSelected =
                        inspectedCandidate?.symbol === item.symbol;
                      return (
                        <tr
                          key={item.symbol}
                          onClick={() => {
                            setInspectedSymbol(item.symbol);
                            setMobileInspectorOpen(true);
                          }}
                          className={`cursor-pointer transition-colors ${
                            isSelected
                              ? "bg-[#C8A951]/10"
                              : "hover:bg-[var(--hify-bg)]"
                          }`}
                        >
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-1.5 font-semibold text-[var(--hify-text)]">
                              <span
                                className={`h-2 w-2 shrink-0 rounded-full ${
                                  item.passed ? "bg-[#10B981]" : "bg-[#F43F5E]"
                                }`}
                                title={item.passed ? "PASS" : "FAIL"}
                              />
                              <span>{item.symbol}</span>
                              <span className="rounded bg-[var(--hify-bg)] px-1.5 py-0.5 text-[10px] font-medium uppercase text-[var(--hify-text-secondary)]">
                                {item.cap_tier}
                              </span>
                            </div>
                          </td>

                          <td className="font-mono font-mono-num px-3 py-3 text-right">
                            <div className="text-[var(--hify-text)]">
                              ₹{formatNum(item.current_price)}
                            </div>
                            <div
                              className={`text-[10px] ${
                                item.is_red_candle
                                  ? "text-[#F43F5E]"
                                  : "text-[#10B981]"
                              }`}
                            >
                              {item.is_red_candle ? "-" : "+"}
                              {formatNum(Math.abs(item.intraday_drop_pct), 2)}%
                            </div>
                          </td>

                          <td className="font-mono font-mono-num px-3 py-3 text-right text-[#F43F5E]">
                            -{formatNum(item.ath_drop_pct, 1)}%
                          </td>

                          <td className="font-mono font-mono-num px-3 py-3 text-right text-[var(--hify-text-secondary)]">
                            {item.high_52w_drop_pct !== undefined
                              ? `-${formatNum(item.high_52w_drop_pct, 1)}%`
                              : "—"}
                          </td>

                          <td className="font-mono font-mono-num px-3 py-3 text-right text-[var(--hify-text-secondary)]">
                            {item.dma200_pct !== undefined
                              ? `${item.dma200_pct >= 0 ? "+" : ""}${formatNum(
                                  item.dma200_pct,
                                  1
                                )}%`
                              : "—"}
                          </td>

                          <td className="font-mono font-mono-num px-3 py-3 text-right">
                            <div className="text-[var(--hify-text)]">
                              {item.option_strike ?? "—"} PE
                            </div>
                            <div className="text-[10px] font-semibold text-[#8E6C20] dark:text-[#C8A951]">
                              {formatNum(item.ppm_pct, 2)}%
                            </div>
                          </td>

                          <td className="font-mono font-mono-num px-3 py-3 text-right text-[var(--hify-text)]">
                            {formatNum(item.bid_ask_spread_pct, 2)}%
                          </td>

                          <td className="font-mono font-mono-num px-4 py-3 text-right font-semibold text-[var(--hify-text)]">
                            {formatNum(item.theta_opportunity_score ?? 0, 1)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Mobile Compact 2-Line Cards (< md) */}
              <div className="space-y-2 md:hidden">
                <div className="flex items-center justify-between gap-2">
                  <label className="text-[11px] font-medium text-[var(--hify-text-secondary)]">
                    Sort by
                  </label>
                  <div className="flex items-center gap-1.5">
                    <select
                      value={sortKey}
                      onChange={(e) => setSortKey(e.target.value as SortKey)}
                      className="min-h-[44px] rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-2.5 text-xs text-[var(--hify-text)]"
                    >
                      <option value="theta_opportunity_score">Theta Score</option>
                      <option value="ath_drop_pct">ATH Drop %</option>
                      <option value="high_52w_drop_pct">52W Drop %</option>
                      <option value="dma200_pct">200DMA %</option>
                      <option value="ppm_pct">PPM %</option>
                      <option value="bid_ask_spread_pct">Spread %</option>
                      <option value="current_price">CMP</option>
                      <option value="symbol">Symbol (A-Z)</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
                      className="min-h-[44px] min-w-[44px] inline-flex items-center justify-center rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] text-xs text-[var(--hify-text)]"
                      aria-label="Toggle sort direction"
                    >
                      {sortDir === "asc" ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
                    </button>
                  </div>
                </div>
                {sortedItems.map((item) => {
                  const isSelected =
                    inspectedCandidate?.symbol === item.symbol;
                  return (
                    <button
                      key={item.symbol}
                      type="button"
                      onClick={() => {
                        setInspectedSymbol(item.symbol);
                        setMobileInspectorOpen(true);
                      }}
                      className={`flex min-h-[60px] w-full flex-col justify-between gap-1.5 rounded-xl border p-3 text-left transition-colors ${
                        isSelected
                          ? "border-[#C8A951] bg-[#C8A951]/10"
                          : "border-[var(--hify-border)] bg-[var(--hify-surface)]"
                      }`}
                    >
                      <div className="flex w-full items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span
                            className={`h-2 w-2 rounded-full ${
                              item.passed ? "bg-[#10B981]" : "bg-[#F43F5E]"
                            }`}
                          />
                          <span className="text-sm font-semibold text-[var(--hify-text)]">
                            {item.symbol}
                          </span>
                          <span className="rounded bg-[var(--hify-bg)] px-1.5 py-0.5 text-[10px] uppercase text-[var(--hify-text-secondary)]">
                            {item.cap_tier}
                          </span>
                        </div>
                        <span className="font-mono font-mono-num text-xs font-semibold text-[var(--hify-text)]">
                          ₹{formatNum(item.current_price)}{" "}
                          <span className="text-[#F43F5E]">
                            (-{formatNum(item.ath_drop_pct, 1)}%)
                          </span>
                        </span>
                      </div>

                      <div className="font-mono font-mono-num flex w-full items-center justify-between text-[11px] text-[var(--hify-text-secondary)]">
                        <span>
                          {item.option_strike ?? "—"} PE ·{" "}
                          <span className="font-semibold text-[#8E6C20] dark:text-[#C8A951]">
                            {formatNum(item.ppm_pct, 2)}% PPM
                          </span>
                        </span>
                        <span>
                          Spr {formatNum(item.bid_ask_spread_pct, 2)}% · Score{" "}
                          <strong className="text-[var(--hify-text)]">
                            {formatNum(item.theta_opportunity_score ?? 0, 1)}
                          </strong>
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* Right Pane: Persistent Inspector (lg+) / Slide-Over Drawer (< lg) */}
        <ScannerInspector
          candidate={inspectedCandidate}
          canOpenNew={canOpenNew}
          mobileOpen={mobileInspectorOpen}
          onCloseMobile={() => setMobileInspectorOpen(false)}
          onStageOrder={openStageModal}
          onFundamentalsUpdated={handleFundamentalsUpdated}
        />
      </div>

      {/* Stage Limit ATO/GTT Modal (Preserved) */}
      {selectedCandidate && stageForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="stage-modal-title"
        >
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-5 shadow-xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2
                  id="stage-modal-title"
                  className="text-base font-semibold text-[var(--hify-text)]"
                >
                  Stage Limit ATO / GTT — {selectedCandidate.symbol}
                </h2>
                <p className="mt-0.5 text-xs text-[var(--hify-text-secondary)]">
                  Order type is locked to LIMIT. Never auto-fired.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedCandidate(null)}
                className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-[var(--hify-text-secondary)] hover:bg-[var(--hify-surface-raised)]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {stageError && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-[var(--hify-error)] bg-[var(--hify-surface-raised)] p-3 text-xs text-[var(--hify-error)]">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{stageError}</span>
              </div>
            )}

            {stageSuccess && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-[var(--hify-success)] bg-[var(--hify-surface-raised)] p-3 text-xs text-[var(--hify-success)]">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{stageSuccess}</span>
              </div>
            )}

            <form onSubmit={handleStageSubmit} className="mt-4 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Order Type (Locked)
                  </label>
                  <input
                    type="text"
                    value="LIMIT"
                    readOnly
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm font-semibold text-[#8E6C20] dark:text-[#C8A951]"
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Option Type
                  </label>
                  <select
                    value={stageForm.option_type}
                    onChange={(e) =>
                      setStageForm({
                        ...stageForm,
                        option_type: e.target.value as "PE" | "CE" | "FUT",
                      })
                    }
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                  >
                    <option value="PE">PE (Put)</option>
                    <option value="CE">CE (Covered Call only)</option>
                    <option value="FUT">FUT (Far-Month)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Strike
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    value={stageForm.strike}
                    onChange={(e) =>
                      setStageForm({ ...stageForm, strike: e.target.value })
                    }
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                    required
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Expiry
                  </label>
                  <input
                    type="text"
                    value={stageForm.expiry}
                    onChange={(e) =>
                      setStageForm({ ...stageForm, expiry: e.target.value })
                    }
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                    required
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    Qty (Lot Size)
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={stageForm.qty}
                    onChange={(e) =>
                      setStageForm({ ...stageForm, qty: e.target.value })
                    }
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
                    value={stageForm.limit_price}
                    onChange={(e) =>
                      setStageForm({
                        ...stageForm,
                        limit_price: e.target.value,
                      })
                    }
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
                    value={stageForm.spread_pct}
                    onChange={(e) =>
                      setStageForm({ ...stageForm, spread_pct: e.target.value })
                    }
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                  />
                </div>

                <div>
                  <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                    GTT Target Price (₹)
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    value={stageForm.gtt_target_price}
                    onChange={(e) =>
                      setStageForm({
                        ...stageForm,
                        gtt_target_price: e.target.value,
                      })
                    }
                    className="font-mono font-mono-num mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)]"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[10px] font-semibold uppercase text-[var(--hify-text-secondary)]">
                  Override Reason (Optional)
                </label>
                <input
                  type="text"
                  placeholder="Required only if overriding a guardrail warning"
                  value={stageForm.override_reason}
                  onChange={(e) =>
                    setStageForm({
                      ...stageForm,
                      override_reason: e.target.value,
                    })
                  }
                  className="mt-1 min-h-[44px] w-full rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-xs text-[var(--hify-text)]"
                />
              </div>

              <div className="flex flex-wrap gap-4 pt-1">
                <label className="flex min-h-[44px] cursor-pointer items-center gap-2 text-xs text-[var(--hify-text)]">
                  <input
                    type="checkbox"
                    checked={stageForm.is_hedged}
                    onChange={(e) =>
                      setStageForm({
                        ...stageForm,
                        is_hedged: e.target.checked,
                      })
                    }
                    className="h-4 w-4 accent-[var(--hify-gold)]"
                  />
                  <span>Hedged Position (6-position tier)</span>
                </label>

                {stageForm.option_type === "CE" && (
                  <label className="flex min-h-[44px] cursor-pointer items-center gap-2 text-xs text-[var(--hify-text)]">
                    <input
                      type="checkbox"
                      checked={stageForm.is_covered_call}
                      onChange={(e) =>
                        setStageForm({
                          ...stageForm,
                          is_covered_call: e.target.checked,
                        })
                      }
                      className="h-4 w-4 accent-[var(--hify-gold)]"
                    />
                    <span>Covered Call (paired with long stock/Future)</span>
                  </label>
                )}
              </div>

              <div className="flex flex-col-reverse gap-2 pt-3 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={() => setSelectedCandidate(null)}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-4 py-2 text-sm font-medium text-[var(--hify-text)] hover:bg-[var(--hify-surface-raised)]"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={staging}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-[#C8A951] px-5 py-2 text-sm font-semibold text-[#18181B] transition-colors hover:bg-[#B6933A] disabled:opacity-50"
                >
                  {staging ? "Staging..." : "Stage Limit Order"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}
