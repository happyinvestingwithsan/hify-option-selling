"""SQLite connection helper and schema initialization."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import PROJECT_ROOT, get_settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL CHECK (option_type IN ('PE', 'CE', 'FUT')),
    expiry TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('SELL', 'BUY')),
    qty INTEGER NOT NULL,
    lot_size INTEGER NOT NULL DEFAULT 1,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL DEFAULT 0.0,
    decay_pct REAL NOT NULL DEFAULT 0.0,
    is_hedged INTEGER NOT NULL DEFAULT 0,
    hedge_leg_id INTEGER,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED', 'ROLLED')),
    opened_at TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT,
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS staged_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL CHECK (option_type IN ('PE', 'CE', 'FUT')),
    expiry TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('SELL', 'BUY')),
    qty INTEGER NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'LIMIT' CHECK (order_type = 'LIMIT'),
    limit_price REAL NOT NULL,
    bid_price REAL,
    ask_price REAL,
    spread_pct REAL,
    gtt_target_price REAL,
    gtt_decay_pct REAL,
    is_hedged INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'STAGED' CHECK (status IN ('STAGED', 'PENDING', 'APPROVED', 'APPROVED_DRY_RUN', 'SENT', 'CANCELLED', 'CANCELLED_KILL_SWITCH', 'REJECTED')),
    guardrail_passed INTEGER NOT NULL DEFAULT 1,
    override_reason TEXT DEFAULT '',
    kite_order_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL CHECK (option_type IN ('PE', 'CE', 'FUT')),
    expiry TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('SELL', 'BUY')),
    qty INTEGER NOT NULL,
    lot_size INTEGER NOT NULL DEFAULT 1,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL DEFAULT 0.0,
    exit_price REAL,
    decay_pct REAL NOT NULL DEFAULT 0.0,
    decay_target_pct REAL NOT NULL DEFAULT 50.0,
    margin_blocked REAL NOT NULL DEFAULT 0.0,
    ppm_pct REAL NOT NULL DEFAULT 0.0,
    ato_trigger_price REAL,
    is_ato_triggered INTEGER NOT NULL DEFAULT 1,
    is_hedged INTEGER NOT NULL DEFAULT 0,
    is_covered_call INTEGER NOT NULL DEFAULT 0,
    target_hit INTEGER NOT NULL DEFAULT 0,
    closed_before_target INTEGER NOT NULL DEFAULT 0,
    exit_reason TEXT DEFAULT '',
    rollover_from_id INTEGER,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'ATO_WAITING', 'CLOSED', 'ROLLED')),
    strategy_tag TEXT DEFAULT 'WHEEL_PE',
    notes TEXT DEFAULT '',
    opened_at TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT,
    pnl REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lessons_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT 'DISCIPLINE',
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    mistake_type TEXT DEFAULT '',
    rule_added TEXT DEFAULT '',
    position_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trades_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER,
    symbol TEXT NOT NULL,
    strike REAL NOT NULL,
    option_type TEXT NOT NULL CHECK (option_type IN ('PE', 'CE', 'FUT')),
    expiry TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('SELL', 'BUY')),
    qty INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    decay_pct REAL NOT NULL DEFAULT 0.0,
    exit_reason TEXT DEFAULT '',
    override_reason TEXT DEFAULT '',
    kite_trade_id TEXT,
    executed_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS console_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    execution_time TEXT NOT NULL,
    trade_type TEXT NOT NULL CHECK (trade_type IN ('BUY', 'SELL')),
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    expiry_date TEXT DEFAULT '',
    source TEXT NOT NULL DEFAULT 'CONSOLE' CHECK (source IN ('CONSOLE', 'KITE_LIVE')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(trade_id, order_id, symbol, execution_time)
);

CREATE TABLE IF NOT EXISTS console_pnl_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_label TEXT NOT NULL DEFAULT '',
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    charges REAL NOT NULL DEFAULT 0.0,
    other_credit_debit REAL NOT NULL DEFAULT 0.0,
    net_realized_pnl REAL NOT NULL DEFAULT 0.0,
    charges_breakdown_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS console_symbol_pnl (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    quantity INTEGER NOT NULL DEFAULT 0,
    buy_value REAL NOT NULL DEFAULT 0.0,
    sell_value REAL NOT NULL DEFAULT 0.0,
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    realized_pnl_pct REAL NOT NULL DEFAULT 0.0,
    open_quantity INTEGER NOT NULL DEFAULT 0,
    open_quantity_type TEXT DEFAULT '',
    open_value REAL NOT NULL DEFAULT 0.0,
    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    unrealized_pnl_pct REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS backoffice_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_date TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'live',
    synced_fills INTEGER NOT NULL DEFAULT 0,
    skipped_duplicates INTEGER NOT NULL DEFAULT 0,
    open_positions_count INTEGER NOT NULL DEFAULT 0,
    live_unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    closed_trades_reconstructed INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS backoffice_live_positions (
    symbol TEXT PRIMARY KEY,
    underlying TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    average_price REAL NOT NULL DEFAULT 0.0,
    last_price REAL NOT NULL DEFAULT 0.0,
    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
    m2m REAL NOT NULL DEFAULT 0.0,
    product TEXT DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS delivery_equity_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    underlying TEXT NOT NULL,
    fno_contract TEXT NOT NULL DEFAULT '',
    fno_strike REAL NOT NULL,
    fno_expiry TEXT NOT NULL DEFAULT '',
    qty INTEGER NOT NULL,
    equity_sell_price REAL NOT NULL,
    equity_sell_date TEXT NOT NULL,
    equity_order_id TEXT NOT NULL DEFAULT '',
    equity_trade_ids TEXT NOT NULL DEFAULT '',
    charges REAL NOT NULL DEFAULT 0.0,
    economic_pnl REAL NOT NULL,
    console_fifo_pnl REAL,
    reason TEXT NOT NULL DEFAULT 'MISSED_ROLLOVER_DELIVERY',
    notes TEXT NOT NULL DEFAULT '',
    equity_handoff_status TEXT NOT NULL DEFAULT 'BOOKED_IN_OPTIONS' CHECK (equity_handoff_status IN ('BOOKED_IN_OPTIONS', 'TRANSFERRED_TO_EQUITY')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS universe_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    universe_type TEXT NOT NULL CHECK (universe_type IN ('F40', 'E40', 'NSE_FNO')),
    cap_tier TEXT NOT NULL DEFAULT 'large' CHECK (cap_tier IN ('large', 'mid', 'small')),
    sector TEXT DEFAULT '',
    lot_size INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    added_at TEXT NOT NULL DEFAULT (datetime('now')),
    removed_at TEXT,
    UNIQUE(symbol, universe_type)
);

CREATE TABLE IF NOT EXISTS universe_changelog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    universe_type TEXT NOT NULL CHECK (universe_type IN ('F40', 'E40', 'NSE_FNO')),
    action TEXT NOT NULL CHECK (action IN ('ADDED', 'REMOVED', 'RESTORED')),
    reason TEXT DEFAULT '',
    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fundamentals_cache (
    symbol TEXT PRIMARY KEY,
    market_cap_cr REAL,
    cap_tier TEXT NOT NULL DEFAULT 'large' CHECK (cap_tier IN ('large', 'mid', 'small')),
    current_pe REAL,
    pe_median_3y REAL,
    pe_median_5y REAL,
    pe_median_10y REAL,
    roce_pct REAL,
    roe_pct REAL,
    debt_to_equity REAL,
    net_debt_to_equity REAL,
    public_holding_pct REAL,
    institutional_holding_pct REAL,
    promoter_pledge_pct REAL,
    peak_sales_10y REAL,
    latest_sales REAL,
    peak_pat_10y REAL,
    latest_pat REAL,
    interest_coverage REAL,
    is_psu INTEGER NOT NULL DEFAULT 0,
    fundamental_passed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scanner_technicals_cache (
    symbol TEXT PRIMARY KEY,
    instrument_type TEXT NOT NULL DEFAULT 'EQ' CHECK (instrument_type IN ('EQ', 'INDEX')),
    current_price REAL,
    open_price REAL,
    high_price REAL,
    low_price REAL,
    prev_close REAL,
    ath_price REAL,
    high_52w REAL,
    sma_200 REAL,
    lower_blue_line REAL,
    is_red_candle INTEGER DEFAULT 0,
    intraday_drop_pct REAL DEFAULT 0.0,
    hv_20 REAL DEFAULT 0.0,
    iv_pct REAL DEFAULT 0.0,
    hv_spike_ratio REAL DEFAULT 1.0,
    option_instrument TEXT,
    option_strike REAL,
    option_expiry TEXT,
    option_bid REAL DEFAULT 0.0,
    option_ask REAL DEFAULT 0.0,
    bid_ask_spread_pct REAL DEFAULT 0.0,
    premium REAL DEFAULT 0.0,
    lot_size INTEGER DEFAULT 0,
    margin_required REAL DEFAULT 0.0,
    data_source TEXT NOT NULL DEFAULT 'cached',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve database path and ensure its parent directory exists."""
    if db_path is not None:
        resolved = Path(db_path)
        if not resolved.is_absolute():
            resolved = PROJECT_ROOT / resolved
    else:
        resolved = get_settings().resolved_database_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Create a SQLite connection with Row factory and foreign keys enabled."""
    resolved = get_db_path(db_path)
    conn = sqlite3.connect(str(resolved), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_session(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager that commits on success and closes the connection."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_staged_orders_if_needed(conn: sqlite3.Connection) -> None:
    """Ensure staged_orders supports U4 statuses and is_hedged column on existing DBs."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='staged_orders'"
    ).fetchone()
    if not row or not row["sql"]:
        return

    table_sql = row["sql"]
    if "APPROVED_DRY_RUN" in table_sql and "is_hedged" in table_sql:
        return

    cols_info = conn.execute("PRAGMA table_info(staged_orders)").fetchall()
    existing_cols = {col["name"] for col in cols_info}
    has_is_hedged = "is_hedged" in existing_cols
    is_hedged_expr = "is_hedged" if has_is_hedged else "0 AS is_hedged"

    conn.executescript(
        f"""
        ALTER TABLE staged_orders RENAME TO staged_orders_old;
        CREATE TABLE staged_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            strike REAL NOT NULL,
            option_type TEXT NOT NULL CHECK (option_type IN ('PE', 'CE', 'FUT')),
            expiry TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('SELL', 'BUY')),
            qty INTEGER NOT NULL,
            order_type TEXT NOT NULL DEFAULT 'LIMIT' CHECK (order_type = 'LIMIT'),
            limit_price REAL NOT NULL,
            bid_price REAL,
            ask_price REAL,
            spread_pct REAL,
            gtt_target_price REAL,
            gtt_decay_pct REAL,
            is_hedged INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'STAGED' CHECK (status IN ('STAGED', 'PENDING', 'APPROVED', 'APPROVED_DRY_RUN', 'SENT', 'CANCELLED', 'CANCELLED_KILL_SWITCH', 'REJECTED')),
            guardrail_passed INTEGER NOT NULL DEFAULT 1,
            override_reason TEXT DEFAULT '',
            kite_order_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO staged_orders (
            id, symbol, strike, option_type, expiry, side, qty, order_type,
            limit_price, bid_price, ask_price, spread_pct, gtt_target_price,
            gtt_decay_pct, is_hedged, status, guardrail_passed, override_reason,
            kite_order_id, created_at, updated_at
        )
        SELECT
            id, symbol, strike, option_type, expiry, side, qty, order_type,
            limit_price, bid_price, ask_price, spread_pct, gtt_target_price,
            gtt_decay_pct, {is_hedged_expr}, status, guardrail_passed, override_reason,
            kite_order_id, created_at, updated_at
        FROM staged_orders_old;
        DROP TABLE staged_orders_old;
        """
    )


def _migrate_paper_trades_if_needed(conn: sqlite3.Connection) -> None:
    """Ensure paper_trades supports U5 ATO_WAITING/ROLLED statuses and simulation columns."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='paper_trades'"
    ).fetchone()
    if not row or not row["sql"]:
        return

    table_sql = row["sql"]
    if "ATO_WAITING" in table_sql and "decay_target_pct" in table_sql:
        return

    cols_info = conn.execute("PRAGMA table_info(paper_trades)").fetchall()
    existing_cols = {col["name"] for col in cols_info}

    def col_or_default(name: str, default_expr: str) -> str:
        return name if name in existing_cols else f"{default_expr} AS {name}"

    conn.executescript(
        f"""
        ALTER TABLE paper_trades RENAME TO paper_trades_old;
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            strike REAL NOT NULL,
            option_type TEXT NOT NULL CHECK (option_type IN ('PE', 'CE', 'FUT')),
            expiry TEXT NOT NULL,
            side TEXT NOT NULL CHECK (side IN ('SELL', 'BUY')),
            qty INTEGER NOT NULL,
            lot_size INTEGER NOT NULL DEFAULT 1,
            entry_price REAL NOT NULL,
            current_price REAL NOT NULL DEFAULT 0.0,
            exit_price REAL,
            decay_pct REAL NOT NULL DEFAULT 0.0,
            decay_target_pct REAL NOT NULL DEFAULT 50.0,
            margin_blocked REAL NOT NULL DEFAULT 0.0,
            ppm_pct REAL NOT NULL DEFAULT 0.0,
            ato_trigger_price REAL,
            is_ato_triggered INTEGER NOT NULL DEFAULT 1,
            is_hedged INTEGER NOT NULL DEFAULT 0,
            is_covered_call INTEGER NOT NULL DEFAULT 0,
            target_hit INTEGER NOT NULL DEFAULT 0,
            closed_before_target INTEGER NOT NULL DEFAULT 0,
            exit_reason TEXT DEFAULT '',
            rollover_from_id INTEGER,
            status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'ATO_WAITING', 'CLOSED', 'ROLLED')),
            strategy_tag TEXT DEFAULT 'WHEEL_PE',
            notes TEXT DEFAULT '',
            opened_at TEXT NOT NULL DEFAULT (datetime('now')),
            closed_at TEXT,
            pnl REAL NOT NULL DEFAULT 0.0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO paper_trades (
            id, symbol, strike, option_type, expiry, side, qty, lot_size,
            entry_price, current_price, exit_price, decay_pct, decay_target_pct,
            margin_blocked, ppm_pct, ato_trigger_price, is_ato_triggered,
            is_hedged, is_covered_call, target_hit, closed_before_target,
            exit_reason, rollover_from_id, status, strategy_tag, notes,
            opened_at, closed_at, pnl, created_at, updated_at
        )
        SELECT
            id, symbol, strike, option_type, expiry, side, qty,
            {col_or_default('lot_size', '1')},
            entry_price, current_price, exit_price, decay_pct,
            {col_or_default('decay_target_pct', '50.0')},
            {col_or_default('margin_blocked', '0.0')},
            {col_or_default('ppm_pct', '0.0')},
            {col_or_default('ato_trigger_price', 'NULL')},
            {col_or_default('is_ato_triggered', '1')},
            {col_or_default('is_hedged', '0')},
            {col_or_default('is_covered_call', '0')},
            {col_or_default('target_hit', '0')},
            {col_or_default('closed_before_target', '0')},
            {col_or_default('exit_reason', "''")},
            {col_or_default('rollover_from_id', 'NULL')},
            status, strategy_tag, notes, opened_at, closed_at, pnl, created_at, updated_at
        FROM paper_trades_old;
        DROP TABLE paper_trades_old;
        """
    )


def init_db(db_path: str | Path | None = None) -> Path:
    """Initialize SQLite schema and return the resolved database path."""
    resolved = get_db_path(db_path)
    with db_session(resolved) as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate_staged_orders_if_needed(conn)
        _migrate_paper_trades_if_needed(conn)
    return resolved
