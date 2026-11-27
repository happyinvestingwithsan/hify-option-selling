"""Isolated Paper / Strategy Lab simulation engine (Unit U5).

Strictly isolated from live Kite order/GTT placement and cancellation endpoints.
Uses only local SQLite (`paper_trades`) and optional read-only `KiteService.get_quote`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import RulesConfig, load_rules_config
from app.db import db_session
from app.kite_client import KiteService, calculate_decay_pct, calculate_spread_pct

ACTIVE_PAPER_STATUSES = ("OPEN", "ATO_WAITING")


class PaperLabError(Exception):
    """Structured exception raised on invalid Paper Lab operation or guardrail violation."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class PaperTradeCreateRequest(BaseModel):
    """Request payload for creating a simulated trade in Paper Lab."""

    symbol: str = Field(..., min_length=1)
    strike: float = Field(..., ge=0.0)
    option_type: Literal["PE", "CE", "FUT"] = "PE"
    expiry: str = Field(..., min_length=1)
    side: Literal["SELL", "BUY"] = "SELL"
    qty: int = Field(..., gt=0)
    lot_size: int = Field(default=1, gt=0)
    order_type: str = "LIMIT"
    limit_price: float = Field(..., gt=0.0)
    bid_price: float | None = Field(default=None, ge=0.0)
    ask_price: float | None = Field(default=None, ge=0.0)
    spread_pct: float | None = Field(default=None, ge=0.0)
    margin_blocked: float = Field(default=0.0, ge=0.0)
    decay_target_pct: float | None = Field(default=None, gt=0.0, le=100.0)
    ato_trigger_price: float | None = Field(default=None, gt=0.0)
    ato_already_triggered: bool = False
    is_hedged: bool = False
    is_covered_call: bool = False
    strategy_tag: str = "WHEEL_PE"
    notes: str = ""


class PaperSimulateTickRequest(BaseModel):
    """Request payload for simulating ATO trigger and premium decay."""

    simulated_spot_price: float | None = Field(default=None, gt=0.0)
    simulated_option_price: float | None = Field(default=None, ge=0.0)
    days_held: int = Field(default=15, ge=0)
    use_live_quote: bool = False
    quote_instrument: str | None = None
    auto_book_on_target: bool = False


class PaperRolloverRequest(BaseModel):
    """Request payload for simulating a Same-Strike Rollover or Far-Future pivot."""

    new_expiry: str = Field(..., min_length=1)
    new_strike: float | None = Field(default=None, ge=0.0)
    new_entry_price: float = Field(..., gt=0.0)
    close_current_price: float = Field(..., ge=0.0)
    pivot_to_far_future: bool = False
    bid_price: float | None = Field(default=None, ge=0.0)
    ask_price: float | None = Field(default=None, ge=0.0)
    spread_pct: float | None = Field(default=None, ge=0.0)
    margin_blocked: float | None = Field(default=None, ge=0.0)
    notes: str = ""


class PaperCloseRequest(BaseModel):
    """Request payload for closing a simulated paper trade."""

    exit_price: float = Field(..., ge=0.0)
    exit_reason: str = ""
    override_reason: str = ""


class PaperLabSummary(BaseModel):
    """Summary metrics for simulated Paper Lab trades."""

    total_trades: int
    open_count: int
    ato_waiting_count: int
    closed_count: int
    rolled_count: int
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    win_rate_pct: float


def _row_to_trade_dict(row: Any) -> dict[str, Any]:
    """Convert SQLite Row from paper_trades into a JSON-serializable dict."""
    data = dict(row)
    for bool_col in ("is_ato_triggered", "is_hedged", "is_covered_call", "target_hit", "closed_before_target"):
        if bool_col in data:
            data[bool_col] = bool(data[bool_col])
    return data


def _compute_pnl(entry_price: float, exit_or_current_price: float, qty: int, side: str) -> float:
    """Compute simulated P&L for SELL or BUY position."""
    if side == "SELL":
        return round((entry_price - exit_or_current_price) * qty, 2)
    return round((exit_or_current_price - entry_price) * qty, 2)


def _resolve_spread_pct(
    bid_price: float | None,
    ask_price: float | None,
    spread_pct: float | None,
) -> float | None:
    """Compute spread percentage from bid/ask when available, else use explicit spread_pct."""
    if bid_price is not None and ask_price is not None:
        return calculate_spread_pct(bid_price, ask_price)
    return spread_pct


def _validate_spread(
    option_type: str,
    bid_price: float | None,
    ask_price: float | None,
    spread_pct: float | None,
    rules: RulesConfig,
) -> float | None:
    """Reject illiquid contracts exceeding rulebook Bid-Ask spread limits."""
    resolved = _resolve_spread_pct(bid_price, ask_price, spread_pct)
    if resolved is None:
        return None
    max_allowed = (
        rules.entry_triggers.max_future_bid_ask_spread_pct
        if option_type == "FUT"
        else rules.entry_triggers.max_option_bid_ask_spread_pct
    )
    if resolved > max_allowed:
        raise PaperLabError(
            code="SPREAD_TOO_WIDE",
            message=f"Bid-Ask spread {resolved}% exceeds max allowed {max_allowed}% for {option_type}.",
            details={"spread_pct": resolved, "max_allowed_pct": max_allowed, "option_type": option_type},
        )
    return resolved


def _resolve_effective_decay_target(days_held: int, base_target_pct: float, rules: RulesConfig) -> float:
    """Resolve Decay Lock target percentage based on holding duration and rulebook tiers."""
    decay_rules = rules.profit_booking_decay_pct
    if days_held <= 1:
        return float(decay_rules.intraday_1_day)
    if days_held <= 3:
        return float(decay_rules.fast_2_to_3_days)
    if days_held >= 20:
        return float(decay_rules.expiry_week_min)
    return float(base_target_pct)


def list_paper_trades(
    status: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """List simulated trades from `paper_trades` along with summary statistics."""
    with db_session(db_path) as conn:
        all_rows = conn.execute(
            "SELECT * FROM paper_trades ORDER BY id DESC"
        ).fetchall()
        if status:
            normalized = status.strip().upper()
            filtered_rows = [r for r in all_rows if r["status"] == normalized]
        else:
            filtered_rows = all_rows

    all_trades = [_row_to_trade_dict(r) for r in all_rows]
    trades = [_row_to_trade_dict(r) for r in filtered_rows]

    open_count = 0
    ato_waiting_count = 0
    closed_count = 0
    rolled_count = 0
    realized_pnl = 0.0
    unrealized_pnl = 0.0
    finished_count = 0
    winning_count = 0

    for t in all_trades:
        st = t["status"]
        if st == "OPEN":
            open_count += 1
            unrealized_pnl += _compute_pnl(
                float(t["entry_price"]),
                float(t["current_price"]),
                int(t["qty"]),
                str(t["side"]),
            )
        elif st == "ATO_WAITING":
            ato_waiting_count += 1
        elif st in ("CLOSED", "ROLLED"):
            if st == "CLOSED":
                closed_count += 1
            else:
                rolled_count += 1
            pnl_val = float(t["pnl"])
            realized_pnl += pnl_val
            finished_count += 1
            if pnl_val > 0:
                winning_count += 1

    realized_pnl = round(realized_pnl, 2)
    unrealized_pnl = round(unrealized_pnl, 2)
    win_rate_pct = round((winning_count / finished_count) * 100.0, 2) if finished_count > 0 else 0.0

    summary = PaperLabSummary(
        total_trades=len(all_trades),
        open_count=open_count,
        ato_waiting_count=ato_waiting_count,
        closed_count=closed_count,
        rolled_count=rolled_count,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        total_pnl=round(realized_pnl + unrealized_pnl, 2),
        win_rate_pct=win_rate_pct,
    )

    return {
        "count": len(trades),
        "trades": trades,
        "summary": summary.model_dump(),
    }


def create_paper_trade(
    req: PaperTradeCreateRequest,
    rules: RulesConfig | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate strategy rules and insert a simulated trade into `paper_trades`."""
    active_rules = rules or load_rules_config()
    order_type = req.order_type.strip().upper()
    if order_type != "LIMIT":
        raise PaperLabError(
            code="MARKET_ORDER_BLOCKED",
            message="Paper Lab enforces LIMIT orders only; MARKET orders are blocked.",
            details={"order_type": req.order_type},
        )

    _validate_spread(
        option_type=req.option_type,
        bid_price=req.bid_price,
        ask_price=req.ask_price,
        spread_pct=req.spread_pct,
        rules=active_rules,
    )

    if req.option_type == "CE" and req.side == "SELL" and not req.is_covered_call:
        raise PaperLabError(
            code="NAKED_CALL_BLOCKED",
            message="Naked Call selling is forbidden; CE SELL requires is_covered_call=True.",
            details={"symbol": req.symbol, "option_type": req.option_type, "side": req.side},
        )

    with db_session(db_path) as conn:
        active_rows = conn.execute(
            "SELECT id, is_hedged FROM paper_trades WHERE status IN ('OPEN', 'ATO_WAITING')"
        ).fetchall()
        active_total = len(active_rows)
        active_naked = sum(1 for r in active_rows if int(r["is_hedged"]) == 0)

        max_naked = active_rules.capital.max_naked_positions
        max_hedged = active_rules.capital.max_hedged_positions

        if not req.is_hedged and active_naked >= max_naked:
            raise PaperLabError(
                code="AUKAAT_NAKED_CAP_EXCEEDED",
                message=f"Paper Lab Aukaat cap reached: max {max_naked} naked positions allowed.",
                details={"active_naked": active_naked, "max_naked_positions": max_naked},
            )
        if active_total >= max_hedged:
            raise PaperLabError(
                code="AUKAAT_HEDGED_CAP_EXCEEDED",
                message=f"Paper Lab Aukaat cap reached: max {max_hedged} total positions allowed.",
                details={"active_total": active_total, "max_hedged_positions": max_hedged},
            )

        ppm_pct = (
            round(((req.limit_price * req.qty) / req.margin_blocked) * 100.0, 2)
            if req.margin_blocked > 0
            else 0.0
        )
        decay_target = (
            float(req.decay_target_pct)
            if req.decay_target_pct is not None
            else float(active_rules.profit_booking_decay_pct.mid_month_gtt)
        )

        is_waiting = req.ato_trigger_price is not None and not req.ato_already_triggered
        status = "ATO_WAITING" if is_waiting else "OPEN"
        is_ato_triggered = 0 if is_waiting else 1

        cursor = conn.execute(
            """
            INSERT INTO paper_trades (
                symbol, strike, option_type, expiry, side, qty, lot_size,
                entry_price, current_price, decay_pct, decay_target_pct,
                margin_blocked, ppm_pct, ato_trigger_price, is_ato_triggered,
                is_hedged, is_covered_call, status, strategy_tag, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                req.symbol.strip().upper(),
                req.strike,
                req.option_type,
                req.expiry.strip().upper(),
                req.side,
                req.qty,
                req.lot_size,
                req.limit_price,
                req.limit_price,
                0.0,
                decay_target,
                req.margin_blocked,
                ppm_pct,
                req.ato_trigger_price,
                is_ato_triggered,
                1 if req.is_hedged else 0,
                1 if req.is_covered_call else 0,
                status,
                req.strategy_tag.strip(),
                req.notes,
            ),
        )
        trade_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,)).fetchone()

    return _row_to_trade_dict(row)


def simulate_ato_and_decay(
    trade_id: int,
    req: PaperSimulateTickRequest,
    rules: RulesConfig | None = None,
    kite_service: KiteService | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Simulate ATO trigger activation, premium decay, and optional target auto-booking."""
    active_rules = rules or load_rules_config()

    with db_session(db_path) as conn:
        row = conn.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,)).fetchone()
        if row is None:
            raise PaperLabError(
                code="PAPER_TRADE_NOT_FOUND",
                message=f"Paper trade {trade_id} not found.",
                status_code=404,
            )

        trade = _row_to_trade_dict(row)
        if trade["status"] in ("CLOSED", "ROLLED"):
            raise PaperLabError(
                code="PAPER_TRADE_NOT_ACTIVE",
                message=f"Cannot simulate trade {trade_id} in status {trade['status']}.",
                details={"status": trade["status"]},
            )

        sim_option_price = req.simulated_option_price
        quote_used: dict[str, Any] | None = None
        if req.use_live_quote and sim_option_price is None:
            service = kite_service or KiteService(db_path=db_path)
            inst = req.quote_instrument or f"NFO:{trade['symbol']}{trade['expiry']}{int(trade['strike'])}{trade['option_type']}"
            quote_resp = service.get_quote([inst])
            quote_data = quote_resp.get("quotes", {}).get(inst)
            if quote_data:
                sim_option_price = float(quote_data.get("last_price", trade["current_price"]))
                quote_used = quote_data

        ato_triggered_now = False
        new_status = trade["status"]
        is_ato_triggered = 1 if trade["is_ato_triggered"] else 0

        if new_status == "ATO_WAITING":
            trigger_price = trade.get("ato_trigger_price")
            hit = False
            if trigger_price is None:
                hit = True
            elif trade["side"] == "SELL" and trade["option_type"] == "PE":
                if req.simulated_spot_price is not None and req.simulated_spot_price <= float(trigger_price):
                    hit = True
                elif sim_option_price is not None and sim_option_price >= float(trigger_price):
                    hit = True
            else:
                if req.simulated_spot_price is not None and req.simulated_spot_price >= float(trigger_price):
                    hit = True
                elif sim_option_price is not None and sim_option_price <= float(trigger_price):
                    hit = True

            if hit:
                new_status = "OPEN"
                is_ato_triggered = 1
                ato_triggered_now = True

        current_price = float(sim_option_price) if sim_option_price is not None else float(trade["current_price"])
        entry_price = float(trade["entry_price"])
        qty = int(trade["qty"])
        side = str(trade["side"])

        effective_target_pct = _resolve_effective_decay_target(
            days_held=req.days_held,
            base_target_pct=float(trade["decay_target_pct"]),
            rules=active_rules,
        )

        if new_status == "OPEN":
            current_decay_pct = calculate_decay_pct(entry_price, current_price, side)
            pnl = _compute_pnl(entry_price, current_price, qty, side)
            target_hit = current_decay_pct >= effective_target_pct
        else:
            current_decay_pct = 0.0
            pnl = 0.0
            target_hit = False

        auto_booked = False
        if new_status == "OPEN" and target_hit and req.auto_book_on_target:
            auto_booked = True
            conn.execute(
                """
                UPDATE paper_trades
                SET status = 'CLOSED',
                    is_ato_triggered = ?,
                    current_price = ?,
                    exit_price = ?,
                    decay_pct = ?,
                    target_hit = 1,
                    closed_before_target = 0,
                    exit_reason = 'DECAY_TARGET_HIT',
                    pnl = ?,
                    closed_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (is_ato_triggered, current_price, current_price, current_decay_pct, pnl, trade_id),
            )
        else:
            conn.execute(
                """
                UPDATE paper_trades
                SET status = ?,
                    is_ato_triggered = ?,
                    current_price = ?,
                    decay_pct = ?,
                    target_hit = ?,
                    pnl = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    new_status,
                    is_ato_triggered,
                    current_price,
                    current_decay_pct,
                    1 if target_hit else 0,
                    pnl,
                    trade_id,
                ),
            )

        updated_row = conn.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,)).fetchone()

    return {
        "trade": _row_to_trade_dict(updated_row),
        "ato_triggered_now": ato_triggered_now,
        "effective_target_pct": effective_target_pct,
        "current_decay_pct": current_decay_pct,
        "target_hit": target_hit,
        "auto_booked": auto_booked,
        "quote_used": quote_used,
    }


def simulate_same_strike_rollover(
    trade_id: int,
    req: PaperRolloverRequest,
    rules: RulesConfig | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Simulate Same-Strike Rollover (blocking roll-down) or Far-Month Future pivot in SQLite."""
    active_rules = rules or load_rules_config()

    with db_session(db_path) as conn:
        row = conn.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,)).fetchone()
        if row is None:
            raise PaperLabError(
                code="PAPER_TRADE_NOT_FOUND",
                message=f"Paper trade {trade_id} not found.",
                status_code=404,
            )

        trade = _row_to_trade_dict(row)
        if trade["status"] != "OPEN":
            raise PaperLabError(
                code="PAPER_TRADE_NOT_OPEN",
                message=f"Only OPEN paper trades can be rolled over (current: {trade['status']}).",
                details={"status": trade["status"]},
            )

        old_strike = float(trade["strike"])
        new_strike = float(req.new_strike) if req.new_strike is not None else old_strike

        if (
            not req.pivot_to_far_future
            and new_strike < old_strike
            and not active_rules.rollover.allow_roll_down_strike
        ):
            raise PaperLabError(
                code="ROLLOVER_STRIKE_DOWN_BLOCKED",
                message=(
                    f"Same-Strike Rollover Lock: rolling down from {old_strike} to {new_strike} is blocked. "
                    "Keep exact same strike or set pivot_to_far_future=True."
                ),
                details={"old_strike": old_strike, "new_strike": new_strike},
            )

        next_option_type = "FUT" if req.pivot_to_far_future else str(trade["option_type"])
        _validate_spread(
            option_type=next_option_type,
            bid_price=req.bid_price,
            ask_price=req.ask_price,
            spread_pct=req.spread_pct,
            rules=active_rules,
        )

        old_entry = float(trade["entry_price"])
        qty = int(trade["qty"])
        old_side = str(trade["side"])
        close_decay = calculate_decay_pct(old_entry, req.close_current_price, old_side)
        close_pnl = _compute_pnl(old_entry, req.close_current_price, qty, old_side)
        close_reason = "PIVOT_TO_FAR_FUTURE" if req.pivot_to_far_future else "ROLLED_SAME_STRIKE"

        conn.execute(
            """
            UPDATE paper_trades
            SET status = 'ROLLED',
                current_price = ?,
                exit_price = ?,
                decay_pct = ?,
                pnl = ?,
                exit_reason = ?,
                closed_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (req.close_current_price, req.close_current_price, close_decay, close_pnl, close_reason, trade_id),
        )

        next_side = "BUY" if req.pivot_to_far_future else old_side
        next_strike = 0.0 if req.pivot_to_far_future else new_strike
        next_margin = float(req.margin_blocked) if req.margin_blocked is not None else float(trade["margin_blocked"])
        next_ppm = round(((req.new_entry_price * qty) / next_margin) * 100.0, 2) if next_margin > 0 else 0.0
        next_tag = "FAR_FUTURE_PIVOT" if req.pivot_to_far_future else str(trade["strategy_tag"])

        cursor = conn.execute(
            """
            INSERT INTO paper_trades (
                symbol, strike, option_type, expiry, side, qty, lot_size,
                entry_price, current_price, decay_pct, decay_target_pct,
                margin_blocked, ppm_pct, is_ato_triggered, is_hedged,
                is_covered_call, rollover_from_id, status, strategy_tag, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, ?, ?, 1, ?, ?, ?, 'OPEN', ?, ?)
            """,
            (
                trade["symbol"],
                next_strike,
                next_option_type,
                req.new_expiry.strip().upper(),
                next_side,
                qty,
                int(trade["lot_size"]),
                req.new_entry_price,
                req.new_entry_price,
                float(trade["decay_target_pct"]),
                next_margin,
                next_ppm,
                1 if trade["is_hedged"] else 0,
                1 if trade["is_covered_call"] else 0,
                trade_id,
                next_tag,
                req.notes or f"Rolled from trade #{trade_id}",
            ),
        )
        new_id = cursor.lastrowid
        closed_row = conn.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,)).fetchone()
        new_row = conn.execute("SELECT * FROM paper_trades WHERE id = ?", (new_id,)).fetchone()

    return {
        "closed_leg": _row_to_trade_dict(closed_row),
        "new_leg": _row_to_trade_dict(new_row),
        "pivot_to_far_future": req.pivot_to_far_future,
    }


def close_paper_trade(
    trade_id: int,
    req: PaperCloseRequest,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Close a simulated paper trade and record realized P&L, decay %, and early-exit flag."""
    with db_session(db_path) as conn:
        row = conn.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,)).fetchone()
        if row is None:
            raise PaperLabError(
                code="PAPER_TRADE_NOT_FOUND",
                message=f"Paper trade {trade_id} not found.",
                status_code=404,
            )

        trade = _row_to_trade_dict(row)
        if trade["status"] in ("CLOSED", "ROLLED"):
            raise PaperLabError(
                code="PAPER_TRADE_ALREADY_CLOSED",
                message=f"Paper trade {trade_id} is already {trade['status']}.",
                details={"status": trade["status"]},
            )

        entry_price = float(trade["entry_price"])
        qty = int(trade["qty"])
        side = str(trade["side"])
        decay_pct = (
            calculate_decay_pct(entry_price, req.exit_price, side)
            if trade["status"] == "OPEN"
            else 0.0
        )
        realized_pnl = (
            _compute_pnl(entry_price, req.exit_price, qty, side)
            if trade["status"] == "OPEN"
            else 0.0
        )
        closed_before_target = 1 if (trade["status"] == "OPEN" and decay_pct < float(trade["decay_target_pct"])) else 0
        exit_reason = req.exit_reason.strip() or (
            "EARLY_EXIT_OVERRIDE" if closed_before_target else "DECAY_TARGET_BOOKED"
        )
        notes = trade["notes"]
        if req.override_reason.strip():
            notes = f"{notes} | Override: {req.override_reason.strip()}".strip(" |")

        conn.execute(
            """
            UPDATE paper_trades
            SET status = 'CLOSED',
                current_price = ?,
                exit_price = ?,
                decay_pct = ?,
                target_hit = ?,
                closed_before_target = ?,
                exit_reason = ?,
                notes = ?,
                pnl = ?,
                closed_at = datetime('now'),
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                req.exit_price,
                req.exit_price,
                decay_pct,
                1 if not closed_before_target and trade["status"] == "OPEN" else 0,
                closed_before_target,
                exit_reason,
                notes,
                realized_pnl,
                trade_id,
            ),
        )
        updated_row = conn.execute("SELECT * FROM paper_trades WHERE id = ?", (trade_id,)).fetchone()

    return {
        "trade": _row_to_trade_dict(updated_row),
        "realized_pnl": realized_pnl,
        "decay_pct": decay_pct,
        "closed_before_target": bool(closed_before_target),
    }
