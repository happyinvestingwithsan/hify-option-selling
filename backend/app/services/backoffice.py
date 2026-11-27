"""Back Office service: Zerodha Console F&O Tradebook + P&L importer & Kite trades() auto-sync (Unit U9)."""

from __future__ import annotations

import io
import json
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import openpyxl

from app.config import PROJECT_ROOT
from app.db import db_session
from app.kite_client import KiteService, calculate_decay_pct, parse_nfo_symbol

DEFAULT_CONSOLE_FOLDER = PROJECT_ROOT / "Console_Reports" / "FY2627_FNO"


def _to_str(val: Any) -> str:
    """Normalize Excel cell value (str, date, datetime, int/float) to clean string."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(val, date):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def _to_float(val: Any, default: float = 0.0) -> float:
    """Safely convert Excel numeric cell to float."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _to_int(val: Any, default: int = 0) -> int:
    """Safely convert Excel numeric cell to int."""
    if val is None or val == "":
        return default
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return default


def _rebuild_trades_history_from_fills(conn: Any) -> dict[str, int]:
    """Reconstruct FIFO round-trip closed trades from console_fills into trades_history."""
    rows = conn.execute(
        """
        SELECT id, trade_id, order_id, symbol, trade_date, execution_time,
               trade_type, quantity, price, expiry_date, source
        FROM console_fills
        ORDER BY execution_time ASC, id ASC
        """
    ).fetchall()

    # Clear prior Back Office reconstructed rows so re-imports and incremental syncs stay idempotent.
    conn.execute("DELETE FROM trades_history WHERE kite_trade_id LIKE 'BO:%'")

    lots_by_symbol: dict[str, deque[list[Any]]] = defaultdict(deque)
    closed_count = 0

    for row in rows:
        tradingsymbol = str(row["symbol"]).strip().upper()
        side = str(row["trade_type"]).strip().upper()
        qty = int(row["quantity"])
        price = float(row["price"])
        exec_time = str(row["execution_time"] or row["trade_date"])
        expiry_date = str(row["expiry_date"] or "")
        if qty <= 0 or side not in {"BUY", "SELL"}:
            continue

        queue = lots_by_symbol[tradingsymbol]
        remaining = qty

        while remaining > 0 and queue and queue[0][0] != side:
            open_lot = queue[0]
            open_side, open_qty, open_price, open_time, open_expiry = open_lot
            matched = min(remaining, open_qty)

            if open_side == "SELL":
                realized_pnl = round((open_price - price) * matched, 2)
            else:
                realized_pnl = round((price - open_price) * matched, 2)

            decay_pct = calculate_decay_pct(open_price, price, open_side)
            underlying, strike, option_type, expiry = parse_nfo_symbol(
                tradingsymbol, default_expiry=open_expiry or expiry_date
            )
            closed_count += 1
            bo_id = f"BO:{tradingsymbol}:{open_time}:{exec_time}:{closed_count}"
            exit_reason = "CONSOLE_FIFO_CLOSE" if row["source"] == "CONSOLE" else "KITE_LIVE_FIFO_CLOSE"

            conn.execute(
                """
                INSERT INTO trades_history (
                    position_id, symbol, strike, option_type, expiry,
                    side, qty, entry_price, exit_price, realized_pnl,
                    decay_pct, exit_reason, override_reason, kite_trade_id, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
                """,
                (
                    None,
                    underlying,
                    strike,
                    option_type,
                    expiry,
                    open_side,
                    matched,
                    open_price,
                    price,
                    realized_pnl,
                    decay_pct,
                    exit_reason,
                    bo_id,
                    exec_time,
                ),
            )

            remaining -= matched
            open_lot[1] -= matched
            if open_lot[1] <= 0:
                queue.popleft()

        if remaining > 0:
            queue.append([side, remaining, price, exec_time, expiry_date])

    open_lots_count = sum(len(q) for q in lots_by_symbol.values())
    return {
        "closed_trades_reconstructed": closed_count,
        "open_lots_count": open_lots_count,
    }


def import_tradebook_xlsx(
    file_bytes: bytes,
    source: str = "CONSOLE",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Parse Zerodha Console F&O Tradebook .xlsx, deduplicate into console_fills, and rebuild FIFO trades."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb["F&O"] if "F&O" in wb.sheetnames else wb.active

    header_row_idx: int | None = None
    col_map: dict[str, int] = {}
    expiry_col_idx: int | None = None

    for r in range(1, min(60, ws.max_row + 1)):
        row_vals = [_to_str(ws.cell(r, c).value) for c in range(1, ws.max_column + 1)]
        if "Symbol" in row_vals and "Trade ID" in row_vals and "Order ID" in row_vals:
            header_row_idx = r
            for idx, name in enumerate(row_vals, start=1):
                if name:
                    col_map[name] = idx
            # Zerodha F&O tradebook has an unlabelled 14th column after Order Execution Time for Expiry Date
            exec_col = col_map.get("Order Execution Time")
            if exec_col and exec_col + 1 <= ws.max_column:
                expiry_col_idx = exec_col + 1
            break

    if header_row_idx is None:
        raise ValueError("Could not locate Tradebook header row (Symbol, Trade ID, Order ID) in Excel file.")

    required_cols = ["Symbol", "Trade Date", "Trade Type", "Quantity", "Price", "Trade ID", "Order ID", "Order Execution Time"]
    missing = [col for col in required_cols if col not in col_map]
    if missing:
        raise ValueError(f"Tradebook Excel missing required columns: {', '.join(missing)}")

    total_rows = 0
    inserted_fills = 0
    skipped_duplicates = 0

    with db_session(db_path) as conn:
        for r in range(header_row_idx + 1, ws.max_row + 1):
            symbol = _to_str(ws.cell(r, col_map["Symbol"]).value).upper()
            if not symbol:
                continue

            trade_date = _to_str(ws.cell(r, col_map["Trade Date"]).value)
            trade_type = _to_str(ws.cell(r, col_map["Trade Type"]).value).upper()
            quantity = _to_int(ws.cell(r, col_map["Quantity"]).value)
            price = _to_float(ws.cell(r, col_map["Price"]).value)
            trade_id = _to_str(ws.cell(r, col_map["Trade ID"]).value)
            order_id = _to_str(ws.cell(r, col_map["Order ID"]).value)
            execution_time = _to_str(ws.cell(r, col_map["Order Execution Time"]).value) or trade_date
            expiry_date = _to_str(ws.cell(r, expiry_col_idx).value) if expiry_col_idx else ""

            if trade_type not in {"BUY", "SELL"} or quantity <= 0:
                continue

            total_rows += 1
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO console_fills (
                    trade_id, order_id, symbol, trade_date, execution_time,
                    trade_type, quantity, price, expiry_date, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    order_id,
                    symbol,
                    trade_date,
                    execution_time,
                    trade_type,
                    quantity,
                    price,
                    expiry_date,
                    source,
                ),
            )
            if cur.rowcount > 0:
                inserted_fills += 1
            else:
                skipped_duplicates += 1

        fifo_stats = _rebuild_trades_history_from_fills(conn)

    return {
        "total_rows_parsed": total_rows,
        "inserted_fills": inserted_fills,
        "skipped_duplicates": skipped_duplicates,
        **fifo_stats,
    }


def import_pnl_xlsx(
    file_bytes: bytes,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Parse Zerodha Console F&O P&L .xlsx (Summary, Charges, Symbol P&L) into SQLite."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb["F&O"] if "F&O" in wb.sheetnames else wb.active

    period_label = ""
    summary_values: dict[str, float] = {
        "Charges": 0.0,
        "Other Credit & Debit": 0.0,
        "Realized P&L": 0.0,
        "Unrealized P&L": 0.0,
    }
    charges_breakdown: dict[str, float] = {}
    symbol_rows: list[dict[str, Any]] = []

    in_summary = False
    in_charges = False
    symbol_header_row: int | None = None
    symbol_col_map: dict[str, int] = {}

    for r in range(1, ws.max_row + 1):
        col_b = _to_str(ws.cell(r, 2).value)
        col_c = ws.cell(r, 3).value

        if not period_label and "P&L Statement" in col_b:
            period_label = col_b
            continue

        if col_b == "Summary":
            in_summary = True
            continue

        if in_summary:
            if col_b == "Charges" and col_c is None:
                in_summary = False
                continue
            if col_b in summary_values:
                summary_values[col_b] = _to_float(col_c)
                continue

        if col_b == "Account Head" and _to_str(col_c) == "Amount":
            in_summary = False
            in_charges = True
            continue

        if in_charges:
            if not col_b:
                in_charges = False
                continue
            charges_breakdown[col_b] = _to_float(col_c)
            continue

        if col_b == "Symbol" and _to_str(col_c) == "ISIN":
            symbol_header_row = r
            for c in range(2, ws.max_column + 1):
                header_name = _to_str(ws.cell(r, c).value)
                if header_name:
                    symbol_col_map[header_name] = c
            break

    if symbol_header_row is not None:
        for r in range(symbol_header_row + 1, ws.max_row + 1):
            sym = _to_str(ws.cell(r, symbol_col_map["Symbol"]).value).upper()
            if not sym:
                break
            symbol_rows.append(
                {
                    "symbol": sym,
                    "quantity": _to_int(ws.cell(r, symbol_col_map.get("Quantity", 4)).value),
                    "buy_value": _to_float(ws.cell(r, symbol_col_map.get("Buy Value", 5)).value),
                    "sell_value": _to_float(ws.cell(r, symbol_col_map.get("Sell Value", 6)).value),
                    "realized_pnl": _to_float(ws.cell(r, symbol_col_map.get("Realized P&L", 7)).value),
                    "realized_pnl_pct": _to_float(ws.cell(r, symbol_col_map.get("Realized P&L Pct.", 8)).value),
                    "open_quantity": _to_int(ws.cell(r, symbol_col_map.get("Open Quantity", 10)).value),
                    "open_quantity_type": _to_str(ws.cell(r, symbol_col_map.get("Open Quantity Type", 11)).value),
                    "open_value": _to_float(ws.cell(r, symbol_col_map.get("Open Value", 12)).value),
                    "unrealized_pnl": _to_float(ws.cell(r, symbol_col_map.get("Unrealized P&L", 13)).value),
                    "unrealized_pnl_pct": _to_float(ws.cell(r, symbol_col_map.get("Unrealized P&L Pct.", 14)).value),
                }
            )

    realized_pnl = summary_values["Realized P&L"]
    unrealized_pnl = summary_values["Unrealized P&L"]
    charges = summary_values["Charges"]
    other_cd = summary_values["Other Credit & Debit"]
    net_realized_pnl = round(realized_pnl - charges + other_cd, 4)

    with db_session(db_path) as conn:
        conn.execute("DELETE FROM console_pnl_summary")
        conn.execute(
            """
            INSERT INTO console_pnl_summary (
                period_label, realized_pnl, unrealized_pnl, charges,
                other_credit_debit, net_realized_pnl, charges_breakdown_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                period_label,
                realized_pnl,
                unrealized_pnl,
                charges,
                other_cd,
                net_realized_pnl,
                json.dumps(charges_breakdown),
            ),
        )

        for item in symbol_rows:
            conn.execute(
                """
                INSERT INTO console_symbol_pnl (
                    symbol, quantity, buy_value, sell_value,
                    realized_pnl, realized_pnl_pct, open_quantity,
                    open_quantity_type, open_value, unrealized_pnl,
                    unrealized_pnl_pct, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(symbol) DO UPDATE SET
                    quantity = excluded.quantity,
                    buy_value = excluded.buy_value,
                    sell_value = excluded.sell_value,
                    realized_pnl = excluded.realized_pnl,
                    realized_pnl_pct = excluded.realized_pnl_pct,
                    open_quantity = excluded.open_quantity,
                    open_quantity_type = excluded.open_quantity_type,
                    open_value = excluded.open_value,
                    unrealized_pnl = excluded.unrealized_pnl,
                    unrealized_pnl_pct = excluded.unrealized_pnl_pct,
                    updated_at = datetime('now')
                """,
                (
                    item["symbol"],
                    item["quantity"],
                    item["buy_value"],
                    item["sell_value"],
                    item["realized_pnl"],
                    item["realized_pnl_pct"],
                    item["open_quantity"],
                    item["open_quantity_type"],
                    item["open_value"],
                    item["unrealized_pnl"],
                    item["unrealized_pnl_pct"],
                ),
            )

    return {
        "period_label": period_label,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "charges": charges,
        "other_credit_debit": other_cd,
        "net_realized_pnl": net_realized_pnl,
        "charges_heads_count": len(charges_breakdown),
        "symbols_upserted": len(symbol_rows),
    }


def import_from_folder(
    folder_path: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Scan Console_Reports/FY2627_FNO for *tradebook*.xlsx and *pnl*.xlsx and import both."""
    target_dir = Path(folder_path) if folder_path else DEFAULT_CONSOLE_FOLDER
    if not target_dir.exists():
        raise FileNotFoundError(f"Console reports folder not found: {target_dir}")

    xlsx_files = sorted(
        p for p in target_dir.glob("*.xlsx") if not p.name.startswith("~$")
    )
    tradebook_files = [p for p in xlsx_files if "tradebook" in p.name.lower()]
    pnl_files = [p for p in xlsx_files if "pnl" in p.name.lower()]

    tradebook_results: list[dict[str, Any]] = []
    pnl_results: list[dict[str, Any]] = []

    for tb_path in tradebook_files:
        res = import_tradebook_xlsx(tb_path.read_bytes(), source="CONSOLE", db_path=db_path)
        tradebook_results.append({"file": tb_path.name, **res})

    for pnl_path in pnl_files:
        res = import_pnl_xlsx(pnl_path.read_bytes(), db_path=db_path)
        pnl_results.append({"file": pnl_path.name, **res})

    return {
        "folder": str(target_dir),
        "tradebook_files": tradebook_results,
        "pnl_files": pnl_results,
    }


def sync_kite_daily_trades(
    kite_service: KiteService,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Sync today's executed trades and live open positions from Kite Connect into SQLite."""
    kite_service._load_session()
    if not kite_service._is_live() or kite_service._kite is None:
        return {
            "mode": "dry_run",
            "is_dry_run": True,
            "synced_fills": 0,
            "skipped_duplicates": 0,
            "open_positions_count": 0,
            "live_unrealized_pnl": 0.0,
            "message": "Kite is in dry_run mode; connect Kite live session to sync today's trades.",
        }

    raw_trades = kite_service._kite.trades() or []
    try:
        raw_positions_resp = kite_service._kite.positions() or {}
    except Exception:
        raw_positions_resp = {}
    net_positions = raw_positions_resp.get("net", []) if isinstance(raw_positions_resp, dict) else []

    inserted = 0
    skipped = 0
    today_str = date.today().isoformat()
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    with db_session(db_path) as conn:
        for tr in raw_trades:
            exchange = str(tr.get("exchange", "")).upper()
            if exchange and exchange != "NFO":
                continue

            tradingsymbol = str(tr.get("tradingsymbol", "")).strip().upper()
            trade_type = str(tr.get("transaction_type", "")).strip().upper()
            quantity = _to_int(tr.get("quantity", 0))
            price = _to_float(tr.get("average_price", tr.get("price", 0.0)))
            trade_id = str(tr.get("trade_id", "")).strip()
            order_id = str(tr.get("order_id", "")).strip()
            fill_ts = tr.get("fill_timestamp") or tr.get("order_timestamp")
            execution_time = _to_str(fill_ts) or now_str
            trade_date = execution_time[:10]

            if not tradingsymbol or trade_type not in {"BUY", "SELL"} or quantity <= 0:
                continue

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO console_fills (
                    trade_id, order_id, symbol, trade_date, execution_time,
                    trade_type, quantity, price, expiry_date, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 'KITE_LIVE')
                """,
                (
                    trade_id,
                    order_id,
                    tradingsymbol,
                    trade_date,
                    execution_time,
                    trade_type,
                    quantity,
                    price,
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

        # Refresh live open NFO positions snapshot for unrealized MTM continuity
        conn.execute("DELETE FROM backoffice_live_positions")
        open_positions_count = 0
        live_unrealized_pnl = 0.0
        for pos in net_positions:
            exchange = str(pos.get("exchange", "")).upper()
            if exchange and exchange != "NFO":
                continue
            tradingsymbol = str(pos.get("tradingsymbol", "")).strip().upper()
            qty = _to_int(pos.get("quantity", 0))
            if not tradingsymbol or qty == 0:
                continue
            underlying, _, _, _ = parse_nfo_symbol(tradingsymbol)
            avg_price = _to_float(pos.get("average_price", 0.0))
            last_price = _to_float(pos.get("last_price", 0.0))
            unrealized = round(_to_float(pos.get("unrealized", pos.get("pnl", 0.0))), 2)
            m2m = round(_to_float(pos.get("m2m", 0.0)), 2)
            product = str(pos.get("product", "")).strip()
            conn.execute(
                """
                INSERT INTO backoffice_live_positions (
                    symbol, underlying, quantity, average_price, last_price,
                    unrealized_pnl, m2m, product, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tradingsymbol,
                    underlying,
                    qty,
                    avg_price,
                    last_price,
                    unrealized,
                    m2m,
                    product,
                    now_str,
                ),
            )
            open_positions_count += 1
            live_unrealized_pnl += unrealized

        live_unrealized_pnl = round(live_unrealized_pnl, 2)
        fifo_stats = _rebuild_trades_history_from_fills(conn)

        conn.execute(
            """
            INSERT INTO backoffice_sync_log (
                sync_date, mode, synced_fills, skipped_duplicates,
                open_positions_count, live_unrealized_pnl, closed_trades_reconstructed, synced_at
            ) VALUES (?, 'live', ?, ?, ?, ?, ?, ?)
            """,
            (
                today_str,
                inserted,
                skipped,
                open_positions_count,
                live_unrealized_pnl,
                fifo_stats["closed_trades_reconstructed"],
                now_str,
            ),
        )

    return {
        "mode": "live",
        "is_dry_run": False,
        "sync_date": today_str,
        "synced_fills": inserted,
        "skipped_duplicates": skipped,
        "open_positions_count": open_positions_count,
        "live_unrealized_pnl": live_unrealized_pnl,
        **fifo_stats,
    }


def _compute_ticker_pnl_and_unified(
    conn: Any,
    summary: dict[str, Any],
    cleaned_filter: str | None,
    kite_connected: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Build unified Console + Kite Live P&L, underlying ticker grouping, and sync/gap status."""
    today_str = date.today().isoformat()

    console_last_row = conn.execute(
        "SELECT MAX(trade_date) AS max_d FROM console_fills WHERE source = 'CONSOLE'"
    ).fetchone()
    console_last_trade_date = str(console_last_row["max_d"] or "") if console_last_row else ""

    last_sync_row = conn.execute(
        """
        SELECT sync_date, synced_at, open_positions_count, live_unrealized_pnl
        FROM backoffice_sync_log
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    kite_last_sync_date = str(last_sync_row["sync_date"] or "") if last_sync_row else ""
    kite_last_sync_at = str(last_sync_row["synced_at"] or "") if last_sync_row else None
    synced_today = kite_last_sync_date == today_str

    # Live positions snapshot (from most recent Kite sync)
    live_pos_rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT symbol, underlying, quantity, average_price, last_price,
                   unrealized_pnl, m2m, product, updated_at
            FROM backoffice_live_positions
            """
        ).fetchall()
    ]
    use_live_unrealized = bool(kite_last_sync_at) and (
        not summary["updated_at"] or kite_last_sync_at >= str(summary["updated_at"])
    )

    # Post-Console Kite Live FIFO closed trades (avoids double-counting Console baseline)
    if console_last_trade_date:
        kite_delta_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT symbol, strike, option_type, expiry, realized_pnl, executed_at
                FROM trades_history
                WHERE kite_trade_id LIKE 'BO:%'
                  AND exit_reason = 'KITE_LIVE_FIFO_CLOSE'
                  AND substr(executed_at, 1, 10) > ?
                """,
                (console_last_trade_date,),
            ).fetchall()
        ]
    else:
        kite_delta_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT symbol, strike, option_type, expiry, realized_pnl, executed_at
                FROM trades_history
                WHERE kite_trade_id LIKE 'BO:%'
                  AND exit_reason = 'KITE_LIVE_FIFO_CLOSE'
                """
            ).fetchall()
        ]

    kite_delta_realized = round(sum(float(r["realized_pnl"] or 0.0) for r in kite_delta_rows), 2)
    console_realized = float(summary["realized_pnl"])
    total_realized = round(console_realized + kite_delta_realized, 2)
    charges = float(summary["charges"])
    other_cd = float(summary["other_credit_debit"])
    net_realized = round(total_realized - charges + other_cd, 2)

    if use_live_unrealized:
        total_unrealized = round(sum(float(r["unrealized_pnl"] or 0.0) for r in live_pos_rows), 2)
        unrealized_source = "KITE_LIVE"
    else:
        total_unrealized = float(summary["unrealized_pnl"])
        unrealized_source = "CONSOLE"

    # Delivery Equity Adjustments (Option A: (sell - strike) * qty - charges) booked in Option Selling
    delivery_rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT id, underlying, fno_contract, fno_strike, fno_expiry, qty,
                   equity_sell_price, equity_sell_date, equity_order_id, equity_trade_ids,
                   charges, economic_pnl, console_fifo_pnl, reason, notes,
                   equity_handoff_status, created_at, updated_at
            FROM delivery_equity_adjustments
            WHERE equity_handoff_status = 'BOOKED_IN_OPTIONS'
            ORDER BY equity_sell_date DESC, id DESC
            """
        ).fetchall()
    ]
    delivery_equity_pnl = round(sum(float(r["economic_pnl"] or 0.0) for r in delivery_rows), 2)
    delivery_equity_charges = round(sum(float(r["charges"] or 0.0) for r in delivery_rows), 2)
    delivery_equity_price_pnl = round(delivery_equity_pnl + delivery_equity_charges, 2)
    true_strategy_net_realized = round(net_realized + delivery_equity_pnl, 2)
    net_trading_after_charges = round(net_realized + total_unrealized, 2)
    true_strategy_net_trading = round(net_realized + total_unrealized + delivery_equity_pnl, 2)

    unified_summary = {
        "console_realized_pnl": round(console_realized, 2),
        "kite_live_delta_realized_pnl": kite_delta_realized,
        "total_realized_pnl": total_realized,
        "charges": round(charges, 4),
        "other_credit_debit": round(other_cd, 2),
        "net_realized_pnl": net_realized,
        "unrealized_pnl": round(total_unrealized, 2),
        "unrealized_source": unrealized_source,
        "net_trading_pnl": net_trading_after_charges,
        "delivery_equity_price_pnl": delivery_equity_price_pnl,
        "delivery_equity_charges": delivery_equity_charges,
        "delivery_equity_pnl": delivery_equity_pnl,
        "delivery_adjustments_count": len(delivery_rows),
        "true_strategy_net_realized_pnl": true_strategy_net_realized,
        "true_strategy_net_trading_pnl": true_strategy_net_trading,
    }

    # Build underlying ticker grouping across Console baseline + Kite live delta + Live positions
    by_ticker: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    all_console_symbols = conn.execute(
        """
        SELECT symbol, realized_pnl, open_quantity, unrealized_pnl
        FROM console_symbol_pnl
        """
    ).fetchall()
    for row in all_console_symbols:
        contract = str(row["symbol"]).strip().upper()
        ticker, _, _, _ = parse_nfo_symbol(contract)
        entry = by_ticker[ticker].setdefault(
            contract,
            {
                "symbol": contract,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "open_qty": 0,
                "source": "CONSOLE",
            },
        )
        entry["realized_pnl"] = round(entry["realized_pnl"] + float(row["realized_pnl"] or 0.0), 2)
        if not use_live_unrealized:
            entry["unrealized_pnl"] = round(
                entry["unrealized_pnl"] + float(row["unrealized_pnl"] or 0.0), 2
            )
            entry["open_qty"] += int(row["open_quantity"] or 0)

    for row in kite_delta_rows:
        ticker = str(row["symbol"]).strip().upper()
        strike_val = float(row["strike"] or 0.0)
        strike_lbl = str(int(strike_val)) if strike_val.is_integer() else str(strike_val)
        contract_lbl = f"{ticker} {strike_lbl}{row['option_type']} ({row['expiry']})"
        entry = by_ticker[ticker].setdefault(
            contract_lbl,
            {
                "symbol": contract_lbl,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "open_qty": 0,
                "source": "KITE_LIVE",
            },
        )
        entry["realized_pnl"] = round(entry["realized_pnl"] + float(row["realized_pnl"] or 0.0), 2)
        if entry["source"] == "CONSOLE":
            entry["source"] = "CONSOLE+KITE"

    if use_live_unrealized:
        for pos in live_pos_rows:
            contract = str(pos["symbol"]).strip().upper()
            ticker = str(pos["underlying"]).strip().upper() or parse_nfo_symbol(contract)[0]
            entry = by_ticker[ticker].setdefault(
                contract,
                {
                    "symbol": contract,
                    "realized_pnl": 0.0,
                    "unrealized_pnl": 0.0,
                    "open_qty": 0,
                    "source": "KITE_LIVE",
                },
            )
            entry["unrealized_pnl"] = round(
                entry["unrealized_pnl"] + float(pos["unrealized_pnl"] or 0.0), 2
            )
            entry["open_qty"] += int(pos["quantity"] or 0)
            if entry["source"] == "CONSOLE":
                entry["source"] = "CONSOLE+KITE"

    delivery_pnl_by_ticker: dict[str, float] = defaultdict(float)
    for adj in delivery_rows:
        ticker = str(adj["underlying"]).strip().upper()
        econ_pnl = round(float(adj["economic_pnl"] or 0.0), 2)
        adj_charges = round(float(adj["charges"] or 0.0), 2)
        price_pnl = round(econ_pnl + adj_charges, 2)
        delivery_pnl_by_ticker[ticker] = round(delivery_pnl_by_ticker[ticker] + econ_pnl, 2)
        contract_lbl = (
            f"{adj['fno_contract']} → EQ EXIT ({adj['qty']} @ ₹{float(adj['equity_sell_price']):.2f})"
            if adj["fno_contract"]
            else f"{ticker} DELIVERY EQ EXIT ({adj['qty']} @ ₹{float(adj['equity_sell_price']):.2f})"
        )
        by_ticker[ticker][f"DELIV:{adj['id']}:{contract_lbl}"] = {
            "symbol": contract_lbl,
            "realized_pnl": price_pnl,
            "unrealized_pnl": 0.0,
            "open_qty": 0,
            "source": "DELIVERY_EQ_ADJ",
        }
        if adj_charges > 0:
            charges_lbl = f"{ticker} DELIVERY & EQ EXIT CHARGES (CNT)"
            by_ticker[ticker][f"DELIV_CHG:{adj['id']}:{charges_lbl}"] = {
                "symbol": charges_lbl,
                "realized_pnl": round(-adj_charges, 2),
                "unrealized_pnl": 0.0,
                "open_qty": 0,
                "source": "DELIVERY_CHARGES",
            }

    ticker_pnl: list[dict[str, Any]] = []
    for ticker, contracts_map in by_ticker.items():
        contracts = []
        for c in contracts_map.values():
            c_net = round(c["realized_pnl"] + c["unrealized_pnl"], 2)
            contracts.append({**c, "net_pnl": c_net})
        contracts.sort(key=lambda x: abs(x["net_pnl"]), reverse=True)

        if cleaned_filter:
            matches_ticker = cleaned_filter in ticker
            matches_contract = any(cleaned_filter in c["symbol"] for c in contracts)
            if not matches_ticker and not matches_contract:
                continue

        fno_realized = round(
            sum(
                c["realized_pnl"]
                for c in contracts
                if c["source"] not in {"DELIVERY_EQ_ADJ", "DELIVERY_CHARGES"}
            ),
            2,
        )
        t_realized = round(sum(c["realized_pnl"] for c in contracts), 2)
        t_unrealized = round(sum(c["unrealized_pnl"] for c in contracts), 2)
        t_delivery_adj = round(delivery_pnl_by_ticker.get(ticker, 0.0), 2)
        t_net = round(t_realized + t_unrealized, 2)
        open_contracts_count = sum(1 for c in contracts if c["open_qty"] != 0)
        ticker_pnl.append(
            {
                "ticker": ticker,
                "fno_realized_pnl": fno_realized,
                "delivery_adj_pnl": t_delivery_adj,
                "realized_pnl": t_realized,
                "unrealized_pnl": t_unrealized,
                "net_pnl": t_net,
                "status": "PROFIT" if t_net >= 0 else "LOSS",
                "contracts_count": len(contracts),
                "open_contracts_count": open_contracts_count,
                "contracts": contracts,
            }
        )

    ticker_pnl.sort(key=lambda x: (-abs(x["net_pnl"]), x["ticker"]))

    # Gap detection: weekdays strictly between console_last_trade_date and today without KITE_LIVE fills or sync log
    gap_days: list[str] = []
    if console_last_trade_date:
        try:
            start_d = date.fromisoformat(console_last_trade_date) + timedelta(days=1)
            end_d = date.today() - timedelta(days=1)
            if start_d <= end_d:
                synced_dates = {
                    str(r["sync_date"])
                    for r in conn.execute("SELECT DISTINCT sync_date FROM backoffice_sync_log").fetchall()
                }
                fill_dates = {
                    str(r["trade_date"])
                    for r in conn.execute(
                        "SELECT DISTINCT trade_date FROM console_fills WHERE source = 'KITE_LIVE'"
                    ).fetchall()
                }
                covered = synced_dates | fill_dates
                cur_d = start_d
                while cur_d <= end_d:
                    if cur_d.weekday() < 5 and cur_d.isoformat() not in covered:
                        gap_days.append(cur_d.isoformat())
                    cur_d += timedelta(days=1)
        except ValueError:
            gap_days = []

    today_fills_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM console_fills WHERE trade_date = ?", (today_str,)
    ).fetchone()
    today_closed_row = conn.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(realized_pnl), 0.0) AS pnl
        FROM trades_history
        WHERE kite_trade_id LIKE 'BO:%' AND substr(executed_at, 1, 10) = ?
        """,
        (today_str,),
    ).fetchone()

    sync_status = {
        "console_last_trade_date": console_last_trade_date or None,
        "console_updated_at": summary["updated_at"],
        "kite_last_sync_date": kite_last_sync_date or None,
        "kite_last_sync_at": kite_last_sync_at,
        "synced_today": synced_today,
        "kite_connected": kite_connected,
        "gap_days_count": len(gap_days),
        "gap_days": gap_days[:10],
        "today_review": {
            "fills_today": int(today_fills_row["cnt"]) if today_fills_row else 0,
            "closed_trades_today": int(today_closed_row["cnt"]) if today_closed_row else 0,
            "realized_today": round(float(today_closed_row["pnl"]), 2) if today_closed_row else 0.0,
            "open_positions_count": len(live_pos_rows),
            "live_unrealized_pnl": round(sum(float(r["unrealized_pnl"] or 0.0) for r in live_pos_rows), 2),
        },
    }

    return unified_summary, ticker_pnl, sync_status


def get_backoffice_summary(
    symbol_filter: str | None = None,
    db_path: str | Path | None = None,
    kite_service: KiteService | None = None,
) -> dict[str, Any]:
    """Return calibrated Console P&L summary, unified Kite delta, ticker grouping, and recent fills."""
    cleaned_filter = symbol_filter.strip().upper() if symbol_filter else None
    kite_connected = False
    if kite_service is not None:
        kite_service._load_session()
        kite_connected = bool(kite_service._is_live())

    with db_session(db_path) as conn:
        summary_row = conn.execute(
            """
            SELECT period_label, realized_pnl, unrealized_pnl, charges,
                   other_credit_debit, net_realized_pnl, charges_breakdown_json, updated_at
            FROM console_pnl_summary
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if summary_row:
            try:
                charges_breakdown = json.loads(summary_row["charges_breakdown_json"] or "{}")
            except json.JSONDecodeError:
                charges_breakdown = {}
            summary = {
                "has_pnl_data": True,
                "period_label": summary_row["period_label"],
                "realized_pnl": float(summary_row["realized_pnl"]),
                "unrealized_pnl": float(summary_row["unrealized_pnl"]),
                "charges": float(summary_row["charges"]),
                "other_credit_debit": float(summary_row["other_credit_debit"]),
                "net_realized_pnl": float(summary_row["net_realized_pnl"]),
                "updated_at": summary_row["updated_at"],
            }
        else:
            charges_breakdown = {}
            summary = {
                "has_pnl_data": False,
                "period_label": "",
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "charges": 0.0,
                "other_credit_debit": 0.0,
                "net_realized_pnl": 0.0,
                "updated_at": None,
            }

        if cleaned_filter:
            like_pattern = f"%{cleaned_filter}%"
            symbol_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT symbol, quantity, buy_value, sell_value, realized_pnl,
                           realized_pnl_pct, open_quantity, open_quantity_type,
                           open_value, unrealized_pnl, unrealized_pnl_pct, updated_at
                    FROM console_symbol_pnl
                    WHERE symbol LIKE ?
                    ORDER BY ABS(realized_pnl) DESC, symbol ASC
                    """,
                    (like_pattern,),
                ).fetchall()
            ]
            fills_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, trade_id, order_id, symbol, trade_date, execution_time,
                           trade_type, quantity, price, expiry_date, source, created_at
                    FROM console_fills
                    WHERE symbol LIKE ?
                    ORDER BY execution_time DESC, id DESC
                    LIMIT 200
                    """,
                    (like_pattern,),
                ).fetchall()
            ]
        else:
            symbol_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT symbol, quantity, buy_value, sell_value, realized_pnl,
                           realized_pnl_pct, open_quantity, open_quantity_type,
                           open_value, unrealized_pnl, unrealized_pnl_pct, updated_at
                    FROM console_symbol_pnl
                    ORDER BY ABS(realized_pnl) DESC, symbol ASC
                    """
                ).fetchall()
            ]
            fills_rows = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, trade_id, order_id, symbol, trade_date, execution_time,
                           trade_type, quantity, price, expiry_date, source, created_at
                    FROM console_fills
                    ORDER BY execution_time DESC, id DESC
                    LIMIT 200
                    """
                ).fetchall()
            ]

        total_fills_count = int(
            conn.execute("SELECT COUNT(*) AS cnt FROM console_fills").fetchone()["cnt"]
        )
        reconstructed_trades_count = int(
            conn.execute(
                "SELECT COUNT(*) AS cnt FROM trades_history WHERE kite_trade_id LIKE 'BO:%'"
            ).fetchone()["cnt"]
        )
        unified_summary, ticker_pnl, sync_status = _compute_ticker_pnl_and_unified(
            conn=conn,
            summary=summary,
            cleaned_filter=cleaned_filter,
            kite_connected=kite_connected,
        )
        delivery_adjustments = _fetch_delivery_adjustments(conn, cleaned_filter)

    return {
        "summary": summary,
        "unified_summary": unified_summary,
        "sync_status": sync_status,
        "charges_breakdown": charges_breakdown,
        "ticker_pnl": ticker_pnl,
        "symbol_pnl": symbol_rows,
        "recent_fills": fills_rows,
        "delivery_adjustments": delivery_adjustments,
        "total_fills_count": total_fills_count,
        "reconstructed_trades_count": reconstructed_trades_count,
    }


def _fetch_delivery_adjustments(conn: Any, cleaned_filter: str | None = None) -> list[dict[str, Any]]:
    """Fetch delivery equity adjustment rows, optionally filtered by underlying/contract."""
    if cleaned_filter:
        like_pattern = f"%{cleaned_filter}%"
        rows = conn.execute(
            """
            SELECT id, underlying, fno_contract, fno_strike, fno_expiry, qty,
                   equity_sell_price, equity_sell_date, equity_order_id, equity_trade_ids,
                   charges, economic_pnl, console_fifo_pnl, reason, notes,
                   equity_handoff_status, created_at, updated_at
            FROM delivery_equity_adjustments
            WHERE underlying LIKE ? OR fno_contract LIKE ?
            ORDER BY equity_sell_date DESC, id DESC
            """,
            (like_pattern, like_pattern),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, underlying, fno_contract, fno_strike, fno_expiry, qty,
                   equity_sell_price, equity_sell_date, equity_order_id, equity_trade_ids,
                   charges, economic_pnl, console_fifo_pnl, reason, notes,
                   equity_handoff_status, created_at, updated_at
            FROM delivery_equity_adjustments
            ORDER BY equity_sell_date DESC, id DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def list_delivery_adjustments(
    symbol_filter: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return all recorded delivery equity adjustments."""
    cleaned_filter = symbol_filter.strip().upper() if symbol_filter else None
    with db_session(db_path) as conn:
        return _fetch_delivery_adjustments(conn, cleaned_filter)


def create_delivery_adjustment(
    underlying: str,
    fno_strike: float,
    qty: int,
    equity_sell_price: float,
    equity_sell_date: str,
    fno_contract: str = "",
    fno_expiry: str = "",
    equity_order_id: str = "",
    equity_trade_ids: str = "",
    charges: float = 0.0,
    console_fifo_pnl: float | None = None,
    reason: str = "MISSED_ROLLOVER_DELIVERY",
    notes: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a physical-delivery forced equity exit adjustment (Option A economic P&L)."""
    clean_underlying = underlying.strip().upper()
    if not clean_underlying:
        raise ValueError("underlying is required.")
    if qty <= 0:
        raise ValueError("qty must be greater than 0.")
    if fno_strike <= 0:
        raise ValueError("fno_strike must be greater than 0.")
    if equity_sell_price < 0:
        raise ValueError("equity_sell_price cannot be negative.")
    if charges < 0:
        raise ValueError("charges cannot be negative.")
    clean_date = equity_sell_date.strip()
    if not clean_date:
        raise ValueError("equity_sell_date is required.")

    economic_pnl = round((equity_sell_price - fno_strike) * qty - charges, 2)

    with db_session(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO delivery_equity_adjustments (
                underlying, fno_contract, fno_strike, fno_expiry, qty,
                equity_sell_price, equity_sell_date, equity_order_id, equity_trade_ids,
                charges, economic_pnl, console_fifo_pnl, reason, notes,
                equity_handoff_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'BOOKED_IN_OPTIONS')
            """,
            (
                clean_underlying,
                fno_contract.strip().upper(),
                float(fno_strike),
                fno_expiry.strip(),
                int(qty),
                float(equity_sell_price),
                clean_date,
                equity_order_id.strip(),
                equity_trade_ids.strip(),
                float(charges),
                economic_pnl,
                float(console_fifo_pnl) if console_fifo_pnl is not None else None,
                reason.strip() or "MISSED_ROLLOVER_DELIVERY",
                notes.strip(),
            ),
        )
        row = conn.execute(
            "SELECT * FROM delivery_equity_adjustments WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return dict(row)


def delete_delivery_adjustment(
    adjustment_id: int,
    db_path: str | Path | None = None,
) -> bool:
    """Delete a delivery equity adjustment by ID. Returns True if deleted."""
    with db_session(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM delivery_equity_adjustments WHERE id = ?", (adjustment_id,)
        )
        return cur.rowcount > 0
