"""Rulebook Retrospective Audit & Lessons Learnt service (Unit U8)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config import PROJECT_ROOT, RulesConfig, load_rules_config
from app.db import db_session

DEFAULT_LESSONS_DOC_PATH = PROJECT_ROOT / "docs" / "LESSONS_LEARNT.md"


class LessonCreateRequest(BaseModel):
    """Request payload for logging a new trading lesson or guardrail."""

    category: str = Field(default="DISCIPLINE", min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    mistake_type: str = ""
    rule_added: str = ""
    position_id: int | None = None
    append_to_doc: bool = False


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Best-effort parser for SQLite datetime('now') or ISO timestamps."""
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _resolve_expected_decay_target(
    exit_reason: str,
    override_reason: str,
    opened_at: str | None,
    closed_at: str | None,
    rules: RulesConfig,
) -> float:
    """Determine expected decay target % from duration or exit context."""
    combined = f"{exit_reason} {override_reason}".upper()
    decay_rules = rules.profit_booking_decay_pct

    if "EXPIRY" in combined:
        return float(decay_rules.expiry_week_min)
    if "1D" in combined or "INTRADAY" in combined:
        return float(decay_rules.intraday_1_day)
    if "2D" in combined or "3D" in combined or "FAST" in combined:
        return float(decay_rules.fast_2_to_3_days)

    start_dt = _parse_iso_datetime(opened_at)
    end_dt = _parse_iso_datetime(closed_at)
    if start_dt and end_dt and end_dt >= start_dt:
        days_held = max(0, (end_dt - start_dt).days)
        if days_held <= 1:
            return float(decay_rules.intraday_1_day)
        if days_held <= 3:
            return float(decay_rules.fast_2_to_3_days)
        if days_held >= 20:
            return float(decay_rules.expiry_week_min)

    return float(decay_rules.mid_month_gtt)


def _add_recommendation(recommendations: list[str], text: str) -> None:
    """Append recommendation if not already present."""
    if text not in recommendations:
        recommendations.append(text)


def run_rulebook_audit(
    db_path: str | Path | None = None,
    rules: RulesConfig | None = None,
) -> dict[str, Any]:
    """Audit trades, positions, staged orders, and lessons against STRATEGY_RULEBOOK.md."""
    cfg = rules or load_rules_config()
    findings: list[dict[str, Any]] = []
    recommendations: list[str] = []

    with db_session(db_path) as conn:
        trades_history = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM trades_history ORDER BY id DESC"
            ).fetchall()
        ]
        positions = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM positions ORDER BY id DESC"
            ).fetchall()
        ]
        staged_orders = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM staged_orders ORDER BY id DESC"
            ).fetchall()
        ]
        lessons = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM lessons_log ORDER BY id DESC"
            ).fetchall()
        ]

    positions_by_id = {int(p["id"]): p for p in positions if p.get("id") is not None}
    audited_position_ids: set[int] = set()
    total_trades_audited = 0

    # 1. Audit closed trades in trades_history
    for trade in trades_history:
        total_trades_audited += 1
        pos_id = trade.get("position_id")
        if pos_id is not None:
            audited_position_ids.add(int(pos_id))
        linked_pos = positions_by_id.get(int(pos_id)) if pos_id is not None else None

        symbol = str(trade["symbol"])
        strike = float(trade["strike"])
        option_type = str(trade["option_type"])
        expiry = str(trade["expiry"])
        side = str(trade["side"])
        qty = int(trade["qty"])
        entry_price = float(trade["entry_price"])
        actual_decay_pct = float(trade.get("decay_pct") or 0.0)
        exit_reason = str(trade.get("exit_reason") or "")
        override_reason = str(trade.get("override_reason") or "")

        # Premature exit vs Decay Target for SELL option trades
        if side == "SELL" and option_type in ("PE", "CE"):
            expected_target_pct = _resolve_expected_decay_target(
                exit_reason=exit_reason,
                override_reason=override_reason,
                opened_at=linked_pos.get("opened_at") if linked_pos else None,
                closed_at=trade.get("executed_at"),
                rules=cfg,
            )
            if actual_decay_pct < expected_target_pct:
                missed_profit_inr = round(
                    max(
                        0.0,
                        ((expected_target_pct - actual_decay_pct) / 100.0)
                        * entry_price
                        * qty,
                    ),
                    2,
                )
                better_action = "Hold for target decay unless thesis breaks."
                findings.append(
                    {
                        "id": f"trade-{trade['id']}-premature-exit",
                        "source": "trades_history",
                        "symbol": symbol,
                        "strike": strike,
                        "option_type": option_type,
                        "expiry": expiry,
                        "rule_violated": "PREMATURE_EXIT",
                        "severity": "HIGH",
                        "actual_decay_pct": round(actual_decay_pct, 2),
                        "expected_target_pct": round(expected_target_pct, 2),
                        "missed_profit_inr": missed_profit_inr,
                        "what_happened": (
                            f"Closed {symbol} {strike:g} {option_type} at "
                            f"{actual_decay_pct:.1f}% decay vs {expected_target_pct:.1f}% target."
                        ),
                        "better_action": better_action,
                    }
                )
                _add_recommendation(recommendations, better_action)

        # Naked Call check
        if side == "SELL" and option_type == "CE":
            is_hedged = bool(linked_pos.get("is_hedged")) if linked_pos else False
            notes = str(linked_pos.get("notes") or "") if linked_pos else ""
            if not is_hedged and "COVERED" not in notes.upper():
                better_action = "Sell Calls only as Covered Calls paired with long stock/Futures."
                findings.append(
                    {
                        "id": f"trade-{trade['id']}-naked-call",
                        "source": "trades_history",
                        "symbol": symbol,
                        "strike": strike,
                        "option_type": option_type,
                        "expiry": expiry,
                        "rule_violated": "NAKED_CALL",
                        "severity": "CRITICAL",
                        "actual_decay_pct": round(actual_decay_pct, 2),
                        "expected_target_pct": None,
                        "missed_profit_inr": 0.0,
                        "what_happened": f"Sold CE on {symbol} {strike:g} without covered/hedged marker.",
                        "better_action": better_action,
                    }
                )
                _add_recommendation(recommendations, better_action)

        # Explicit override logged
        if override_reason.strip():
            better_action = "Avoid manual rule overrides; let GTT Decay Lock manage exits."
            findings.append(
                {
                    "id": f"trade-{trade['id']}-override",
                    "source": "trades_history",
                    "symbol": symbol,
                    "strike": strike,
                    "option_type": option_type,
                    "expiry": expiry,
                    "rule_violated": "RULE_OVERRIDE",
                    "severity": "MEDIUM",
                    "actual_decay_pct": round(actual_decay_pct, 2),
                    "expected_target_pct": None,
                    "missed_profit_inr": 0.0,
                    "what_happened": f"Manual override recorded on {symbol}: {override_reason.strip()}",
                    "better_action": better_action,
                }
            )
            _add_recommendation(recommendations, better_action)

    # 2. Audit open/closed positions not already audited via trades_history
    open_positions = [p for p in positions if str(p.get("status")) == "OPEN"]
    naked_open = sum(1 for p in open_positions if not bool(p.get("is_hedged")))
    hedged_open = sum(1 for p in open_positions if bool(p.get("is_hedged")))

    if naked_open > cfg.capital.max_naked_positions or (
        naked_open + hedged_open > cfg.capital.max_hedged_positions
    ):
        better_action = (
            f"Respect {cfg.capital.tier} Aukaat cap: max {cfg.capital.max_naked_positions} naked "
            f"or {cfg.capital.max_hedged_positions} hedged positions."
        )
        findings.append(
            {
                "id": "portfolio-aukaat-cap",
                "source": "positions",
                "symbol": "PORTFOLIO",
                "strike": 0.0,
                "option_type": "PE",
                "expiry": "ACTIVE",
                "rule_violated": "AUKAAT_CAP_BREACH",
                "severity": "CRITICAL",
                "actual_decay_pct": None,
                "expected_target_pct": None,
                "missed_profit_inr": 0.0,
                "what_happened": (
                    f"Active positions ({naked_open} naked, {hedged_open} hedged) exceed "
                    f"{cfg.capital.tier} Aukaat limits."
                ),
                "better_action": better_action,
            }
        )
        _add_recommendation(recommendations, better_action)

    for pos in positions:
        pos_id = int(pos["id"])
        if pos_id not in audited_position_ids:
            total_trades_audited += 1
        if str(pos.get("status")) == "CLOSED" and pos_id not in audited_position_ids:
            side = str(pos["side"])
            option_type = str(pos["option_type"])
            actual_decay_pct = float(pos.get("decay_pct") or 0.0)
            entry_price = float(pos["entry_price"])
            qty = int(pos["qty"])
            if side == "SELL" and option_type in ("PE", "CE"):
                expected_target_pct = _resolve_expected_decay_target(
                    exit_reason=str(pos.get("notes") or ""),
                    override_reason="",
                    opened_at=pos.get("opened_at"),
                    closed_at=pos.get("closed_at"),
                    rules=cfg,
                )
                if actual_decay_pct < expected_target_pct:
                    missed_profit_inr = round(
                        max(
                            0.0,
                            ((expected_target_pct - actual_decay_pct) / 100.0)
                            * entry_price
                            * qty,
                        ),
                        2,
                    )
                    better_action = "Hold for target decay unless thesis breaks."
                    findings.append(
                        {
                            "id": f"position-{pos_id}-premature-exit",
                            "source": "positions",
                            "symbol": str(pos["symbol"]),
                            "strike": float(pos["strike"]),
                            "option_type": option_type,
                            "expiry": str(pos["expiry"]),
                            "rule_violated": "PREMATURE_EXIT",
                            "severity": "HIGH",
                            "actual_decay_pct": round(actual_decay_pct, 2),
                            "expected_target_pct": round(expected_target_pct, 2),
                            "missed_profit_inr": missed_profit_inr,
                            "what_happened": (
                                f"Closed {pos['symbol']} {float(pos['strike']):g} {option_type} "
                                f"at {actual_decay_pct:.1f}% decay vs {expected_target_pct:.1f}% target."
                            ),
                            "better_action": better_action,
                        }
                    )
                    _add_recommendation(recommendations, better_action)

    # 3. Audit staged_orders for Bid-Ask spread > 5% (or > 1.5% for FUT) & overrides
    for order in staged_orders:
        spread_pct = order.get("spread_pct")
        option_type = str(order["option_type"])
        max_spread = (
            cfg.entry_triggers.max_future_bid_ask_spread_pct
            if option_type == "FUT"
            else cfg.entry_triggers.max_option_bid_ask_spread_pct
        )
        if spread_pct is not None and float(spread_pct) > max_spread:
            better_action = (
                f"Reject illiquid {option_type} contracts with Bid-Ask spread > {max_spread:.1f}%."
            )
            findings.append(
                {
                    "id": f"order-{order['id']}-wide-spread",
                    "source": "staged_orders",
                    "symbol": str(order["symbol"]),
                    "strike": float(order["strike"]),
                    "option_type": option_type,
                    "expiry": str(order["expiry"]),
                    "rule_violated": "WIDE_SPREAD",
                    "severity": "MEDIUM",
                    "actual_decay_pct": None,
                    "expected_target_pct": None,
                    "missed_profit_inr": 0.0,
                    "what_happened": (
                        f"Staged {order['symbol']} {option_type} with {float(spread_pct):.2f}% "
                        f"spread (limit {max_spread:.1f}%)."
                    ),
                    "better_action": better_action,
                }
            )
            _add_recommendation(recommendations, better_action)

    # 4. Surface explicit violations/overrides logged in lessons_log
    for lesson in lessons:
        mistake_type = str(lesson.get("mistake_type") or "").strip().upper()
        category = str(lesson.get("category") or "").strip().upper()
        if mistake_type in (
            "DECAY_LOCK_OVERRIDE",
            "ROLL_DOWN_STRIKE",
            "AUKAAT_BREACH",
            "NAKED_CALL",
            "WIDE_SPREAD",
            "EARLY_EXIT",
        ) or category == "DECAY_LOCK_OVERRIDE":
            better_action = (
                str(lesson.get("rule_added") or "").strip()
                or "Follow automated Decay Lock and Same-Strike Rollover guardrails."
            )
            findings.append(
                {
                    "id": f"lesson-{lesson['id']}",
                    "source": "lessons_log",
                    "symbol": "LESSON",
                    "strike": 0.0,
                    "option_type": "PE",
                    "expiry": str(lesson.get("created_at") or "")[:10],
                    "rule_violated": mistake_type or category,
                    "severity": "MEDIUM",
                    "actual_decay_pct": None,
                    "expected_target_pct": None,
                    "missed_profit_inr": 0.0,
                    "what_happened": f"{lesson['title']}: {lesson['description']}",
                    "better_action": better_action,
                }
            )
            _add_recommendation(recommendations, better_action)

    violations_count = len(findings)
    total_missed_profit_inr = round(
        sum(float(f.get("missed_profit_inr") or 0.0) for f in findings),
        2,
    )

    if violations_count == 0:
        discipline_score_pct = 100.0
    else:
        denominator = max(total_trades_audited, violations_count, 1)
        penalty = (violations_count / denominator) * 100.0
        discipline_score_pct = round(max(0.0, min(100.0, 100.0 - penalty)), 1)

    return {
        "discipline_score_pct": discipline_score_pct,
        "total_missed_profit_inr": total_missed_profit_inr,
        "total_trades_audited": total_trades_audited,
        "violations_count": violations_count,
        "findings": findings,
        "recommendations": recommendations,
    }


def list_lessons(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return all logged lessons from `lessons_log` ordered newest first."""
    with db_session(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM lessons_log ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def create_lesson(
    req: LessonCreateRequest,
    db_path: str | Path | None = None,
    lessons_doc_path: Path | None = None,
) -> dict[str, Any]:
    """Insert a lesson into `lessons_log` and optionally append to `docs/LESSONS_LEARNT.md`."""
    with db_session(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO lessons_log (
                category, title, description, mistake_type, rule_added, position_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                req.category.strip().upper(),
                req.title.strip(),
                req.description.strip(),
                req.mistake_type.strip().upper(),
                req.rule_added.strip(),
                req.position_id,
            ),
        )
        lesson_id = cursor.lastrowid
        row = conn.execute(
            "SELECT * FROM lessons_log WHERE id = ?",
            (lesson_id,),
        ).fetchone()

    lesson = dict(row)

    if req.append_to_doc:
        target_doc = lessons_doc_path or DEFAULT_LESSONS_DOC_PATH
        target_doc.parent.mkdir(parents=True, exist_ok=True)
        bullet = (
            f"\n- **LL-{lesson['id']:03d} [{lesson['category']}] {lesson['title']}:** "
            f"{lesson['description']}"
            + (f" *(Guardrail: {lesson['rule_added']})*" if lesson["rule_added"] else "")
            + "\n"
        )
        with target_doc.open("a", encoding="utf-8") as fh:
            fh.write(bullet)

    return lesson
