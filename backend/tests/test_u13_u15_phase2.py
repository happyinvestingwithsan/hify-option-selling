"""Unit tests for Phase 2 (U13 Universe, U14 Fundamentals/Theta, U15 Capacity/Delivery)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.config import load_rules_config
from app.db import init_db
from app.services.fundamentals import evaluate_fundamental_pass
from app.services.guardrails import check_physical_delivery_guard, get_capital_capacity
from app.services.scanner import (
    DhoolChaatScanner,
    calculate_lower_blue_line,
    calculate_theta_opportunity_score,
)
from app.services.universe import (
    UniverseStockInput,
    get_universe_changelog,
    list_universe_stocks,
    reconcile_universe_list,
    seed_f40_e40_if_empty,
)


def test_universe_f40_e40_seed_and_no_s200(tmp_path: Path) -> None:
    db_path = tmp_path / "test_u13.db"
    init_db(db_path)
    seeded = seed_f40_e40_if_empty(db_path=db_path)
    assert seeded == {"F40": 40, "E40": 40}

    f40 = list_universe_stocks(universe_type="F40", db_path=db_path)
    e40 = list_universe_stocks(universe_type="E40", db_path=db_path)
    assert len(f40) == 40
    assert len(e40) == 40

    large_f40 = list_universe_stocks(universe_type="F40", cap_tier="large", db_path=db_path)
    assert len(large_f40) > 0
    assert all(row["cap_tier"] == "large" for row in large_f40)

    with pytest.raises(ValueError):
        reconcile_universe_list("S200", [], db_path=db_path)  # type: ignore[arg-type]


def test_universe_dynamic_in_out_changelog(tmp_path: Path) -> None:
    db_path = tmp_path / "test_u13_inout.db"
    init_db(db_path)
    res1 = reconcile_universe_list(
        "NSE_FNO",
        [
            UniverseStockInput(symbol="INFY", cap_tier="large", lot_size=400),
            UniverseStockInput(symbol="TATAMOTORS", cap_tier="large", lot_size=550),
        ],
        reason="sync1",
        db_path=db_path,
    )
    assert res1["added"] == ["INFY", "TATAMOTORS"]

    res2 = reconcile_universe_list(
        "NSE_FNO",
        [
            UniverseStockInput(symbol="INFY", cap_tier="large", lot_size=400),
            UniverseStockInput(symbol="RELIANCE", cap_tier="large", lot_size=250),
        ],
        reason="sync2",
        db_path=db_path,
    )
    assert res2["added"] == ["RELIANCE"]
    assert res2["removed"] == ["TATAMOTORS"]

    log = get_universe_changelog(universe_type="NSE_FNO", db_path=db_path)
    actions = {(row["symbol"], row["action"]) for row in log}
    assert ("RELIANCE", "ADDED") in actions
    assert ("TATAMOTORS", "REMOVED") in actions


def test_lower_blue_line_theta_score_and_fundamentals() -> None:
    closes = [100.0] * 200
    assert calculate_lower_blue_line(closes) == 86.0

    high_vol = calculate_theta_opportunity_score(
        ppm_pct=6.5, iv_pct=45.0, hv_spike_ratio=1.4, spread_pct=1.2, is_red_candle=True
    )
    low_vol = calculate_theta_opportunity_score(
        ppm_pct=2.0, iv_pct=14.0, hv_spike_ratio=0.9, spread_pct=4.5, is_red_candle=False
    )
    assert high_vol > low_vol

    assert evaluate_fundamental_pass(
        {
            "public_holding_pct": 22.0,
            "promoter_pledge_pct": 0.0,
            "current_pe": 18.0,
            "pe_median_5y": 24.0,
            "roce_pct": 19.0,
            "debt_to_equity": 0.1,
        }
    )
    assert not evaluate_fundamental_pass(
        {
            "public_holding_pct": 38.0,
            "promoter_pledge_pct": 0.0,
            "current_pe": 18.0,
            "pe_median_5y": 24.0,
            "roce_pct": 19.0,
            "debt_to_equity": 0.1,
        }
    )


def test_scanner_aukaat_summary_and_cap_slicer() -> None:
    scanner = DhoolChaatScanner(rules=load_rules_config())
    res = scanner.scan(include_rejected=False, cap_tier="large")
    assert "naked_max" in res.aukaat_summary
    assert all(item.cap_tier == "large" for item in res.items)


def test_capital_capacity_nifty_ath_and_delivery_guard(tmp_path: Path) -> None:
    db_path = tmp_path / "test_u15.db"
    init_db(db_path)
    normal = get_capital_capacity(nifty_at_ath=False, db_path=db_path)
    ath_cut = get_capital_capacity(nifty_at_ath=True, db_path=db_path)
    assert normal["naked_max"] == 4
    assert ath_cut["naked_max"] == 2

    guard_alert = check_physical_delivery_guard(days_to_expiry=1, option_type="PE", moneyness="ITM")
    assert guard_alert["requires_squareoff_or_roll"] is True
    guard_safe = check_physical_delivery_guard(days_to_expiry=10, option_type="PE", moneyness="ITM")
    assert guard_safe["requires_squareoff_or_roll"] is False
