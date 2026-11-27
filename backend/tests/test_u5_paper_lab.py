"""Tests for Unit U5: Isolated Paper / Strategy Lab."""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import PROJECT_ROOT, get_settings
from app.db import init_db
from app.main import create_app


def _build_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_file = tmp_path / "u5_test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    get_settings.cache_clear()
    init_db(db_file)
    app = create_app()
    return TestClient(app)


def test_paper_lab_strict_isolation_ast_check() -> None:
    """Assert paper_lab.py and routers/paper.py have zero imports/calls to live order/GTT endpoints."""
    forbidden_modules = {"orders", "guardrails", "app.routers.orders", "app.services.guardrails"}
    forbidden_symbols = {
        "approve_staged_order",
        "trigger_kill_switch",
        "place_order",
        "place_gtt",
        "cancel_order",
        "delete_gtt",
        "stage_ato_gtt_order",
    }

    target_files = [
        PROJECT_ROOT / "backend" / "app" / "services" / "paper_lab.py",
        PROJECT_ROOT / "backend" / "app" / "routers" / "paper.py",
    ]

    for file_path in target_files:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_modules, f"Forbidden import {alias.name} in {file_path}"
                    assert not alias.name.endswith(".orders"), f"Forbidden orders import in {file_path}"
                    assert not alias.name.endswith(".guardrails"), f"Forbidden guardrails import in {file_path}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert mod not in forbidden_modules, f"Forbidden import from {mod} in {file_path}"
                assert not mod.endswith(".orders"), f"Forbidden orders import in {file_path}"
                assert not mod.endswith(".guardrails"), f"Forbidden guardrails import in {file_path}"
                for alias in node.names:
                    assert alias.name not in forbidden_symbols, f"Forbidden symbol {alias.name} in {file_path}"
            elif isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_symbols, f"Forbidden attribute {node.attr} in {file_path}"
            elif isinstance(node, ast.Name):
                assert node.id not in forbidden_symbols, f"Forbidden name {node.id} in {file_path}"


def test_paper_trade_creation_guardrails_and_aukaat_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validate LIMIT-only, spread, naked call, PPM, and 25L Aukaat cap in Paper Lab."""
    with _build_client(tmp_path, monkeypatch) as client:
        # 1. Reject MARKET order
        resp = client.post(
            "/api/paper/trades",
            json={
                "symbol": "HDFCBANK",
                "strike": 1600,
                "option_type": "PE",
                "expiry": "26DEC",
                "side": "SELL",
                "qty": 550,
                "order_type": "MARKET",
                "limit_price": 24.0,
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "MARKET_ORDER_BLOCKED"

        # 2. Reject wide spread (>5% option, >1.5% future)
        resp = client.post(
            "/api/paper/trades",
            json={
                "symbol": "HDFCBANK",
                "strike": 1600,
                "option_type": "PE",
                "expiry": "26DEC",
                "side": "SELL",
                "qty": 550,
                "order_type": "LIMIT",
                "limit_price": 24.0,
                "bid_price": 20.0,
                "ask_price": 25.0,
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "SPREAD_TOO_WIDE"

        resp = client.post(
            "/api/paper/trades",
            json={
                "symbol": "HDFCBANK",
                "strike": 0,
                "option_type": "FUT",
                "expiry": "26DEC",
                "side": "BUY",
                "qty": 550,
                "order_type": "LIMIT",
                "limit_price": 1620.0,
                "spread_pct": 2.0,
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "SPREAD_TOO_WIDE"

        # 3. Reject naked Call, allow covered Call
        resp = client.post(
            "/api/paper/trades",
            json={
                "symbol": "INFY",
                "strike": 1900,
                "option_type": "CE",
                "expiry": "26DEC",
                "side": "SELL",
                "qty": 400,
                "limit_price": 30.0,
                "is_covered_call": False,
            },
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "NAKED_CALL_BLOCKED"

        # 4. Create 4 naked trades (allowed), 5th naked blocked, 5th & 6th hedged allowed, 7th blocked
        for idx, sym in enumerate(["HDFCBANK", "TCS", "ICICIBANK", "SBIN"]):
            ok = client.post(
                "/api/paper/trades",
                json={
                    "symbol": sym,
                    "strike": 1000 + idx * 100,
                    "option_type": "PE",
                    "expiry": "26DEC",
                    "side": "SELL",
                    "qty": 500,
                    "limit_price": 25.0,
                    "bid_price": 24.5,
                    "ask_price": 25.0,
                    "margin_blocked": 250000.0,
                    "is_hedged": False,
                },
            )
            assert ok.status_code == 200
            trade = ok.json()["trade"]
            assert trade["status"] == "OPEN"
            assert trade["ppm_pct"] == 5.0
            assert trade["decay_target_pct"] == 50.0

        fifth_naked = client.post(
            "/api/paper/trades",
            json={
                "symbol": "LT",
                "strike": 3500,
                "option_type": "PE",
                "expiry": "26DEC",
                "side": "SELL",
                "qty": 150,
                "limit_price": 40.0,
                "is_hedged": False,
            },
        )
        assert fifth_naked.status_code == 422
        assert fifth_naked.json()["detail"]["code"] == "AUKAAT_NAKED_CAP_EXCEEDED"

        for sym in ["LT", "RELIANCE"]:
            hedged_ok = client.post(
                "/api/paper/trades",
                json={
                    "symbol": sym,
                    "strike": 2800,
                    "option_type": "CE",
                    "expiry": "26DEC",
                    "side": "SELL",
                    "qty": 250,
                    "limit_price": 30.0,
                    "is_hedged": True,
                    "is_covered_call": True,
                },
            )
            assert hedged_ok.status_code == 200

        seventh = client.post(
            "/api/paper/trades",
            json={
                "symbol": "ITC",
                "strike": 450,
                "option_type": "PE",
                "expiry": "26DEC",
                "side": "SELL",
                "qty": 1600,
                "limit_price": 6.0,
                "is_hedged": True,
            },
        )
        assert seventh.status_code == 422
        assert seventh.json()["detail"]["code"] == "AUKAAT_HEDGED_CAP_EXCEEDED"


def test_ato_trigger_and_decay_simulation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify ATO_WAITING -> OPEN trigger, decay tier targets, read-only quote, and auto-booking."""
    with _build_client(tmp_path, monkeypatch) as client:
        create_resp = client.post(
            "/api/paper/trades",
            json={
                "symbol": "TATAMOTORS",
                "strike": 900,
                "option_type": "PE",
                "expiry": "26DEC",
                "side": "SELL",
                "qty": 550,
                "limit_price": 20.0,
                "ato_trigger_price": 885.0,
                "margin_blocked": 220000.0,
            },
        )
        assert create_resp.status_code == 200
        trade = create_resp.json()["trade"]
        trade_id = trade["id"]
        assert trade["status"] == "ATO_WAITING"
        assert trade["is_ato_triggered"] is False

        # Spot hasn't dropped to trigger yet
        sim1 = client.post(
            f"/api/paper/trades/{trade_id}/simulate",
            json={"simulated_spot_price": 905.0, "simulated_option_price": 18.0, "days_held": 1},
        )
        assert sim1.status_code == 200
        assert sim1.json()["ato_triggered_now"] is False
        assert sim1.json()["trade"]["status"] == "ATO_WAITING"

        # Spot hits trigger (<= 885.0)
        sim2 = client.post(
            f"/api/paper/trades/{trade_id}/simulate",
            json={"simulated_spot_price": 884.0, "simulated_option_price": 19.0, "days_held": 1},
        )
        assert sim2.status_code == 200
        data2 = sim2.json()
        assert data2["ato_triggered_now"] is True
        assert data2["trade"]["status"] == "OPEN"
        assert data2["trade"]["is_ato_triggered"] is True
        assert data2["effective_target_pct"] == 30.0
        assert data2["target_hit"] is False

        # Read-only quote lookup (dry-run fallback)
        sim_quote = client.post(
            f"/api/paper/trades/{trade_id}/simulate",
            json={"use_live_quote": True, "days_held": 15},
        )
        assert sim_quote.status_code == 200
        assert sim_quote.json()["quote_used"] is not None

        # Hit 1-day 30% decay target with auto_book_on_target=True (20 -> 13 = 35% decay)
        sim3 = client.post(
            f"/api/paper/trades/{trade_id}/simulate",
            json={"simulated_option_price": 13.0, "days_held": 1, "auto_book_on_target": True},
        )
        assert sim3.status_code == 200
        data3 = sim3.json()
        assert data3["target_hit"] is True
        assert data3["auto_booked"] is True
        assert data3["current_decay_pct"] == 35.0
        assert data3["trade"]["status"] == "CLOSED"
        assert data3["trade"]["pnl"] == 3850.0  # (20 - 13) * 550


def test_same_strike_rollover_and_far_future_pivot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify Same-Strike Rollover lock blocks roll-down, allows same-strike and far-future pivot."""
    with _build_client(tmp_path, monkeypatch) as client:
        t1 = client.post(
            "/api/paper/trades",
            json={
                "symbol": "ASIANPAINT",
                "strike": 2800,
                "option_type": "PE",
                "expiry": "26DEC",
                "side": "SELL",
                "qty": 200,
                "limit_price": 40.0,
                "margin_blocked": 200000.0,
            },
        ).json()["trade"]

        # Block rolling down to lower strike (2700 < 2800)
        blocked = client.post(
            f"/api/paper/trades/{t1['id']}/rollover",
            json={
                "new_expiry": "30JAN",
                "new_strike": 2700,
                "new_entry_price": 35.0,
                "close_current_price": 55.0,
                "pivot_to_far_future": False,
            },
        )
        assert blocked.status_code == 422
        assert blocked.json()["detail"]["code"] == "ROLLOVER_STRIKE_DOWN_BLOCKED"

        # Allow exact same strike rollover (2800 -> 2800)
        rolled = client.post(
            f"/api/paper/trades/{t1['id']}/rollover",
            json={
                "new_expiry": "30JAN",
                "new_strike": 2800,
                "new_entry_price": 65.0,
                "close_current_price": 50.0,
                "pivot_to_far_future": False,
            },
        )
        assert rolled.status_code == 200
        r_data = rolled.json()
        assert r_data["closed_leg"]["status"] == "ROLLED"
        assert r_data["closed_leg"]["pnl"] == -2000.0  # (40 - 50) * 200
        new_leg = r_data["new_leg"]
        assert new_leg["status"] == "OPEN"
        assert new_leg["strike"] == 2800.0
        assert new_leg["expiry"] == "30JAN"
        assert new_leg["rollover_from_id"] == t1["id"]

        # Pivot to Far-Month Future
        pivot = client.post(
            f"/api/paper/trades/{new_leg['id']}/rollover",
            json={
                "new_expiry": "27FEB",
                "new_entry_price": 2810.0,
                "close_current_price": 45.0,
                "pivot_to_far_future": True,
            },
        )
        assert pivot.status_code == 200
        p_data = pivot.json()
        assert p_data["pivot_to_far_future"] is True
        assert p_data["new_leg"]["option_type"] == "FUT"
        assert p_data["new_leg"]["side"] == "BUY"
        assert p_data["new_leg"]["strike"] == 0.0


def test_close_paper_trade_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify manual close P&L, closed_before_target flag, and summary aggregation."""
    with _build_client(tmp_path, monkeypatch) as client:
        # Trade 1: closed early before 50% decay target
        t1 = client.post(
            "/api/paper/trades",
            json={
                "symbol": "WIPRO",
                "strike": 500,
                "option_type": "PE",
                "expiry": "26DEC",
                "side": "SELL",
                "qty": 1500,
                "limit_price": 10.0,
            },
        ).json()["trade"]

        close1 = client.post(
            f"/api/paper/trades/{t1['id']}/close",
            json={"exit_price": 8.0, "override_reason": "Testing early exit"},
        )
        assert close1.status_code == 200
        c1 = close1.json()
        assert c1["realized_pnl"] == 3000.0
        assert c1["decay_pct"] == 20.0
        assert c1["closed_before_target"] is True
        assert c1["trade"]["status"] == "CLOSED"

        # Trade 2: remains OPEN with unrealized P&L
        t2 = client.post(
            "/api/paper/trades",
            json={
                "symbol": "INFY",
                "strike": 1800,
                "option_type": "PE",
                "expiry": "26DEC",
                "side": "SELL",
                "qty": 400,
                "limit_price": 25.0,
            },
        ).json()["trade"]

        client.post(
            f"/api/paper/trades/{t2['id']}/simulate",
            json={"simulated_option_price": 20.0, "days_held": 15},
        )

        listed = client.get("/api/paper/trades")
        assert listed.status_code == 200
        body = listed.json()
        assert body["count"] == 2
        summary = body["summary"]
        assert summary["open_count"] == 1
        assert summary["closed_count"] == 1
        assert summary["realized_pnl"] == 3000.0
        assert summary["unrealized_pnl"] == 2000.0
        assert summary["total_pnl"] == 5000.0
        assert summary["win_rate_pct"] == 100.0
