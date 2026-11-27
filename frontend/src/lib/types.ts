export interface KiteStatus {
  connected: boolean;
  mode: "live" | "dry_run";
  is_dry_run: boolean;
  user_id: string;
  login_time: string | null;
  api_key_configured: boolean;
}

export interface KiteLoginUrlResponse {
  login_url: string | null;
  mode: "live" | "dry_run";
  is_dry_run: boolean;
  message: string;
}

export interface KiteMargins {
  mode: "live" | "dry_run";
  is_dry_run: boolean;
  available_cash: number;
  collateral_pledged: number;
  utilised_margin: number;
  total_available: number;
}

export interface KitePnl {
  mode: "live" | "dry_run";
  is_dry_run: boolean;
  realized_pnl: number;
  unrealized_mtm: number;
  total_pnl: number;
  positions_count: number;
}

export interface KiteOpenOrder {
  order_id: string;
  tradingsymbol: string;
  exchange: string;
  transaction_type: string;
  order_type: string;
  product: string;
  quantity: number;
  price: number;
  status: string;
}

export interface KiteGttOrder {
  gtt_id: number | string;
  tradingsymbol: string;
  exchange: string;
  trigger_type: string;
  trigger_value: number | null;
  limit_price: number | null;
  status: string;
}

export interface KiteOrdersResponse {
  mode: "live" | "dry_run";
  is_dry_run: boolean;
  open_orders: KiteOpenOrder[];
  gtts: KiteGttOrder[];
}

export interface ActiveTrade {
  tradingsymbol: string;
  symbol: string;
  strike: number;
  option_type: "PE" | "CE" | "FUT" | string;
  expiry: string;
  side: "SELL" | "BUY" | string;
  qty: number;
  entry_price: number;
  current_price: number;
  decay_pct: number;
  unrealized_pnl: number;
  status: string;
}

export interface ClosedTrade {
  kite_trade_id?: string;
  tradingsymbol: string;
  symbol: string;
  strike: number;
  option_type: "PE" | "CE" | "FUT" | string;
  expiry: string;
  side: "SELL" | "BUY" | string;
  qty: number;
  entry_price: number;
  exit_price: number;
  realized_pnl: number;
  decay_pct: number;
  exit_reason?: string;
}

export interface KiteTradesResponse {
  mode: "live" | "dry_run";
  is_dry_run: boolean;
  active_trades: ActiveTrade[];
  closed_trades: ClosedTrade[];
}

export interface StagedOrder {
  id: number;
  symbol: string;
  strike: number;
  option_type: "PE" | "CE" | "FUT" | string;
  expiry: string;
  side: "SELL" | "BUY" | string;
  qty: number;
  order_type: string;
  limit_price: number;
  gtt_target_price: number | null;
  gtt_decay_pct: number | null;
  spread_pct: number | null;
  is_hedged: number | boolean;
  is_covered_call?: number | boolean;
  status: string;
  override_reason?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface StagedOrdersResponse {
  count: number;
  orders: StagedOrder[];
}

export interface ScannerResultItem {
  symbol: string;
  company_name: string;
  sector: string;
  cap_tier: "large" | "mid" | "small" | "LARGE" | "MID" | "SMALL" | string;
  current_price: number;
  ath_price: number;
  ath_drop_pct: number;
  required_ath_drop_pct: number;
  high_52w?: number;
  high_52w_drop_pct?: number;
  sma_200?: number;
  dma200_pct?: number;
  institutional_holding_pct: number;
  current_pe: number;
  median_pe: number;
  is_red_candle: boolean;
  intraday_drop_pct: number;
  lower_blue_line: number;
  lower_blue_line_distance_pct: number;
  suggested_moneyness: "ATM" | "OTM" | "ITM" | string;
  option_instrument: string | null;
  option_strike: number | null;
  option_bid: number;
  option_ask: number;
  bid_ask_spread_pct: number;
  premium: number;
  lot_size: number;
  margin_required: number;
  ppm_pct: number;
  ppm_tier: "Aggressive" | "Normal" | "Conservative" | string;
  iv_pct?: number;
  hv_spike_ratio?: number;
  theta_opportunity_score?: number;
  universe_tags?: string[];
  instrument_type?: string;
  data_source?: string;
  fundamentals?: Record<string, number | string | null>;
  fundamental_checks?: Record<string, boolean | null>;
  fundamental_passed?: boolean | null;
  is_psu: boolean;
  requires_hedge: boolean;
  hedge_note: string | null;
  passed: boolean;
  rejection_reasons: string[];
}

export interface ScannerFundamentalsRefreshResponse {
  symbol: string;
  fundamentals: Record<string, number | string | null>;
  fundamental_checks: Record<string, boolean | null>;
  fundamental_passed: boolean | null;
}

export interface ScannerResponse {
  total_evaluated: number;
  passed_count: number;
  rejected_count: number;
  quotes_refreshed: boolean;
  universe_type?: "F40" | "E40" | "NSE_FNO" | "INDICES" | string | null;
  slicer?: string | null;
  freshness?: "live" | "cached" | "offline" | string;
  synced_at?: string | null;
  aukaat_summary?: {
    naked_used: number;
    naked_max: number;
    naked_free: number;
    total_used: number;
    hedged_max: number;
    can_open_new: boolean;
  };
  items: ScannerResultItem[];
}

export interface DecayLockResult {
  locked: boolean;
  requires_override: boolean;
  allowed: boolean;
  required_target_pct: number;
  decay_pct: number;
  days_held: number;
  is_expiry_week: boolean;
  tier_label: string;
  override_logged: boolean;
  message: string;
}

export interface KillSwitchResponse {
  status?: string;
  cancelled_staged_count: number;
  live_cancelled_orders: number;
  live_cancelled_gtts: number;
  live_errors?: string[];
  message?: string;
}

export interface AuditFinding {
  id: string;
  source: string;
  symbol: string;
  strike: number;
  option_type: "PE" | "CE" | "FUT" | string;
  expiry: string;
  rule_violated: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | string;
  actual_decay_pct: number | null;
  expected_target_pct: number | null;
  missed_profit_inr: number;
  what_happened: string;
  better_action: string;
}

export interface RetrospectiveAuditResponse {
  discipline_score_pct: number;
  total_missed_profit_inr: number;
  total_trades_audited: number;
  violations_count: number;
  findings: AuditFinding[];
  recommendations: string[];
}

export interface LessonItem {
  id: number;
  category: string;
  title: string;
  description: string;
  mistake_type: string;
  rule_added: string;
  position_id: number | null;
  created_at: string;
}

export interface LessonsListResponse {
  count: number;
  lessons: LessonItem[];
}

export interface LessonCreatePayload {
  category: string;
  title: string;
  description: string;
  mistake_type?: string;
  rule_added?: string;
  position_id?: number | null;
  append_to_doc?: boolean;
}

export interface PaperTrade {
  id: number;
  symbol: string;
  strike: number;
  option_type: "PE" | "CE" | "FUT" | string;
  expiry: string;
  side: "SELL" | "BUY" | string;
  qty: number;
  lot_size: number;
  entry_price: number;
  current_price: number;
  exit_price: number | null;
  decay_pct: number;
  decay_target_pct: number;
  margin_blocked: number;
  ppm_pct: number;
  ato_trigger_price: number | null;
  is_ato_triggered: boolean;
  is_hedged: boolean;
  is_covered_call: boolean;
  target_hit: boolean;
  closed_before_target: boolean;
  exit_reason: string;
  rollover_from_id: number | null;
  status: "OPEN" | "ATO_WAITING" | "CLOSED" | "ROLLED" | string;
  strategy_tag: string;
  notes: string;
  opened_at: string;
  closed_at: string | null;
  pnl: number;
}

export interface PaperLabSummary {
  total_trades: number;
  open_count: number;
  ato_waiting_count: number;
  closed_count: number;
  rolled_count: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  win_rate_pct: number;
}

export interface PaperTradesResponse {
  summary: PaperLabSummary;
  trades: PaperTrade[];
}

export interface BackOfficePnlSummary {
  has_pnl_data: boolean;
  period_label: string;
  realized_pnl: number;
  unrealized_pnl: number;
  charges: number;
  other_credit_debit: number;
  net_realized_pnl: number;
  updated_at: string | null;
}

export interface BackOfficeSymbolPnl {
  symbol: string;
  quantity: number;
  buy_value: number;
  sell_value: number;
  realized_pnl: number;
  realized_pnl_pct: number;
  open_quantity: number;
  open_quantity_type: string;
  open_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  updated_at: string;
}

export interface BackOfficeFill {
  id: number;
  trade_id: string;
  order_id: string;
  symbol: string;
  trade_date: string;
  execution_time: string;
  trade_type: "BUY" | "SELL" | string;
  quantity: number;
  price: number;
  expiry_date: string;
  source: "CONSOLE" | "KITE_LIVE" | string;
  created_at: string;
}

export interface BackOfficeDeliveryAdjustment {
  id: number;
  underlying: string;
  fno_contract: string;
  fno_strike: number;
  fno_expiry: string;
  qty: number;
  equity_sell_price: number;
  equity_sell_date: string;
  equity_order_id: string;
  equity_trade_ids: string;
  charges: number;
  economic_pnl: number;
  console_fifo_pnl: number | null;
  reason: string;
  notes: string;
  equity_handoff_status: "BOOKED_IN_OPTIONS" | "TRANSFERRED_TO_EQUITY" | string;
  created_at: string;
  updated_at: string;
}

export interface BackOfficeUnifiedSummary {
  console_realized_pnl: number;
  kite_live_delta_realized_pnl: number;
  total_realized_pnl: number;
  charges: number;
  other_credit_debit: number;
  net_realized_pnl: number;
  unrealized_pnl: number;
  unrealized_source: "KITE_LIVE" | "CONSOLE" | string;
  net_trading_pnl: number;
  delivery_equity_price_pnl?: number;
  delivery_equity_charges?: number;
  delivery_equity_pnl?: number;
  delivery_adjustments_count?: number;
  true_strategy_net_realized_pnl?: number;
  true_strategy_net_trading_pnl?: number;
}

export interface BackOfficeTickerContract {
  symbol: string;
  realized_pnl: number;
  unrealized_pnl: number;
  net_pnl: number;
  open_qty: number;
  source: string;
}

export interface BackOfficeTickerPnl {
  ticker: string;
  fno_realized_pnl?: number;
  delivery_adj_pnl?: number;
  realized_pnl: number;
  unrealized_pnl: number;
  net_pnl: number;
  status: "PROFIT" | "LOSS" | string;
  contracts_count: number;
  open_contracts_count: number;
  contracts: BackOfficeTickerContract[];
}

export interface BackOfficeTodayReview {
  fills_today: number;
  closed_trades_today: number;
  realized_today: number;
  open_positions_count: number;
  live_unrealized_pnl: number;
}

export interface BackOfficeSyncStatus {
  console_last_trade_date: string | null;
  console_updated_at: string | null;
  kite_last_sync_date: string | null;
  kite_last_sync_at: string | null;
  synced_today: boolean;
  kite_connected: boolean;
  gap_days_count: number;
  gap_days: string[];
  today_review: BackOfficeTodayReview;
}

export interface BackOfficeSummaryResponse {
  summary: BackOfficePnlSummary;
  unified_summary?: BackOfficeUnifiedSummary;
  sync_status?: BackOfficeSyncStatus;
  charges_breakdown: Record<string, number>;
  ticker_pnl?: BackOfficeTickerPnl[];
  symbol_pnl: BackOfficeSymbolPnl[];
  recent_fills: BackOfficeFill[];
  delivery_adjustments?: BackOfficeDeliveryAdjustment[];
  total_fills_count: number;
  reconstructed_trades_count: number;
}

export interface BackOfficeTradebookImportResult {
  file?: string;
  filename?: string;
  total_rows_parsed: number;
  inserted_fills: number;
  skipped_duplicates: number;
  closed_trades_reconstructed: number;
  open_lots_count: number;
}

export interface BackOfficePnlImportResult {
  file?: string;
  filename?: string;
  period_label: string;
  realized_pnl: number;
  unrealized_pnl: number;
  charges: number;
  other_credit_debit: number;
  net_realized_pnl: number;
  charges_heads_count: number;
  symbols_upserted: number;
}

export interface BackOfficeImportLocalResponse {
  folder: string;
  tradebook_files: BackOfficeTradebookImportResult[];
  pnl_files: BackOfficePnlImportResult[];
}

export interface BackOfficeUploadResponse {
  tradebook: BackOfficeTradebookImportResult | null;
  pnl: BackOfficePnlImportResult | null;
}

export interface BackOfficeSyncKiteResponse {
  mode: "live" | "dry_run";
  is_dry_run: boolean;
  sync_date?: string;
  synced_fills: number;
  skipped_duplicates: number;
  open_positions_count?: number;
  live_unrealized_pnl?: number;
  closed_trades_reconstructed?: number;
  open_lots_count?: number;
  message?: string;
}

export function formatINR(value: number, showSign = false): string {
  const absVal = Math.abs(value);
  const formatted = new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
    minimumFractionDigits: absVal % 1 === 0 ? 0 : 2,
  }).format(absVal);

  if (value < 0) return `-${formatted}`;
  if (showSign && value > 0) return `+${formatted}`;
  return formatted;
}

export function formatNum(value: number, decimals = 2): string {
  return value.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}
