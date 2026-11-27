"""Unit U2 validation tests: Zerodha Kite OAuth, dry-run fallback, live sync, and quotes."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import db_session, init_db
from app.kite_client import (
    KiteService,
    calculate_decay_pct,
    calculate_spread_pct,
    parse_nfo_symbol,
)
from app.main import create_app
from app.routers.kite import get_kite_service


def test_symbol_and_math_helpers() -> None:
    """Verify NFO symbol parsing, decay %, and bid-ask spread % calculations."""
    assert parse_nfo_symbol("RELIANCE25MAY1200PE") == ("RELIANCE", 1200.0, "PE", "25MAY")
    assert parse_nfo_symbol("TCS25MAYFUT") == ("TCS", 0.0, "FUT", "25MAY")
    assert calculate_decay_pct(100.0, 40.0, "SELL") == 60.0
    assert calculate_spread_pct(95.0, 100.0) == 5.0
    assert calculate_spread_pct(0.0, 100.0) == 100.0


def test_dry_run_endpoints_and_sqlite_sync(tmp_path: Path, monkeypatch) -> None:
    """All /api/kite endpoints return dry_run fallback and sync trades idempotently to SQLite."""
    db_file = tmp_path / "u2_dry_run.db"
    session_file = tmp_path / ".kite_session.json"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.setenv("KITE_API_KEY", "")
    monkeypatch.setenv("KITE_API_SECRET", "")
    get_settings.cache_clear()
    init_db(db_file)

    app = create_app()
    app.dependency_overrides[get_kite_service] = lambda: KiteService(
        settings=get_settings(),
        session_path=session_file,
        db_path=db_file,
    )

    try:
        with TestClient(app) as client:
            status_resp = client.get("/api/kite/status")
            assert status_resp.status_code == 200
            status_data = status_resp.json()
            assert status_data["connected"] is False
            assert status_data["mode"] == "dry_run"
            assert status_data["is_dry_run"] is True
            assert "access_token" not in status_data

            login_resp = client.get("/api/kite/login-url")
            assert login_resp.status_code == 200
            assert login_resp.json()["is_dry_run"] is True

            margins_resp = client.get("/api/kite/margins")
            assert margins_resp.status_code == 200
            margins = margins_resp.json()
            assert margins["is_dry_run"] is True
            assert margins["total_available"] > 0

            pnl_resp = client.get("/api/kite/pnl")
            assert pnl_resp.status_code == 200
            pnl = pnl_resp.json()
            assert pnl["is_dry_run"] is True
            assert pnl["total_pnl"] == pnl["realized_pnl"] + pnl["unrealized_mtm"]

            orders_resp = client.get("/api/kite/orders")
            assert orders_resp.status_code == 200
            orders = orders_resp.json()
            assert orders["is_dry_run"] is True
            assert len(orders["open_orders"]) >= 1
            assert len(orders["gtts"]) >= 1

            # Sync twice to verify idempotency in SQLite
            trades_resp1 = client.get("/api/kite/trades")
            trades_resp2 = client.get("/api/kite/trades")
            assert trades_resp1.status_code == 200
            assert trades_resp2.status_code == 200
            trades_data = trades_resp2.json()
            assert len(trades_data["active_trades"]) == 2
            assert len(trades_data["closed_trades"]) == 1

            with db_session(db_file) as conn:
                pos_count = conn.execute("SELECT COUNT(*) FROM positions WHERE status = 'OPEN'").fetchone()[0]
                hist_count = conn.execute("SELECT COUNT(*) FROM trades_history").fetchone()[0]
                assert pos_count == 2
                assert hist_count == 1

            quote_resp = client.get("/api/kite/quote?symbols=NFO:RELIANCE25MAY1200PE,NSE:RELIANCE")
            assert quote_resp.status_code == 200
            quote_data = quote_resp.json()
            assert quote_data["is_dry_run"] is True
            q = quote_data["quotes"]["NFO:RELIANCE25MAY1200PE"]
            assert q["best_bid"] > 0
            assert q["best_ask"] > q["best_bid"]
            assert q["bid_ask_spread_pct"] <= 5.0
    finally:
        get_settings.cache_clear()


def test_oauth_exchange_and_live_mode(tmp_path: Path, monkeypatch) -> None:
    """OAuth callback/session persists token securely and live endpoints never leak secrets."""
    db_file = tmp_path / "u2_live.db"
    session_file = tmp_path / ".kite_session.json"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.setenv("KITE_API_KEY", "test_api_key")
    monkeypatch.setenv("KITE_API_SECRET", "super_secret_value")
    get_settings.cache_clear()
    init_db(db_file)

    mock_kite = MagicMock()
    mock_kite.login_url.return_value = "https://kite.zerodha.com/connect/login?api_key=test_api_key&v=3"
    mock_kite.generate_session.return_value = {
        "access_token": "live_access_token_xyz",
        "user_id": "ZR1234",
    }
    mock_kite.margins.return_value = {
        "available": {"cash": 500000.0, "collateral": 1500000.0},
        "utilised": {"debits": 300000.0},
        "net": 1700000.0,
    }
    mock_kite.positions.return_value = {
        "net": [
            {
                "tradingsymbol": "INFY25MAY1400PE",
                "quantity": -400,
                "average_price": 30.0,
                "last_price": 15.0,
                "unrealised": 6000.0,
                "realised": 0.0,
            },
            {
                "tradingsymbol": "TCS25MAY3400PE",
                "quantity": 0,
                "sell_quantity": 175,
                "buy_quantity": 175,
                "sell_price": 50.0,
                "buy_price": 20.0,
                "realised": 5250.0,
            },
        ]
    }
    mock_kite.orders.return_value = [
        {
            "order_id": "2505010001",
            "tradingsymbol": "INFY25MAY1400PE",
            "exchange": "NFO",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "product": "NRML",
            "quantity": 400,
            "price": 12.0,
            "status": "OPEN",
        }
    ]
    mock_kite.get_gtts.return_value = [
        {
            "id": 777,
            "type": "single",
            "status": "active",
            "condition": {
                "exchange": "NFO",
                "tradingsymbol": "INFY25MAY1400PE",
                "trigger_values": [12.5],
            },
            "orders": [{"price": 12.2}],
        }
    ]
    mock_kite.quote.return_value = {
        "NFO:INFY25MAY1400PE": {
            "last_price": 15.0,
            "volume": 50000,
            "oi": 200000,
            "depth": {
                "buy": [{"price": 14.8}],
                "sell": [{"price": 15.2}],
            },
        }
    }

    monkeypatch.setattr("app.kite_client.KiteConnect", lambda api_key: mock_kite)

    app = create_app()
    app.dependency_overrides[get_kite_service] = lambda: KiteService(
        settings=get_settings(),
        session_path=session_file,
        db_path=db_file,
    )

    try:
        with TestClient(app) as client:
            login_resp = client.get("/api/kite/login-url")
            assert login_resp.status_code == 200
            assert "kite.zerodha.com" in login_resp.json()["login_url"]

            cb_resp = client.get("/api/kite/callback?request_token=req_abc_123")
            assert cb_resp.status_code == 200
            cb_data = cb_resp.json()
            assert cb_data["connected"] is True
            assert cb_data["mode"] == "live"
            assert cb_data["is_dry_run"] is False
            assert cb_data["user_id"] == "ZR1234"
            assert "live_access_token_xyz" not in cb_resp.text
            assert "super_secret_value" not in cb_resp.text

            saved = json.loads(session_file.read_text(encoding="utf-8"))
            assert saved["access_token"] == "live_access_token_xyz"
            assert saved["user_id"] == "ZR1234"

            pnl_resp = client.get("/api/kite/pnl")
            assert pnl_resp.status_code == 200
            assert pnl_resp.json()["mode"] == "live"
            assert pnl_resp.json()["realized_pnl"] == 5250.0
            assert pnl_resp.json()["unrealized_mtm"] == 6000.0
            assert pnl_resp.json()["positions_count"] == 1

            trades_resp = client.get("/api/kite/trades")
            assert trades_resp.status_code == 200
            assert len(trades_resp.json()["active_trades"]) == 1
            assert len(trades_resp.json()["closed_trades"]) == 1

            quote_resp = client.get("/api/kite/quote?symbols=NFO:INFY25MAY1400PE")
            assert quote_resp.status_code == 200
            q = quote_resp.json()["quotes"]["NFO:INFY25MAY1400PE"]
            assert q["best_bid"] == 14.8
            assert q["best_ask"] == 15.2
            assert q["bid_ask_spread_pct"] == 2.63
    finally:
        get_settings.cache_clear()
