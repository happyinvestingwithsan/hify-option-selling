"""Unit and API tests for Unit U3: Dhool Chaat After-Market Scanner."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import RulesConfig
from app.main import create_app
from app.services.scanner import (
    DhoolChaatScanner,
    StockCandidateInput,
    calculate_ath_drop_pct,
    calculate_ppm_pct,
    classify_ppm_tier,
    evaluate_candidate,
    suggest_strike_moneyness,
)


def _base_candidate(**overrides) -> StockCandidateInput:
    data = {
        "symbol": "TESTSTOCK",
        "company_name": "Test Stock Ltd",
        "sector": "IT",
        "cap_tier": "large",
        "ath_price": 1000.0,
        "current_price": 720.0,  # 28% drop
        "institutional_holding_pct": 75.0,
        "current_pe": 18.0,
        "median_pe": 24.0,
        "is_red_candle": True,
        "intraday_drop_pct": -2.5,
        "lower_blue_line": 718.0,
        "option_instrument": "NFO:TESTSTOCK26NOV720PE",
        "option_strike": 720.0,
        "option_bid": 20.0,
        "option_ask": 20.5,
        "premium": 20.25,
        "lot_size": 500,
        "margin_required": 200000.0,
        "is_psu": False,
    }
    data.update(overrides)
    return StockCandidateInput(**data)


def test_math_helpers() -> None:
    rules = RulesConfig()
    assert calculate_ath_drop_pct(1000.0, 750.0) == 25.0
    assert calculate_ath_drop_pct(1000.0, 1050.0) == 0.0

    ppm = calculate_ppm_pct(premium=30.0, lot_size=500, margin_required=200000.0)
    assert ppm == 7.5
    assert classify_ppm_tier(7.5, rules) == "Aggressive"
    assert classify_ppm_tier(4.5, rules) == "Normal"
    assert classify_ppm_tier(2.2, rules) == "Conservative"

    assert suggest_strike_moneyness(100.0, 100.0) == "ATM"
    assert suggest_strike_moneyness(103.0, 100.0) == "OTM"
    assert suggest_strike_moneyness(97.0, 100.0) == "ITM"


def test_evaluate_candidate_passes_and_psu_hedge() -> None:
    rules = RulesConfig()
    res = evaluate_candidate(_base_candidate(), rules)
    assert res.passed is True
    assert res.rejection_reasons == []
    assert res.ath_drop_pct == 28.0
    assert res.suggested_moneyness == "ATM"
    assert res.ppm_pct == 5.06
    assert res.ppm_tier == "Normal"
    assert res.requires_hedge is False

    psu_res = evaluate_candidate(_base_candidate(is_psu=True), rules)
    assert psu_res.passed is True
    assert psu_res.requires_hedge is True
    assert psu_res.hedge_note is not None
    assert "Bull Put Spread" in psu_res.hedge_note


def test_evaluate_candidate_rejections() -> None:
    rules = RulesConfig()

    # Large cap < 25%, Mid cap < 30%, Small cap < 35%
    assert evaluate_candidate(_base_candidate(cap_tier="large", current_price=800.0), rules).passed is False
    assert evaluate_candidate(_base_candidate(cap_tier="mid", current_price=720.0), rules).passed is False
    assert evaluate_candidate(_base_candidate(cap_tier="small", current_price=680.0), rules).passed is False

    # Institutional < 70%
    inst_fail = evaluate_candidate(_base_candidate(institutional_holding_pct=65.0), rules)
    assert inst_fail.passed is False
    assert any("Institutional" in r for r in inst_fail.rejection_reasons)

    # PE >= Median PE
    pe_fail = evaluate_candidate(_base_candidate(current_pe=25.0, median_pe=24.0), rules)
    assert pe_fail.passed is False
    assert any("PE" in r for r in pe_fail.rejection_reasons)

    # Green candle
    candle_fail = evaluate_candidate(_base_candidate(is_red_candle=False), rules)
    assert candle_fail.passed is False
    assert any("Red Candle" in r for r in candle_fail.rejection_reasons)

    # Too far above Lower Blue Line (> 5%)
    zone_fail = evaluate_candidate(_base_candidate(current_price=720.0, lower_blue_line=650.0), rules)
    assert zone_fail.passed is False
    assert any("Lower Blue Line" in r for r in zone_fail.rejection_reasons)

    # Spread > 5%
    spread_fail = evaluate_candidate(_base_candidate(option_bid=18.0, option_ask=22.0), rules)
    assert spread_fail.passed is False
    assert any("spread" in r.lower() for r in spread_fail.rejection_reasons)


def test_live_quote_enrichment() -> None:
    class MockLiveKiteService:
        def _is_live(self) -> bool:
            return True

        def get_quote(self, instruments: list[str]) -> dict:
            return {
                "mode": "live",
                "is_dry_run": False,
                "quotes": {
                    inst: {
                        "best_bid": 10.0,
                        "best_ask": 12.0,
                        "bid_ask_spread_pct": 16.67,
                    }
                    for inst in instruments
                },
            }

    scanner = DhoolChaatScanner(
        rules=RulesConfig(),
        kite_service=MockLiveKiteService(),  # type: ignore[arg-type]
        universe=[_base_candidate()],
    )
    resp = scanner.scan(include_rejected=True, refresh_live_quotes=True)
    assert resp.quotes_refreshed is True
    assert resp.rejected_count == 1
    assert resp.items[0].bid_ask_spread_pct == 16.67


def test_scanner_api_endpoints(tmp_path, monkeypatch) -> None:
    from app.config import get_settings
    from app.db import init_db

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "u3_scanner.db"))
    get_settings.cache_clear()
    monkeypatch.setattr("app.angel_client.AngelDataService.ensure_session", lambda self: False)
    monkeypatch.setattr("app.kite_client.KiteService._is_live", lambda self: False)

    init_db(tmp_path / "u3_scanner.db")
    app = create_app()
    with TestClient(app) as client:
        resp_pass = client.get("/api/scanner/candidates?include_rejected=false")
        assert resp_pass.status_code == 200
        data_pass = resp_pass.json()
        assert data_pass["passed_count"] >= 5
        assert data_pass["rejected_count"] >= 4
        assert all(item["passed"] is True for item in data_pass["items"])

        resp_all = client.get("/api/scanner/candidates?include_rejected=true")
        assert resp_all.status_code == 200
        data_all = resp_all.json()
        assert len(data_all["items"]) == data_all["total_evaluated"]

        resp_mid = client.get("/api/scanner/candidates?cap_tier=mid")
        assert resp_mid.status_code == 200
        assert all(item["cap_tier"] == "mid" for item in resp_mid.json()["items"])

        payload = [
            _base_candidate(symbol="CUSTOM1").model_dump(),
            _base_candidate(symbol="CUSTOM2", is_red_candle=False).model_dump(),
        ]
        resp_eval = client.post("/api/scanner/evaluate", json=payload)
        assert resp_eval.status_code == 200
        eval_data = resp_eval.json()
        assert eval_data["total_evaluated"] == 2
        assert eval_data["passed_count"] == 1
        assert eval_data["rejected_count"] == 1
