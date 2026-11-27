"""Unit and API tests for Unit U17/U18: Live Scanner v2 Engine & Router."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import RulesConfig
from app.main import create_app
from app.services import fundamentals as fundamentals_svc
from app.services.scanner import (
    DhoolChaatScanner,
    StockCandidateInput,
    calculate_52w_drop_pct,
    calculate_dma200_pct,
    evaluate_candidate,
)


def test_52w_and_200dma_math_and_non_rejection_of_fundamental_gates() -> None:
    assert calculate_52w_drop_pct(1000.0, 820.0) == 18.0
    assert calculate_52w_drop_pct(1000.0, 1050.0) == 0.0
    assert calculate_dma200_pct(900.0, 1000.0) == -10.0
    assert calculate_dma200_pct(1100.0, 1000.0) == 10.0

    # Candidate passes all technical/liquidity Rulebook checks, but fails Screener fundamental gates
    candidate = StockCandidateInput(
        symbol="TECHPASS",
        company_name="Tech Pass Ltd",
        sector="IT",
        cap_tier="large",
        ath_price=1000.0,
        current_price=720.0,  # 28% ATH drop
        high_52w=900.0,  # 20% 52W drop
        sma_200=800.0,  # -10% vs 200 DMA
        institutional_holding_pct=75.0,
        current_pe=18.0,
        median_pe=24.0,
        is_red_candle=True,
        intraday_drop_pct=-2.5,
        lower_blue_line=718.0,
        option_instrument="NFO:TECHPASS26NOV720PE",
        option_strike=720.0,
        option_bid=20.0,
        option_ask=20.5,
        premium=20.25,
        lot_size=500,
        margin_required=200000.0,
        fundamentals={"public_holding_pct": 42.0, "debt_to_equity": 1.4},
        fundamental_checks={"public_lt_30": False, "de_le_025": False},
        fundamental_passed=False,
    )
    res = evaluate_candidate(candidate, RulesConfig())
    assert res.high_52w_drop_pct == 20.0
    assert res.dma200_pct == -10.0
    assert res.fundamental_passed is False
    assert res.fundamental_checks["public_lt_30"] is False
    # CRITICAL: Screener fundamental gates must NOT auto-reject the row
    assert res.passed is True
    assert res.rejection_reasons == []


def test_technical_filters_in_scanner() -> None:
    c1 = StockCandidateInput(
        symbol="DEEPRED",
        cap_tier="large",
        ath_price=1000.0,
        current_price=700.0,
        high_52w=900.0,
        sma_200=800.0,
        institutional_holding_pct=75.0,
        current_pe=15.0,
        median_pe=20.0,
        is_red_candle=True,
        intraday_drop_pct=-3.2,
        lower_blue_line=695.0,
        option_bid=10.0,
        option_ask=10.2,
        premium=10.1,
        lot_size=500,
        margin_required=200000.0,
    )
    c2 = StockCandidateInput(
        symbol="GREENMILD",
        cap_tier="large",
        ath_price=1000.0,
        current_price=920.0,
        high_52w=950.0,
        sma_200=900.0,
        institutional_holding_pct=75.0,
        current_pe=15.0,
        median_pe=20.0,
        is_red_candle=False,
        intraday_drop_pct=1.1,
        lower_blue_line=880.0,
        option_bid=10.0,
        option_ask=11.0,
        premium=10.5,
        lot_size=500,
        margin_required=200000.0,
    )
    scanner = DhoolChaatScanner(rules=RulesConfig(), universe=[c1, c2])

    red_only = scanner.scan(include_rejected=True, red_candle_only=True)
    assert [item.symbol for item in red_only.items] == ["DEEPRED"]

    ath_filtered = scanner.scan(include_rejected=True, min_ath_drop_pct=25.0)
    assert [item.symbol for item in ath_filtered.items] == ["DEEPRED"]

    w52_filtered = scanner.scan(include_rejected=True, min_52w_drop_pct=15.0)
    assert [item.symbol for item in w52_filtered.items] == ["DEEPRED"]

    dma_filtered = scanner.scan(include_rejected=True, min_dma200_drop_pct=10.0)
    assert [item.symbol for item in dma_filtered.items] == ["DEEPRED"]


def test_scanner_v2_slicers_hydrate_and_fundamentals_api(monkeypatch) -> None:
    app = create_app()
    with TestClient(app) as client:
        # 1. Default /api/scanner/candidates includes rejected rows and returns full hydrated master list
        resp_default = client.get("/api/scanner/candidates")
        assert resp_default.status_code == 200
        default_data = resp_default.json()
        assert default_data["total_evaluated"] >= 80
        assert len(default_data["items"]) == default_data["total_evaluated"]
        assert default_data["freshness"] in ("dry_run", "cached", "live")

        # 2. INDICES slicer returns the 4 baseline NSE F&O indices
        resp_idx = client.get("/api/scanner/candidates?universe_type=INDICES")
        assert resp_idx.status_code == 200
        idx_data = resp_idx.json()
        idx_syms = {item["symbol"] for item in idx_data["items"]}
        assert idx_syms == {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"}
        assert all(item["instrument_type"] == "INDEX" for item in idx_data["items"])

        # 3. F40 and E40 slicers return their respective 40-stock lists
        resp_f40 = client.get("/api/scanner/candidates?universe_type=F40")
        assert resp_f40.status_code == 200
        assert resp_f40.json()["total_evaluated"] == 40

        resp_e40 = client.get("/api/scanner/candidates?universe_type=E40")
        assert resp_e40.status_code == 200
        assert resp_e40.json()["total_evaluated"] == 40

        # 4. POST /api/scanner/hydrate works for explicit symbols
        resp_hydrate = client.post(
            "/api/scanner/hydrate",
            json={"symbols": ["RELIANCE", "NIFTY"], "include_indices": False, "fetch_fundamentals": False},
        )
        assert resp_hydrate.status_code == 200
        hyd = resp_hydrate.json()
        assert hyd["hydrated"] == 2
        assert hyd["eq_count"] == 1
        assert hyd["index_count"] == 1

        # 5. POST /api/scanner/fundamentals/{symbol} (mocked Screener HTTP)
        sample_html = """
        <div data-company-id="12345"></div>
        <ul>
          <li>Market Cap <span class="number">1,25,000</span></li>
          <li>Stock P/E <span class="number">18.4</span></li>
          <li>ROCE <span class="number">21.5</span></li>
          <li>ROE <span class="number">16.2</span></li>
          <li>Debt to equity <span class="number">0.12</span></li>
        </ul>
        <section id="shareholding">
          <tr><td>Public</td><td>22.5%</td></tr>
          <tr><td>Pledged</td><td>0.0%</td></tr>
        </section>
        """
        chart_json = '{"datasets":[{"metric":"Median PE","values":[["2025-01-01","24.0"]]}]}'

        def mock_fetch_text(url: str, timeout: int = 12) -> str:
            if "api/company" in url:
                return chart_json
            return sample_html

        monkeypatch.setattr(fundamentals_svc, "_fetch_text", mock_fetch_text)
        resp_fund = client.post("/api/scanner/fundamentals/RELIANCE")
        assert resp_fund.status_code == 200
        fund_data = resp_fund.json()
        assert fund_data["symbol"] == "RELIANCE"
        assert fund_data["fundamental_passed"] is True
        assert fund_data["fundamental_checks"]["public_lt_30"] is True
        assert fund_data["fundamentals"]["current_pe"] == 18.4
