"""Comprehensive unit and API tests for Unit U4: ATO/GTT Staging & Guardrails Engine."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import load_rules_config
from app.db import db_session, init_db
from app.main import create_app
from app.routers.kite import get_kite_service
from app.services.guardrails import (
    GuardrailViolationError,
    OrderStageRequest,
    check_decay_lock,
    stage_ato_gtt_order,
    trigger_kill_switch,
    validate_order_request,
)


@pytest.fixture()
def isolated_app(tmp_path: Path):
    """Create a FastAPI TestClient backed by an isolated temporary SQLite DB."""
    db_file = tmp_path / "test_u4.db"
    init_db(db_file)
    app = create_app()
    app.state.db_path = str(db_file)
    app.state.db_initialized = True
    app.state.rules = load_rules_config()
    with TestClient(app) as client:
        # Override lifespan's default db_path with our isolated temp db
        app.state.db_path = str(db_file)
        yield client, db_file, app


def _valid_stage_payload(**overrides) -> dict:
    payload = {
        "symbol": "RELIANCE",
        "strike": 1200.0,
        "option_type": "PE",
        "expiry": "25MAY",
        "side": "SELL",
        "qty": 500,
        "order_type": "LIMIT",
        "limit_price": 24.5,
        "bid_price": 24.0,
        "ask_price": 24.8,
        "gtt_target_price": 12.25,
        "gtt_decay_pct": 50.0,
        "is_hedged": False,
        "is_covered_call": False,
    }
    payload.update(overrides)
    return payload


def test_rejects_market_order_type(isolated_app) -> None:
    client, _, _ = isolated_app
    resp = client.post("/api/orders/stage", json=_valid_stage_payload(order_type="MARKET"))
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "LIMIT_ONLY"


def test_rejects_wide_bid_ask_spread_for_options_and_futures(isolated_app) -> None:
    client, _, _ = isolated_app

    # Option spread: (25.0 - 23.0) / 25.0 = 8.0% > 5.0%
    resp_opt = client.post(
        "/api/orders/stage",
        json=_valid_stage_payload(bid_price=23.0, ask_price=25.0),
    )
    assert resp_opt.status_code == 422
    assert resp_opt.json()["detail"]["code"] == "SPREAD_TOO_WIDE"

    # Future spread: (1250.0 - 1220.0) / 1250.0 = 2.4% > 1.5%
    resp_fut = client.post(
        "/api/orders/stage",
        json=_valid_stage_payload(
            option_type="FUT",
            strike=0.0,
            side="BUY",
            limit_price=1235.0,
            bid_price=1220.0,
            ask_price=1250.0,
        ),
    )
    assert resp_fut.status_code == 422
    assert resp_fut.json()["detail"]["code"] == "SPREAD_TOO_WIDE"


def test_rejects_naked_call_allows_covered_call(isolated_app) -> None:
    client, _, _ = isolated_app

    # Naked CE SELL -> blocked
    resp_naked = client.post(
        "/api/orders/stage",
        json=_valid_stage_payload(option_type="CE", side="SELL", is_covered_call=False),
    )
    assert resp_naked.status_code == 422
    assert resp_naked.json()["detail"]["code"] == "NAKED_CALL_FORBIDDEN"

    # Covered Call -> allowed
    resp_covered = client.post(
        "/api/orders/stage",
        json=_valid_stage_payload(option_type="CE", side="SELL", is_covered_call=True),
    )
    assert resp_covered.status_code == 200
    assert resp_covered.json()["status"] == "STAGED"


def test_aukaat_cap_4_naked_and_6_hedged(isolated_app) -> None:
    client, db_file, _ = isolated_app

    # Seed 2 open naked positions in SQLite
    with db_session(db_file) as conn:
        for sym in ("TCS", "INFY"):
            conn.execute(
                """
                INSERT INTO positions (symbol, strike, option_type, expiry, side, qty, entry_price, is_hedged, status)
                VALUES (?, 1500.0, 'PE', '25MAY', 'SELL', 100, 20.0, 0, 'OPEN')
                """,
                (sym,),
            )

    # Stage 2 more naked orders -> total naked = 4 (at cap)
    for sym in ("HDFCBANK", "ICICIBANK"):
        resp = client.post("/api/orders/stage", json=_valid_stage_payload(symbol=sym, is_hedged=False))
        assert resp.status_code == 200

    # 5th naked order -> blocked by ₹25L Aukaat naked cap
    resp_5th_naked = client.post(
        "/api/orders/stage",
        json=_valid_stage_payload(symbol="SBIN", is_hedged=False),
    )
    assert resp_5th_naked.status_code == 422
    assert resp_5th_naked.json()["detail"]["code"] == "AUKAAT_NAKED_CAP_EXCEEDED"

    # Hedged orders up to total 6 -> allowed (2 positions + 2 staged + 2 hedged = 6)
    for sym in ("LT", "AXISBANK"):
        resp_h = client.post("/api/orders/stage", json=_valid_stage_payload(symbol=sym, is_hedged=True))
        assert resp_h.status_code == 200

    # 7th total order -> blocked by ₹25L Aukaat hedged cap
    resp_7th = client.post(
        "/api/orders/stage",
        json=_valid_stage_payload(symbol="KOTAKBANK", is_hedged=True),
    )
    assert resp_7th.status_code == 422
    assert resp_7th.json()["detail"]["code"] == "AUKAAT_HEDGED_CAP_EXCEEDED"


def test_same_strike_rollover_and_far_future_pivot(isolated_app) -> None:
    client, _, _ = isolated_app

    # Roll down 1200 -> 1150 -> blocked
    resp_down = client.post(
        "/api/orders/rollover",
        json={
            "symbol": "RELIANCE",
            "old_strike": 1200.0,
            "new_strike": 1150.0,
            "option_type": "PE",
            "new_expiry": "25JUN",
            "side": "SELL",
            "qty": 500,
            "order_type": "LIMIT",
            "limit_price": 28.0,
            "bid_price": 27.5,
            "ask_price": 28.2,
            "pivot_to_far_future": False,
        },
    )
    assert resp_down.status_code == 422
    assert resp_down.json()["detail"]["code"] == "ROLL_DOWN_STRIKE_FORBIDDEN"

    # Exact same strike 1200 -> 1200 -> allowed
    resp_same = client.post(
        "/api/orders/rollover",
        json={
            "symbol": "RELIANCE",
            "old_strike": 1200.0,
            "new_strike": 1200.0,
            "option_type": "PE",
            "new_expiry": "25JUN",
            "side": "SELL",
            "qty": 500,
            "order_type": "LIMIT",
            "limit_price": 34.0,
            "bid_price": 33.5,
            "ask_price": 34.2,
            "pivot_to_far_future": False,
        },
    )
    assert resp_same.status_code == 200
    assert resp_same.json()["order"]["strike"] == 1200.0

    # Pivot to Far-Month Future -> allowed, stages FUT BUY
    resp_fut = client.post(
        "/api/orders/rollover",
        json={
            "symbol": "RELIANCE",
            "old_strike": 1200.0,
            "new_strike": 0.0,
            "option_type": "PE",
            "new_expiry": "25JUL",
            "side": "SELL",
            "qty": 500,
            "order_type": "LIMIT",
            "limit_price": 1210.0,
            "bid_price": 1208.0,
            "ask_price": 1212.0,
            "pivot_to_far_future": True,
        },
    )
    assert resp_fut.status_code == 200
    assert resp_fut.json()["order"]["option_type"] == "FUT"
    assert resp_fut.json()["order"]["side"] == "BUY"


def test_decay_lock_tiers_and_override_logging(isolated_app) -> None:
    client, db_file, _ = isolated_app

    # 1 day, 20% < 30% without override -> locked
    r1 = client.post(
        "/api/orders/decay-check",
        json={"days_held": 1, "decay_pct": 20.0, "is_expiry_week": False},
    )
    assert r1.status_code == 200
    assert r1.json()["locked"] is True
    assert r1.json()["requires_override"] is True
    assert r1.json()["required_target_pct"] == 30.0

    # 2-3 days, 45% >= 45% -> unlocked
    r2 = client.post(
        "/api/orders/decay-check",
        json={"days_held": 2, "decay_pct": 45.0, "is_expiry_week": False},
    )
    assert r2.status_code == 200
    assert r2.json()["locked"] is False
    assert r2.json()["allowed"] is True

    # Expiry week, 55% < 70% WITH override -> allowed and logged to lessons_log
    r3 = client.post(
        "/api/orders/decay-check",
        json={
            "days_held": 18,
            "decay_pct": 55.0,
            "is_expiry_week": True,
            "override_reason": "Major RBI event tomorrow, locking 55% early.",
            "position_id": 1,
        },
    )
    assert r3.status_code == 200
    body3 = r3.json()
    assert body3["locked"] is False
    assert body3["allowed"] is True
    assert body3["override_logged"] is True
    assert body3["required_target_pct"] == 70.0

    with db_session(db_file) as conn:
        log_row = conn.execute("SELECT * FROM lessons_log WHERE category = 'DECAY_OVERRIDE'").fetchone()
    assert log_row is not None
    assert "RBI event" in log_row["description"]


def test_manual_approval_and_kill_switch(isolated_app) -> None:
    client, db_file, app = isolated_app

    # Stage an order
    stage_resp = client.post("/api/orders/stage", json=_valid_stage_payload())
    assert stage_resp.status_code == 200
    order_id = stage_resp.json()["order"]["id"]

    # List staged orders
    list_resp = client.get("/api/orders/staged")
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] == 1

    # Approve without confirm_manual_approval=True -> blocked
    bad_approve = client.post(f"/api/orders/{order_id}/approve", json={"confirm_manual_approval": False})
    assert bad_approve.status_code == 422
    assert bad_approve.json()["detail"]["code"] == "MANUAL_APPROVAL_REQUIRED"

    # Approve with confirm_manual_approval=True -> APPROVED_DRY_RUN
    ok_approve = client.post(f"/api/orders/{order_id}/approve", json={"confirm_manual_approval": True})
    assert ok_approve.status_code == 200
    assert ok_approve.json()["mode"] == "DRY_RUN"
    assert ok_approve.json()["auto_fired"] is False
    assert ok_approve.json()["order"]["status"] == "APPROVED_DRY_RUN"

    # Kill switch without confirm_kill=True -> blocked
    bad_kill = client.post("/api/orders/kill-switch", json={"confirm_kill": False})
    assert bad_kill.status_code == 422
    assert bad_kill.json()["detail"]["code"] == "KILL_SWITCH_CONFIRMATION_REQUIRED"

    # Mock a live Kite client to verify kill switch cancels staged + live orders/GTTs
    cancelled_orders = []
    deleted_gtts = []

    class FakeKite:
        def orders(self):
            return [
                {"order_id": "ORD1", "status": "OPEN", "variety": "regular"},
                {"order_id": "ORD2", "status": "COMPLETE", "variety": "regular"},
            ]

        def cancel_order(self, variety, order_id):
            cancelled_orders.append((variety, order_id))

        def get_gtts(self):
            return [{"id": 901, "status": "active"}, {"id": 902, "status": "triggered"}]

        def delete_gtt(self, trigger_id):
            deleted_gtts.append(trigger_id)

    fake_service = SimpleNamespace(_is_live=lambda: True, _kite=FakeKite())
    app.dependency_overrides[get_kite_service] = lambda: fake_service
    try:
        kill_resp = client.post("/api/orders/kill-switch", json={"confirm_kill": True})
    finally:
        app.dependency_overrides.clear()

    assert kill_resp.status_code == 200
    kill_data = kill_resp.json()
    assert kill_data["kill_switch_triggered"] is True
    assert kill_data["cancelled_staged_count"] == 1
    assert kill_data["live_cancelled_orders"] == 1
    assert kill_data["live_cancelled_gtts"] == 1
    assert cancelled_orders == [("regular", "ORD1")]
    assert deleted_gtts == [901]

    with db_session(db_file) as conn:
        row = conn.execute("SELECT status FROM staged_orders WHERE id = ?", (order_id,)).fetchone()
    assert row["status"] == "CANCELLED_KILL_SWITCH"


def test_direct_service_guardrail_exceptions(tmp_path: Path) -> None:
    db_file = tmp_path / "direct.db"
    init_db(db_file)
    rules = load_rules_config()

    with pytest.raises(GuardrailViolationError) as exc_info:
        validate_order_request(
            OrderStageRequest(
                symbol="TCS",
                strike=3500.0,
                option_type="PE",
                expiry="25MAY",
                side="SELL",
                qty=175,
                order_type="MARKET",
                limit_price=50.0,
            ),
            rules=rules,
            db_path=db_file,
        )
    assert exc_info.value.code == "LIMIT_ONLY"

    res = check_decay_lock(
        days_held=15,
        decay_pct=49.0,
        is_expiry_week=False,
        override_reason=None,
        rules=rules,
        db_path=db_file,
    )
    assert res.locked is True
    assert res.required_target_pct == 50.0

    staged = stage_ato_gtt_order(
        OrderStageRequest(
            symbol="TCS",
            strike=3500.0,
            option_type="PE",
            expiry="25MAY",
            side="SELL",
            qty=175,
            order_type="LIMIT",
            limit_price=50.0,
            spread_pct=2.0,
        ),
        rules=rules,
        db_path=db_file,
    )
    assert staged["status"] == "STAGED"

    kill_res = trigger_kill_switch(confirm_kill=True, db_path=db_file)
    assert kill_res["cancelled_staged_count"] == 1
