"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  KeyRound,
  RefreshCw,
} from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import {
  formatINR,
  formatNum,
  type KiteLoginUrlResponse,
  type KiteMargins,
  type KiteOrdersResponse,
  type KitePnl,
  type KiteStatus,
  type KiteTradesResponse,
  type StagedOrdersResponse,
} from "@/lib/types";
import { KillSwitchButton } from "@/components/KillSwitchModal";
import { SortableTh, useTableSort } from "@/components/SortableTh";
import { StagedOrdersList } from "@/components/StagedOrdersList";

export default function CockpitDashboardPage() {
  const [status, setStatus] = useState<KiteStatus | null>(null);
  const [pnl, setPnl] = useState<KitePnl | null>(null);
  const [margins, setMargins] = useState<KiteMargins | null>(null);
  const [ordersData, setOrdersData] = useState<KiteOrdersResponse | null>(null);
  const [tradesData, setTradesData] = useState<KiteTradesResponse | null>(null);
  const [stagedData, setStagedData] = useState<StagedOrdersResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [authNotice, setAuthNotice] = useState<string | null>(null);

  const [showTokenBox, setShowTokenBox] = useState(false);
  const [requestToken, setRequestToken] = useState("");
  const [exchangingToken, setExchangingToken] = useState(false);

  const [tradesTab, setTradesTab] = useState<"active" | "closed">("active");

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, pnlRes, marginsRes, ordersRes, tradesRes, stagedRes] =
        await Promise.all([
          apiFetch<KiteStatus>("/api/kite/status"),
          apiFetch<KitePnl>("/api/kite/pnl"),
          apiFetch<KiteMargins>("/api/kite/margins"),
          apiFetch<KiteOrdersResponse>("/api/kite/orders"),
          apiFetch<KiteTradesResponse>("/api/kite/trades"),
          apiFetch<StagedOrdersResponse>("/api/orders/staged"),
        ]);
      setStatus(statusRes);
      setPnl(pnlRes);
      setMargins(marginsRes);
      setOrdersData(ordersRes);
      setTradesData(tradesRes);
      setStagedData(stagedRes);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Unable to reach FastAPI backend. Ensure backend is running on :8000."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  async function handleKiteLogin() {
    setAuthNotice(null);
    try {
      const res = await apiFetch<KiteLoginUrlResponse>("/api/kite/login-url");
      if (res.login_url) {
        window.open(res.login_url, "_blank", "noopener,noreferrer");
        setShowTokenBox(true);
        setAuthNotice("Zerodha OAuth opened. Paste the returned request_token below.");
      } else {
        setAuthNotice(res.message);
      }
    } catch (err) {
      setAuthNotice(err instanceof ApiError ? err.message : "Failed to fetch Kite login URL.");
    }
  }

  async function handleExchangeToken(e: React.FormEvent) {
    e.preventDefault();
    if (!requestToken.trim()) return;
    setExchangingToken(true);
    setAuthNotice(null);
    try {
      await apiFetch<KiteStatus>("/api/kite/session", {
        method: "POST",
        body: JSON.stringify({ request_token: requestToken.trim() }),
      });
      setRequestToken("");
      setShowTokenBox(false);
      setAuthNotice("Kite session connected successfully.");
      await loadDashboard();
    } catch (err) {
      setAuthNotice(err instanceof ApiError ? err.message : "Failed to exchange request_token.");
    } finally {
      setExchangingToken(false);
    }
  }

  const activeTrades = tradesData?.active_trades ?? [];
  const closedTrades = tradesData?.closed_trades ?? [];
  const openOrders = ordersData?.open_orders ?? [];
  const gtts = ordersData?.gtts ?? [];
  const stagedOrders = stagedData?.orders ?? [];
  const activePositionsCount = pnl?.positions_count ?? activeTrades.length;

  const combinedOrderRows = [
    ...openOrders.map((ord) => ({
      key: `ord-${ord.order_id}`,
      contract: ord.tradingsymbol,
      typeLabel: `${ord.transaction_type} ${ord.quantity} · ${ord.order_type}`,
      priceValue: ord.price,
      priceDisplay: `₹${formatNum(ord.price)}`,
      status: ord.status,
    })),
    ...gtts.map((gtt) => ({
      key: `gtt-${gtt.gtt_id}`,
      contract: gtt.tradingsymbol,
      typeLabel: `GTT #${gtt.gtt_id}`,
      priceValue: gtt.trigger_value ?? gtt.limit_price ?? 0,
      priceDisplay: `${gtt.trigger_value !== null ? `₹${formatNum(gtt.trigger_value)}` : "—"} / ${gtt.limit_price !== null ? `₹${formatNum(gtt.limit_price)}` : "—"}`,
      status: gtt.trigger_type,
    })),
  ];

  const ordersSort = useTableSort(combinedOrderRows, "contract", "asc", {
    contract: (r) => r.contract,
    typeLabel: (r) => r.typeLabel,
    priceValue: (r) => r.priceValue,
    status: (r) => r.status,
  });

  const activeTradesSort = useTableSort(activeTrades, "unrealized_pnl", "desc", {
    tradingsymbol: (r) => r.tradingsymbol,
    side: (r) => `${r.side} ${r.qty}`,
    entry_price: (r) => r.entry_price,
    decay_pct: (r) => r.decay_pct,
    unrealized_pnl: (r) => r.unrealized_pnl,
  });

  const closedTradesSort = useTableSort(closedTrades, "realized_pnl", "desc", {
    tradingsymbol: (r) => r.tradingsymbol,
    qty: (r) => r.qty,
    entry_price: (r) => r.entry_price,
    decay_pct: (r) => r.decay_pct,
    realized_pnl: (r) => r.realized_pnl,
    exit_reason: (r) => r.exit_reason ?? "",
  });

  return (
    <section className="space-y-4">
      {/* Slim Action Bar */}
      <div className="flex flex-col gap-3 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5">
          <h1 className="text-lg font-semibold tracking-tight text-[var(--hify-text)]">
            Trading Cockpit
          </h1>
          {status?.user_id && (
            <span className="font-mono font-mono-num rounded border border-[var(--hify-border)] px-2 py-0.5 text-xs text-[var(--hify-text-secondary)]">
              {status.user_id}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleKiteLogin}
            className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-[var(--hify-gold)] px-4 py-2 text-sm font-semibold text-[#18181B] transition-colors hover:bg-[var(--hify-gold-hover)]"
          >
            <ExternalLink className="h-4 w-4" />
            <span>Kite Login</span>
          </button>

          <button
            type="button"
            onClick={() => setShowTokenBox((prev) => !prev)}
            className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3 py-2 text-xs font-medium text-[var(--hify-text)] hover:bg-[var(--hify-surface-raised)]"
          >
            <KeyRound className="h-4 w-4" />
            <span>Token</span>
            {showTokenBox ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>

          <button
            type="button"
            onClick={() => void loadDashboard()}
            disabled={loading}
            className="inline-flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface)] px-3 py-2 text-xs font-medium text-[var(--hify-text)] hover:bg-[var(--hify-surface-raised)] disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>

          <KillSwitchButton onTriggered={() => void loadDashboard()} />
        </div>
      </div>

      {/* Collapsible request_token paste box */}
      {showTokenBox && (
        <form
          onSubmit={handleExchangeToken}
          className="flex flex-col gap-2 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-3 sm:flex-row sm:items-center"
        >
          <input
            type="text"
            value={requestToken}
            onChange={(e) => setRequestToken(e.target.value)}
            placeholder="Paste Kite request_token from callback URL..."
            className="font-mono font-mono-num min-h-[44px] flex-1 rounded-lg border border-[var(--hify-border)] bg-[var(--hify-bg)] px-3 py-2 text-sm text-[var(--hify-text)] placeholder:text-[var(--hify-text-secondary)] focus:outline-none focus:ring-2 focus:ring-[var(--hify-border)]"
          />
          <button
            type="submit"
            disabled={exchangingToken || !requestToken.trim()}
            className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-[var(--hify-border)] bg-[var(--hify-surface-raised)] px-4 py-2 text-sm font-semibold text-[var(--hify-text)] hover:border-[var(--hify-gold)] disabled:opacity-50"
          >
            {exchangingToken ? "Connecting..." : "Connect Session"}
          </button>
        </form>
      )}

      {authNotice && (
        <p className="text-xs text-[#8E6C20] dark:text-[#C8A951]">{authNotice}</p>
      )}

      {error && (
        <div className="rounded-xl border border-[var(--hify-error)] bg-[var(--hify-surface)] p-3 text-sm text-[var(--hify-error)]">
          {error}
        </div>
      )}

      {/* Crisp 5-KPI Strip */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-3.5">
          <p className="text-[11px] font-medium text-[var(--hify-text-secondary)]">Total P&amp;L</p>
          <p
            className={`font-mono font-mono-num mt-1 text-lg font-semibold ${
              (pnl?.total_pnl ?? 0) >= 0
                ? "text-[var(--hify-success)]"
                : "text-[var(--hify-error)]"
            }`}
          >
            {pnl ? formatINR(pnl.total_pnl, true) : "—"}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-3.5">
          <p className="text-[11px] font-medium text-[var(--hify-text-secondary)]">Unrealized MTM</p>
          <p
            className={`font-mono font-mono-num mt-1 text-lg font-semibold ${
              (pnl?.unrealized_mtm ?? 0) >= 0
                ? "text-[var(--hify-success)]"
                : "text-[var(--hify-error)]"
            }`}
          >
            {pnl ? formatINR(pnl.unrealized_mtm, true) : "—"}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-3.5">
          <p className="text-[11px] font-medium text-[var(--hify-text-secondary)]">Realized P&amp;L</p>
          <p
            className={`font-mono font-mono-num mt-1 text-lg font-semibold ${
              (pnl?.realized_pnl ?? 0) >= 0
                ? "text-[var(--hify-success)]"
                : "text-[var(--hify-error)]"
            }`}
          >
            {pnl ? formatINR(pnl.realized_pnl, true) : "—"}
          </p>
        </div>

        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-3.5">
          <p className="text-[11px] font-medium text-[var(--hify-text-secondary)]">
            Margin Available
          </p>
          <p className="font-mono font-mono-num mt-1 text-lg font-semibold text-[var(--hify-text)]">
            {margins ? formatINR(margins.total_available) : "—"}
          </p>
          <p className="font-mono font-mono-num text-[10px] text-[var(--hify-text-secondary)]">
            {margins ? `${formatINR(margins.available_cash)} / ${formatINR(margins.collateral_pledged)}` : "Cash / Pledged"}
          </p>
        </div>

        <div className="col-span-2 rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-3.5 lg:col-span-1">
          <p className="text-[11px] font-medium text-[var(--hify-text-secondary)]">
            ₹25L Aukaat Cap
          </p>
          <p className="font-mono font-mono-num mt-1 text-lg font-semibold text-[#8E6C20] dark:text-[#C8A951]">
            {activePositionsCount} / 4 naked
          </p>
        </div>
      </div>

      {/* Open Orders & Active GTTs + Staged Orders */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--hify-text)]">
              Open Orders ({openOrders.length}) &amp; GTTs ({gtts.length})
            </h2>
          </div>

          {openOrders.length === 0 && gtts.length === 0 ? (
            <p className="mt-3 text-xs text-[var(--hify-text-secondary)]">
              No open orders or active GTT triggers.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                    <SortableTh label="Contract" columnKey="contract" activeKey={ordersSort.sortKey} dir={ordersSort.sortDir} onSort={ordersSort.toggleSort} className="py-2 pr-3" />
                    <SortableTh label="Type" columnKey="typeLabel" activeKey={ordersSort.sortKey} dir={ordersSort.sortDir} onSort={ordersSort.toggleSort} className="py-2 pr-3" />
                    <SortableTh label="Price / Trigger" columnKey="priceValue" activeKey={ordersSort.sortKey} dir={ordersSort.sortDir} onSort={ordersSort.toggleSort} align="right" className="py-2 pr-3" />
                    <SortableTh label="Status" columnKey="status" activeKey={ordersSort.sortKey} dir={ordersSort.sortDir} onSort={ordersSort.toggleSort} align="right" className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--hify-border)]">
                  {ordersSort.sortedRows.map((row) => (
                    <tr key={row.key}>
                      <td className="py-2.5 pr-3 font-semibold text-[var(--hify-text)]">
                        {row.contract}
                      </td>
                      <td className="font-mono font-mono-num py-2.5 pr-3 text-[var(--hify-text-secondary)]">
                        {row.typeLabel}
                      </td>
                      <td className="font-mono font-mono-num py-2.5 pr-3 text-right text-[var(--hify-text)]">
                        {row.priceDisplay}
                      </td>
                      <td className="py-2.5 text-right font-medium text-[#8E6C20] dark:text-[#C8A951]">
                        {row.status}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Staged ATO / GTT Orders */}
        <StagedOrdersList orders={stagedOrders} onApproved={() => void loadDashboard()} />
      </div>

      {/* Active Trades & Closed Trades */}
      <div className="rounded-xl border border-[var(--hify-border)] bg-[var(--hify-surface)] p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-sm font-semibold text-[var(--hify-text)]">Trades</h2>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setTradesTab("active")}
              className={`min-h-[44px] rounded-lg border px-4 py-2 text-xs font-semibold transition-colors ${
                tradesTab === "active"
                  ? "border-[var(--hify-gold)] bg-[var(--hify-gold-milestone)] text-[#8E6C20] dark:bg-[var(--hify-surface-raised)] dark:text-[#C8A951]"
                  : "border-[var(--hify-border)] bg-[var(--hify-surface)] text-[var(--hify-text-secondary)]"
              }`}
            >
              Active ({activeTrades.length})
            </button>
            <button
              type="button"
              onClick={() => setTradesTab("closed")}
              className={`min-h-[44px] rounded-lg border px-4 py-2 text-xs font-semibold transition-colors ${
                tradesTab === "closed"
                  ? "border-[var(--hify-gold)] bg-[var(--hify-gold-milestone)] text-[#8E6C20] dark:bg-[var(--hify-surface-raised)] dark:text-[#C8A951]"
                  : "border-[var(--hify-border)] bg-[var(--hify-surface)] text-[var(--hify-text-secondary)]"
              }`}
            >
              Closed ({closedTrades.length})
            </button>
          </div>
        </div>

        {tradesTab === "active" ? (
          activeTrades.length === 0 ? (
            <p className="mt-3 text-xs text-[var(--hify-text-secondary)]">
              No active open trades.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                    <SortableTh label="Contract" columnKey="tradingsymbol" activeKey={activeTradesSort.sortKey} dir={activeTradesSort.sortDir} onSort={activeTradesSort.toggleSort} className="py-2 pr-4" />
                    <SortableTh label="Side / Qty" columnKey="side" activeKey={activeTradesSort.sortKey} dir={activeTradesSort.sortDir} onSort={activeTradesSort.toggleSort} className="py-2 pr-4" />
                    <SortableTh label="Entry → LTP" columnKey="entry_price" activeKey={activeTradesSort.sortKey} dir={activeTradesSort.sortDir} onSort={activeTradesSort.toggleSort} className="py-2 pr-4" />
                    <SortableTh label="Decay %" columnKey="decay_pct" activeKey={activeTradesSort.sortKey} dir={activeTradesSort.sortDir} onSort={activeTradesSort.toggleSort} align="right" className="py-2 pr-4" />
                    <SortableTh label="Unrealized P&L" columnKey="unrealized_pnl" activeKey={activeTradesSort.sortKey} dir={activeTradesSort.sortDir} onSort={activeTradesSort.toggleSort} align="right" className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--hify-border)]">
                  {activeTradesSort.sortedRows.map((trade) => (
                    <tr key={trade.tradingsymbol}>
                      <td className="py-2.5 pr-4 font-semibold text-[var(--hify-text)]">
                        {trade.tradingsymbol}
                      </td>
                      <td className="font-mono font-mono-num py-2.5 pr-4 text-[var(--hify-text-secondary)]">
                        {trade.side} {trade.qty}
                      </td>
                      <td className="font-mono font-mono-num py-2.5 pr-4 text-[var(--hify-text-secondary)]">
                        ₹{formatNum(trade.entry_price)} → ₹{formatNum(trade.current_price)}
                      </td>
                      <td className="font-mono font-mono-num py-2.5 pr-4 text-right font-semibold text-[#8E6C20] dark:text-[#C8A951]">
                        {formatNum(trade.decay_pct, 1)}%
                      </td>
                      <td
                        className={`font-mono font-mono-num py-2.5 text-right font-semibold ${
                          trade.unrealized_pnl >= 0
                            ? "text-[var(--hify-success)]"
                            : "text-[var(--hify-error)]"
                        }`}
                      >
                        {formatINR(trade.unrealized_pnl, true)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : closedTrades.length === 0 ? (
          <p className="mt-3 text-xs text-[var(--hify-text-secondary)]">
            No closed trades recorded yet.
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[var(--hify-border)] text-[var(--hify-text-secondary)]">
                  <SortableTh label="Contract" columnKey="tradingsymbol" activeKey={closedTradesSort.sortKey} dir={closedTradesSort.sortDir} onSort={closedTradesSort.toggleSort} className="py-2 pr-4" />
                  <SortableTh label="Qty" columnKey="qty" activeKey={closedTradesSort.sortKey} dir={closedTradesSort.sortDir} onSort={closedTradesSort.toggleSort} className="py-2 pr-4" />
                  <SortableTh label="Entry → Exit" columnKey="entry_price" activeKey={closedTradesSort.sortKey} dir={closedTradesSort.sortDir} onSort={closedTradesSort.toggleSort} className="py-2 pr-4" />
                  <SortableTh label="Decay %" columnKey="decay_pct" activeKey={closedTradesSort.sortKey} dir={closedTradesSort.sortDir} onSort={closedTradesSort.toggleSort} align="right" className="py-2 pr-4" />
                  <SortableTh label="Realized P&L" columnKey="realized_pnl" activeKey={closedTradesSort.sortKey} dir={closedTradesSort.sortDir} onSort={closedTradesSort.toggleSort} align="right" className="py-2 pr-4" />
                  <SortableTh label="Exit Reason" columnKey="exit_reason" activeKey={closedTradesSort.sortKey} dir={closedTradesSort.sortDir} onSort={closedTradesSort.toggleSort} className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--hify-border)]">
                {closedTradesSort.sortedRows.map((trade, idx) => (
                  <tr key={trade.kite_trade_id ?? `${trade.tradingsymbol}-${idx}`}>
                    <td className="py-2.5 pr-4 font-semibold text-[var(--hify-text)]">
                      {trade.tradingsymbol}
                    </td>
                    <td className="font-mono font-mono-num py-2.5 pr-4 text-[var(--hify-text)]">
                      {trade.qty}
                    </td>
                    <td className="font-mono font-mono-num py-2.5 pr-4 text-[var(--hify-text-secondary)]">
                      ₹{formatNum(trade.entry_price)} → ₹{formatNum(trade.exit_price)}
                    </td>
                    <td className="font-mono font-mono-num py-2.5 pr-4 text-right text-[#8E6C20] dark:text-[#C8A951]">
                      {formatNum(trade.decay_pct, 1)}%
                    </td>
                    <td
                      className={`font-mono font-mono-num py-2.5 pr-4 text-right font-semibold ${
                        trade.realized_pnl >= 0
                          ? "text-[var(--hify-success)]"
                          : "text-[var(--hify-error)]"
                      }`}
                    >
                      {formatINR(trade.realized_pnl, true)}
                    </td>
                    <td className="py-2.5 text-[var(--hify-text-secondary)]">
                      {trade.exit_reason ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
