"""ATO / GTT Staging & Hard Strategy Guardrails Engine (Unit U4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import RulesConfig, load_rules_config
from app.db import db_session
from app.kite_client import KiteService, calculate_spread_pct

ACTIVE_STAGED_STATUSES = ("STAGED", "PENDING", "APPROVED", "APPROVED_DRY_RUN")
KILL_SWITCH_TARGET_STATUSES = ("STAGED", "PENDING", "APPROVED", "APPROVED_DRY_RUN")


class GuardrailViolationError(Exception):
    """Structured exception raised when a hard strategy guardrail is violated."""

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


class OrderStageRequest(BaseModel):
    """Request payload for staging a Limit-only ATO/GTT order."""

    symbol: str = Field(..., min_length=1)
    strike: float = Field(..., ge=0.0)
    option_type: Literal["PE", "CE", "FUT"] = "PE"
    expiry: str = Field(..., min_length=1)
    side: Literal["SELL", "BUY"] = "SELL"
    qty: int = Field(..., gt=0)
    order_type: str = "LIMIT"
    limit_price: float = Field(..., gt=0.0)
    bid_price: float | None = Field(default=None, ge=0.0)
    ask_price: float | None = Field(default=None, ge=0.0)
    spread_pct: float | None = Field(default=None, ge=0.0)
    gtt_target_price: float | None = Field(default=None, gt=0.0)
    gtt_decay_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    is_hedged: bool = False
    is_covered_call: bool = False
    override_reason: str = ""


class ApproveOrderRequest(BaseModel):
    """Explicit manual approval payload for a staged order."""

    confirm_manual_approval: bool = False
    execute_live: bool = False


class RolloverStageRequest(BaseModel):
    """Request payload for Same-Strike Rollover or Far-Month Future pivot."""

    symbol: str = Field(..., min_length=1)
    old_strike: float = Field(..., gt=0.0)
    new_strike: float = Field(..., ge=0.0)
    option_type: Literal["PE", "CE", "FUT"] = "PE"
    new_expiry: str = Field(..., min_length=1)
    side: Literal["SELL", "BUY"] = "SELL"
    qty: int = Field(..., gt=0)
    order_type: str = "LIMIT"
    limit_price: float = Field(..., gt=0.0)
    bid_price: float | None = Field(default=None, ge=0.0)
    ask_price: float | None = Field(default=None, ge=0.0)
    spread_pct: float | None = Field(default=None, ge=0.0)
    pivot_to_far_future: bool = False
    is_hedged: bool = False
    is_covered_call: bool = False
    gtt_target_price: float | None = Field(default=None, gt=0.0)
    gtt_decay_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class DecayCheckRequest(BaseModel):
    """Request payload for Decay Lock evaluation and optional override logging."""

    days_held: int = Field(..., ge=0)
    decay_pct: float = Field(..., le=100.0)
    is_expiry_week: bool = False
    override_reason: str | None = None
    position_id: int | None = None


class DecayLockResult(BaseModel):
    """Structured result of a Decay Lock check."""

    locked: bool
    requires_override: bool
    allowed: bool
    required_target_pct: float
    decay_pct: float
    days_held: int
    is_expiry_week: bool
    tier_label: str
    override_logged: bool = False
    message: str


class KillSwitchRequest(BaseModel):
    """Explicit confirmation payload for triggering the Kill Switch."""

    confirm_kill: bool = False


def _resolve_spread_pct(
    bid_price: float | None,
    ask_price: float | None,
    spread_pct: float | None,
) -> float | None:
    """Resolve spread percentage from explicit value or bid/ask quotes."""
    if spread_pct is not None:
        return round(spread_pct, 2)
    if bid_price is not None and ask_price is not None:
        if bid_price > ask_price:
            raise GuardrailViolationError(
                code="INVALID_QUOTES",
                message="bid_price cannot exceed ask_price.",
                details={"bid_price": bid_price, "ask_price": ask_price},
            )
        return calculate_spread_pct(bid_price, ask_price)
    return None


def get_aukaat_counts(db_path: str | Path | None = None) -> dict[str, int]:
    """Count open positions and active staged orders for ₹25L Aukaat enforcement."""
    placeholders = ",".join("?" for _ in ACTIVE_STAGED_STATUSES)
    with db_session(db_path) as conn:
        pos_row = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN is_hedged = 0 THEN 1 ELSE 0 END), 0) AS naked_positions,
                COALESCE(SUM(CASE WHEN is_hedged = 1 THEN 1 ELSE 0 END), 0) AS hedged_positions,
                COUNT(*) AS total_positions
            FROM positions
            WHERE status = 'OPEN'
            """
        ).fetchone()
        staged_row = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(CASE WHEN is_hedged = 0 THEN 1 ELSE 0 END), 0) AS naked_staged,
                COALESCE(SUM(CASE WHEN is_hedged = 1 THEN 1 ELSE 0 END), 0) AS hedged_staged,
                COUNT(*) AS total_staged
            FROM staged_orders
            WHERE status IN ({placeholders})
            """,
            ACTIVE_STAGED_STATUSES,
        ).fetchone()

    naked_count = int(pos_row["naked_positions"]) + int(staged_row["naked_staged"])
    hedged_count = int(pos_row["hedged_positions"]) + int(staged_row["hedged_staged"])
    total_count = int(pos_row["total_positions"]) + int(staged_row["total_staged"])
    return {
        "naked_count": naked_count,
        "hedged_count": hedged_count,
        "total_count": total_count,
    }


def validate_order_request(
    request: OrderStageRequest,
    rules: RulesConfig | None = None,
    db_path: str | Path | None = None,
    skip_aukaat_check: bool = False,
) -> float | None:
    """Validate an order against all hard strategy guardrails. Returns resolved spread_pct."""
    cfg = rules or load_rules_config()

    # 1. Limit Orders Only (never MARKET)
    if request.order_type.strip().upper() != "LIMIT":
        raise GuardrailViolationError(
            code="LIMIT_ONLY",
            message="Only LIMIT orders are permitted. MARKET orders are strictly blocked.",
            details={"order_type": request.order_type},
        )

    # 2. 5% Bid-Ask Spread Rule (1.5% for Futures)
    resolved_spread = _resolve_spread_pct(request.bid_price, request.ask_price, request.spread_pct)
    max_spread = (
        cfg.entry_triggers.max_future_bid_ask_spread_pct
        if request.option_type == "FUT"
        else cfg.entry_triggers.max_option_bid_ask_spread_pct
    )
    if resolved_spread is not None and resolved_spread > max_spread:
        raise GuardrailViolationError(
            code="SPREAD_TOO_WIDE",
            message=(
                f"Bid-Ask spread {resolved_spread:.2f}% exceeds maximum allowed "
                f"{max_spread:.2f}% for {request.option_type}."
            ),
            details={
                "spread_pct": resolved_spread,
                "max_spread_pct": max_spread,
                "option_type": request.option_type,
            },
        )

    # 3. No Naked Calls
    if request.option_type == "CE" and request.side == "SELL" and not request.is_covered_call:
        raise GuardrailViolationError(
            code="NAKED_CALL_FORBIDDEN",
            message="Naked Call selling is forbidden. Calls may only be sold as Covered Calls.",
            details={"symbol": request.symbol, "option_type": request.option_type, "side": request.side},
        )

    # 4. ₹25L Aukaat Cap
    if not skip_aukaat_check:
        counts = get_aukaat_counts(db_path=db_path)
        if not request.is_hedged and counts["naked_count"] >= cfg.capital.max_naked_positions:
            raise GuardrailViolationError(
                code="AUKAAT_NAKED_CAP_EXCEEDED",
                message=(
                    f"₹25L Aukaat cap reached: {counts['naked_count']}/{cfg.capital.max_naked_positions} "
                    "naked positions/staged orders active."
                ),
                details={**counts, "max_naked_positions": cfg.capital.max_naked_positions},
            )
        if counts["total_count"] >= cfg.capital.max_hedged_positions:
            raise GuardrailViolationError(
                code="AUKAAT_HEDGED_CAP_EXCEEDED",
                message=(
                    f"₹25L Aukaat cap reached: {counts['total_count']}/{cfg.capital.max_hedged_positions} "
                    "total positions/staged orders active."
                ),
                details={**counts, "max_hedged_positions": cfg.capital.max_hedged_positions},
            )

    return resolved_spread


def validate_rollover_request(
    old_strike: float,
    new_strike: float,
    pivot_to_far_future: bool,
    rules: RulesConfig | None = None,
) -> None:
    """Enforce Same-Strike Rollover Lock (never roll down a Put strike)."""
    cfg = rules or load_rules_config()
    if pivot_to_far_future:
        if not cfg.rollover.pivot_to_far_future_if_illiquid:
            raise GuardrailViolationError(
                code="FAR_FUTURE_PIVOT_DISABLED",
                message="Far-Month Future pivot is disabled in rules config.",
            )
        return

    if not cfg.rollover.allow_roll_down_strike and new_strike < old_strike:
        raise GuardrailViolationError(
            code="ROLL_DOWN_STRIKE_FORBIDDEN",
            message=(
                f"Same-Strike Rollover Lock: cannot roll down from {old_strike} to {new_strike}. "
                "Keep the exact same strike or pivot to Far-Month Futures."
            ),
            details={"old_strike": old_strike, "new_strike": new_strike},
        )


def check_decay_lock(
    days_held: int,
    decay_pct: float,
    is_expiry_week: bool,
    override_reason: str | None,
    rules: RulesConfig | None = None,
    db_path: str | Path | None = None,
    position_id: int | None = None,
) -> DecayLockResult:
    """Check Decay Lock profit-booking targets and log overrides to lessons_log."""
    cfg = rules or load_rules_config()
    targets = cfg.profit_booking_decay_pct

    if is_expiry_week:
        required_target = targets.expiry_week_min
        tier_label = "EXPIRY_WEEK"
    elif days_held <= 1:
        required_target = targets.intraday_1_day
        tier_label = "INTRADAY_1_DAY"
    elif days_held <= 3:
        required_target = targets.fast_2_to_3_days
        tier_label = "FAST_2_TO_3_DAYS"
    else:
        required_target = targets.mid_month_gtt
        tier_label = "MID_MONTH_GTT"

    if decay_pct >= required_target:
        return DecayLockResult(
            locked=False,
            requires_override=False,
            allowed=True,
            required_target_pct=required_target,
            decay_pct=decay_pct,
            days_held=days_held,
            is_expiry_week=is_expiry_week,
            tier_label=tier_label,
            override_logged=False,
            message=f"Decay target met ({decay_pct:.1f}% >= {required_target:.1f}%). Muh Meetha Karo!",
        )

    cleaned_reason = (override_reason or "").strip()
    if not cleaned_reason:
        return DecayLockResult(
            locked=True,
            requires_override=True,
            allowed=False,
            required_target_pct=required_target,
            decay_pct=decay_pct,
            days_held=days_held,
            is_expiry_week=is_expiry_week,
            tier_label=tier_label,
            override_logged=False,
            message=(
                f"Decay Lock active: {decay_pct:.1f}% < {required_target:.1f}% target ({tier_label}). "
                "Provide an override_reason to log early exit."
            ),
        )

    with db_session(db_path) as conn:
        conn.execute(
            """
            INSERT INTO lessons_log (category, title, description, mistake_type, rule_added, position_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "DECAY_OVERRIDE",
                f"Early Exit Override ({tier_label}: {decay_pct:.1f}% vs {required_target:.1f}%)",
                cleaned_reason,
                "EARLY_EXIT",
                f"Wait for {required_target:.1f}% decay in {tier_label}",
                position_id,
            ),
        )

    return DecayLockResult(
        locked=False,
        requires_override=False,
        allowed=True,
        required_target_pct=required_target,
        decay_pct=decay_pct,
        days_held=days_held,
        is_expiry_week=is_expiry_week,
        tier_label=tier_label,
        override_logged=True,
        message=f"Decay Lock overridden and logged to lessons_log ({decay_pct:.1f}% < {required_target:.1f}%).",
    )


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def list_staged_orders(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return all staged orders ordered by newest first."""
    with db_session(db_path) as conn:
        rows = conn.execute("SELECT * FROM staged_orders ORDER BY id DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def stage_ato_gtt_order(
    request: OrderStageRequest,
    rules: RulesConfig | None = None,
    db_path: str | Path | None = None,
    skip_aukaat_check: bool = False,
) -> dict[str, Any]:
    """Validate all guardrails and insert a LIMIT-only staged order (never auto-fires live)."""
    resolved_spread = validate_order_request(
        request=request,
        rules=rules,
        db_path=db_path,
        skip_aukaat_check=skip_aukaat_check,
    )
    symbol = request.symbol.strip().upper()
    expiry = request.expiry.strip().upper()

    with db_session(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO staged_orders (
                symbol, strike, option_type, expiry, side, qty, order_type,
                limit_price, bid_price, ask_price, spread_pct, gtt_target_price,
                gtt_decay_pct, is_hedged, status, guardrail_passed, override_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, 'LIMIT', ?, ?, ?, ?, ?, ?, ?, 'STAGED', 1, ?)
            """,
            (
                symbol,
                request.strike,
                request.option_type,
                expiry,
                request.side,
                request.qty,
                request.limit_price,
                request.bid_price,
                request.ask_price,
                resolved_spread,
                request.gtt_target_price,
                request.gtt_decay_pct,
                1 if request.is_hedged else 0,
                request.override_reason.strip(),
            ),
        )
        order_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM staged_orders WHERE id = ?", (order_id,)).fetchone()
    return _row_to_dict(row)


def stage_rollover_order(
    request: RolloverStageRequest,
    rules: RulesConfig | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate Same-Strike Rollover Lock + order guardrails and stage rollover order."""
    validate_rollover_request(
        old_strike=request.old_strike,
        new_strike=request.new_strike,
        pivot_to_far_future=request.pivot_to_far_future,
        rules=rules,
    )

    target_option_type: Literal["PE", "CE", "FUT"] = "FUT" if request.pivot_to_far_future else request.option_type
    target_strike = 0.0 if request.pivot_to_far_future else request.new_strike
    target_side: Literal["SELL", "BUY"] = "BUY" if request.pivot_to_far_future else request.side

    stage_req = OrderStageRequest(
        symbol=request.symbol,
        strike=target_strike,
        option_type=target_option_type,
        expiry=request.new_expiry,
        side=target_side,
        qty=request.qty,
        order_type=request.order_type,
        limit_price=request.limit_price,
        bid_price=request.bid_price,
        ask_price=request.ask_price,
        spread_pct=request.spread_pct,
        gtt_target_price=request.gtt_target_price,
        gtt_decay_pct=request.gtt_decay_pct,
        is_hedged=request.is_hedged,
        is_covered_call=request.is_covered_call,
        override_reason=f"ROLLOVER_FROM_{request.old_strike}",
    )
    return stage_ato_gtt_order(
        request=stage_req,
        rules=rules,
        db_path=db_path,
        skip_aukaat_check=True,
    )


def approve_staged_order(
    order_id: int,
    confirm_manual_approval: bool,
    execute_live: bool = False,
    kite_service: KiteService | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Require explicit manual approval; mark APPROVED_DRY_RUN or prepare Kite payload."""
    if not confirm_manual_approval:
        raise GuardrailViolationError(
            code="MANUAL_APPROVAL_REQUIRED",
            message="Explicit confirm_manual_approval=True is required to approve a staged order.",
            details={"order_id": order_id},
        )

    with db_session(db_path) as conn:
        row = conn.execute("SELECT * FROM staged_orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise GuardrailViolationError(
                code="ORDER_NOT_FOUND",
                message=f"Staged order {order_id} not found.",
                details={"order_id": order_id},
                status_code=404,
            )

        order = _row_to_dict(row)
        if order["status"] not in ("STAGED", "PENDING"):
            raise GuardrailViolationError(
                code="INVALID_ORDER_STATE",
                message=f"Order {order_id} cannot be approved from status '{order['status']}'.",
                details={"order_id": order_id, "status": order["status"]},
            )

        is_live = bool(execute_live and kite_service is not None and kite_service._is_live())
        new_status = "APPROVED" if is_live else "APPROVED_DRY_RUN"

        conn.execute(
            "UPDATE staged_orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (new_status, order_id),
        )
        updated = conn.execute("SELECT * FROM staged_orders WHERE id = ?", (order_id,)).fetchone()

    result = _row_to_dict(updated)
    tradingsymbol = (
        f"{result['symbol']}{result['expiry']}FUT"
        if result["option_type"] == "FUT"
        else f"{result['symbol']}{result['expiry']}{int(result['strike']) if float(result['strike']).is_integer() else result['strike']}{result['option_type']}"
    )
    kite_payload = {
        "exchange": "NFO",
        "tradingsymbol": tradingsymbol,
        "transaction_type": result["side"],
        "quantity": result["qty"],
        "order_type": "LIMIT",
        "price": result["limit_price"],
        "product": "NRML",
        "gtt_target_price": result["gtt_target_price"],
    }
    return {
        "order": result,
        "mode": "LIVE_PREPARED" if is_live else "DRY_RUN",
        "auto_fired": False,
        "kite_payload": kite_payload,
    }


def trigger_kill_switch(
    confirm_kill: bool,
    kite_service: KiteService | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Cancel all active staged orders and safely cancel pending Kite orders/GTTs if live."""
    if not confirm_kill:
        raise GuardrailViolationError(
            code="KILL_SWITCH_CONFIRMATION_REQUIRED",
            message="Explicit confirm_kill=True is required to trigger the Kill Switch.",
        )

    placeholders = ",".join("?" for _ in KILL_SWITCH_TARGET_STATUSES)
    with db_session(db_path) as conn:
        cursor = conn.execute(
            f"""
            UPDATE staged_orders
            SET status = 'CANCELLED_KILL_SWITCH', updated_at = datetime('now')
            WHERE status IN ({placeholders})
            """,
            KILL_SWITCH_TARGET_STATUSES,
        )
        cancelled_staged_count = cursor.rowcount

    live_cancelled_orders = 0
    live_cancelled_gtts = 0
    live_errors: list[str] = []
    live_mode = bool(kite_service is not None and kite_service._is_live() and kite_service._kite is not None)

    if live_mode and kite_service is not None and kite_service._kite is not None:
        kite_client = kite_service._kite
        try:
            orders = kite_client.orders()
            for order in orders or []:
                status = str(order.get("status", "")).upper()
                if status in ("OPEN", "TRIGGER PENDING", "AMO REQ RECEIVED", "VALIDATION PENDING"):
                    try:
                        kite_client.cancel_order(
                            variety=order.get("variety", "regular"),
                            order_id=order["order_id"],
                        )
                        live_cancelled_orders += 1
                    except Exception as exc:  # pragma: no cover - defensive live guard
                        live_errors.append(f"order:{order.get('order_id')}:{type(exc).__name__}")
        except Exception as exc:  # pragma: no cover - defensive live guard
            live_errors.append(f"orders_fetch:{type(exc).__name__}")

        if hasattr(kite_client, "get_gtts") and hasattr(kite_client, "delete_gtt"):
            try:
                gtts = kite_client.get_gtts()
                for gtt in gtts or []:
                    if str(gtt.get("status", "")).lower() == "active":
                        try:
                            kite_client.delete_gtt(gtt["id"])
                            live_cancelled_gtts += 1
                        except Exception as exc:  # pragma: no cover
                            live_errors.append(f"gtt:{gtt.get('id')}:{type(exc).__name__}")
            except Exception as exc:  # pragma: no cover
                live_errors.append(f"gtts_fetch:{type(exc).__name__}")

    return {
        "kill_switch_triggered": True,
        "cancelled_staged_count": cancelled_staged_count,
        "live_mode": live_mode,
        "live_cancelled_orders": live_cancelled_orders,
        "live_cancelled_gtts": live_cancelled_gtts,
        "live_errors": live_errors,
    }


def get_capital_capacity(
    rules: RulesConfig | None = None,
    kite_service: KiteService | None = None,
    nifty_at_ath: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Capital-First capacity check: Aukaat slots, Nifty ATH 50% cut, and Kite margin."""
    cfg = rules or load_rules_config()
    counts = get_aukaat_counts(db_path=db_path)

    naked_max = cfg.capital.max_naked_positions
    hedged_max = cfg.capital.max_hedged_positions
    if nifty_at_ath:
        factor = max(0.0, 1.0 - (cfg.capital.cut_exposure_at_nifty_ath_pct / 100.0))
        naked_max = max(1, int(naked_max * factor))
        hedged_max = max(1, int(hedged_max * factor))

    margins = kite_service.get_margins() if kite_service else None
    return {
        "tier": cfg.capital.tier,
        "nifty_at_ath_cut_applied": nifty_at_ath,
        "naked_used": counts["naked_count"],
        "naked_max": naked_max,
        "naked_free": max(0, naked_max - counts["naked_count"]),
        "total_used": counts["total_count"],
        "hedged_max": hedged_max,
        "hedged_free": max(0, hedged_max - counts["total_count"]),
        "can_open_naked": counts["naked_count"] < naked_max,
        "can_open_hedged": counts["total_count"] < hedged_max,
        "available_margin_inr": margins.total_available if margins else 0.0,
    }


def check_physical_delivery_guard(
    days_to_expiry: int,
    option_type: Literal["PE", "CE", "FUT"],
    moneyness: Literal["ITM", "ATM", "OTM"] = "ITM",
    rules: RulesConfig | None = None,
) -> dict[str, Any]:
    """Enforce Physical Delivery Guard (<=2 days before expiry / Last Thursday)."""
    cfg = rules or load_rules_config()
    cutoff = cfg.rollover.physical_delivery_cutoff_days
    in_cutoff = days_to_expiry <= cutoff
    requires_action = in_cutoff and option_type in ("PE", "CE") and moneyness in ("ITM", "ATM")
    return {
        "days_to_expiry": days_to_expiry,
        "cutoff_days": cutoff,
        "in_delivery_window": in_cutoff,
        "requires_squareoff_or_roll": requires_action,
        "action": "SQUARE_OFF_OR_ROLL_BEFORE_CLOSE" if requires_action else "HOLD_OR_MONITOR",
        "message": (
            f"Physical Delivery Guard: {days_to_expiry}d to expiry (<= {cutoff}d cutoff). Square off or roll Same-Strike before Last Thursday close."
            if requires_action
            else f"Safe: {days_to_expiry}d to expiry (> {cutoff}d cutoff)."
        ),
    }
