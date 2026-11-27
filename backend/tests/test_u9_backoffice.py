"""Unit U9 tests: Back Office Console Tradebook + P&L importer & Kite trades() sync."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT
from app.db import db_session, init_db
from app.main import app
from app.services.backoffice import (
    get_backoffice_summary,
    import_from_folder,
    import_pnl_xlsx,
    import_tradebook_xlsx,
)

CONSOLE_DIR = PROJECT_ROOT / "Console_Reports" / "FY2627_FNO"
TRADEBOOK_XLSX = CONSOLE_DIR / "tradebook-MV4345-FO_26_Nov_26.xlsx"
PNL_XLSX = CONSOLE_DIR / "pnl-MV4345_26_Nov_2026.xlsx"


@pytest.fixture()
def temp_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "test_u9.db"
    init_db(db_file)
    return db_file


def test_import_real_tradebook_and_deduplication(temp_db: Path) -> None:
    assert TRADEBOOK_XLSX.exists(), f"Missing fixture: {TRADEBOOK_XLSX}"
    tb_bytes = TRADEBOOK_XLSX.read_bytes()

    first = import_tradebook_xlsx(tb_bytes, source="CONSOLE", db_path=temp_db)
    assert first["total_rows_parsed"] == 136
    assert first["inserted_fills"] == 136
    assert first["skipped_duplicates"] == 0
    assert first["closed_trades_reconstructed"] > 0

    # Re-importing the exact same file must be 100% idempotent
    second = import_tradebook_xlsx(tb_bytes, source="CONSOLE", db_path=temp_db)
    assert second["total_rows_parsed"] == 136
    assert second["inserted_fills"] == 0
    assert second["skipped_duplicates"] == 136

    with db_session(temp_db) as conn:
        fills_cnt = conn.execute("SELECT COUNT(*) FROM console_fills").fetchone()[0]
        bo_trades_cnt = conn.execute(
            "SELECT COUNT(*) FROM trades_history WHERE kite_trade_id LIKE 'BO:%'"
        ).fetchone()[0]

    assert fills_cnt == 136
    assert bo_trades_cnt == first["closed_trades_reconstructed"]


def test_import_real_pnl_calibrated_values(temp_db: Path) -> None:
    assert PNL_XLSX.exists(), f"Missing fixture: {PNL_XLSX}"
    pnl_bytes = PNL_XLSX.read_bytes()

    res = import_pnl_xlsx(pnl_bytes, db_path=temp_db)
    assert res["realized_pnl"] == pytest.approx(-15778.75, abs=1e-4)
    assert res["charges"] == pytest.approx(6858.6005, abs=1e-4)
    assert res["other_credit_debit"] == pytest.approx(47.2, abs=1e-4)
    assert res["unrealized_pnl"] == pytest.approx(125180.0, abs=1e-4)
    assert res["net_realized_pnl"] == pytest.approx(-15778.75 - 6858.6005 + 47.2, abs=1e-4)
    assert res["charges_heads_count"] >= 8
    assert res["symbols_upserted"] > 0

    summary = get_backoffice_summary(db_path=temp_db)
    assert summary["summary"]["has_pnl_data"] is True
    assert summary["summary"]["realized_pnl"] == pytest.approx(-15778.75, abs=1e-4)
    assert summary["summary"]["charges"] == pytest.approx(6858.6005, abs=1e-4)
    assert summary["charges_breakdown"]["Brokerage - Z"] == pytest.approx(2540.0, abs=1e-4)


def test_import_from_folder_and_api_endpoints(
    temp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app.state.db_path = str(temp_db)
    client = TestClient(app)

    # 1. Import via /api/backoffice/import-local
    resp_local = client.post("/api/backoffice/import-local")
    assert resp_local.status_code == 200
    body_local = resp_local.json()
    assert len(body_local["tradebook_files"]) == 1
    assert len(body_local["pnl_files"]) == 1
    assert body_local["tradebook_files"][0]["inserted_fills"] == 136
    assert body_local["pnl_files"][0]["realized_pnl"] == pytest.approx(-15778.75, abs=1e-4)

    # 2. Query /api/backoffice/summary with and without symbol filter
    resp_sum = client.get("/api/backoffice/summary")
    assert resp_sum.status_code == 200
    sum_data = resp_sum.json()
    assert sum_data["total_fills_count"] == 136
    assert sum_data["reconstructed_trades_count"] > 0
    assert sum_data["summary"]["realized_pnl"] == pytest.approx(-15778.75, abs=1e-4)
    assert sum_data["summary"]["charges"] == pytest.approx(6858.6005, abs=1e-4)

    resp_filtered = client.get("/api/backoffice/summary?symbol=COLPAL")
    assert resp_filtered.status_code == 200
    filtered_data = resp_filtered.json()
    assert len(filtered_data["symbol_pnl"]) > 0
    assert all("COLPAL" in row["symbol"] for row in filtered_data["symbol_pnl"])
    assert all("COLPAL" in row["symbol"] for row in filtered_data["recent_fills"])

    # 3. Upload endpoint deduplication check
    with TRADEBOOK_XLSX.open("rb") as tb_f, PNL_XLSX.open("rb") as pnl_f:
        resp_upload = client.post(
            "/api/backoffice/upload",
            files={
                "tradebook_file": (
                    TRADEBOOK_XLSX.name,
                    tb_f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                "pnl_file": (
                    PNL_XLSX.name,
                    pnl_f,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )
    assert resp_upload.status_code == 200
    up_data = resp_upload.json()
    assert up_data["tradebook"]["skipped_duplicates"] == 136
    assert up_data["pnl"]["realized_pnl"] == pytest.approx(-15778.75, abs=1e-4)

    # 4. Sync Kite daily trades (dry_run mode, deterministic regardless of local .kite_session.json)
    monkeypatch.setattr("app.kite_client.KiteService._is_live", lambda self: False)
    resp_sync = client.post("/api/backoffice/sync-kite-trades")
    assert resp_sync.status_code == 200
    assert resp_sync.json()["mode"] == "dry_run"

    # 5. Verify /api/retrospective/audit picks up reconstructed BO: trades
    resp_audit = client.get("/api/retrospective/audit")
    assert resp_audit.status_code == 200
    assert resp_audit.json()["total_trades_audited"] > 0


def test_unified_kite_sync_and_ticker_grouping(
    temp_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify Console + Kite Live unified ledger, live unrealized MTM, and underlying ticker grouping."""
    from datetime import date

    app.state.db_path = str(temp_db)
    client = TestClient(app)

    # Seed Console baseline
    assert client.post("/api/backoffice/import-local").status_code == 200

    today = date.today().isoformat()

    class FakeKite:
        def trades(self):
            return [
                {
                    "exchange": "NFO",
                    "tradingsymbol": "TMPV26NOV800PE",
                    "transaction_type": "SELL",
                    "quantity": 500,
                    "average_price": 20.0,
                    "trade_id": "KITE-T1",
                    "order_id": "KITE-O1",
                    "fill_timestamp": f"{today}T10:00:00",
                },
                {
                    "exchange": "NFO",
                    "tradingsymbol": "TMPV26NOV800PE",
                    "transaction_type": "BUY",
                    "quantity": 500,
                    "average_price": 10.0,
                    "trade_id": "KITE-T2",
                    "order_id": "KITE-O2",
                    "fill_timestamp": f"{today}T14:00:00",
                },
            ]

        def positions(self):
            return {
                "net": [
                    {
                        "exchange": "NFO",
                        "tradingsymbol": "TMPV26DEC820PE",
                        "quantity": -500,
                        "average_price": 25.0,
                        "last_price": 21.0,
                        "unrealized": 2000.0,
                        "m2m": 2000.0,
                        "product": "NRML",
                    }
                ]
            }

    monkeypatch.setattr("app.kite_client.KiteService._load_session", lambda self: None)
    monkeypatch.setattr("app.kite_client.KiteService._is_live", lambda self: True)

    def _inject_fake_kite(self, *args, **kwargs):
        self._kite = FakeKite()

    from app.kite_client import KiteService

    orig_init = KiteService.__init__

    def _patched_init(self, db_path=None):
        orig_init(self, db_path=db_path)
        self._kite = FakeKite()

    monkeypatch.setattr(KiteService, "__init__", _patched_init)

    sync_resp = client.post("/api/backoffice/sync-kite-trades")
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()
    assert sync_data["mode"] == "live"
    assert sync_data["synced_fills"] == 2
    assert sync_data["open_positions_count"] == 1
    assert sync_data["live_unrealized_pnl"] == pytest.approx(2000.0, abs=1e-4)

    # Summary must unify Console baseline (-15778.75) + Kite delta (+5000.0) and use live unrealized (2000.0)
    sum_resp = client.get("/api/backoffice/summary?symbol=TMPV")
    assert sum_resp.status_code == 200
    body = sum_resp.json()

    unified = body["unified_summary"]
    assert unified["console_realized_pnl"] == pytest.approx(-15778.75, abs=1e-4)
    assert unified["kite_live_delta_realized_pnl"] == pytest.approx(5000.0, abs=1e-4)
    assert unified["total_realized_pnl"] == pytest.approx(-10778.75, abs=1e-4)
    assert unified["unrealized_pnl"] == pytest.approx(2000.0, abs=1e-4)
    assert unified["unrealized_source"] == "KITE_LIVE"

    sync_status = body["sync_status"]
    assert sync_status["synced_today"] is True
    assert sync_status["kite_connected"] is True
    assert sync_status["today_review"]["fills_today"] == 2
    assert sync_status["today_review"]["realized_today"] == pytest.approx(5000.0, abs=1e-4)

    # Ticker grouping for TMPV
    tmpv_rows = [r for r in body["ticker_pnl"] if r["ticker"] == "TMPV"]
    assert len(tmpv_rows) == 1
    tmpv = tmpv_rows[0]
    assert tmpv["realized_pnl"] >= 5000.0 - 1e6  # includes any Console TMPV + 5000 Kite live
    assert tmpv["unrealized_pnl"] == pytest.approx(2000.0, abs=1e-4)
    assert tmpv["net_pnl"] == pytest.approx(tmpv["realized_pnl"] + 2000.0, abs=1e-4)
    assert tmpv["status"] in {"PROFIT", "LOSS"}
    assert tmpv["contracts_count"] >= 2


def test_delivery_equity_adjustments_option_a(temp_db: Path) -> None:
    """Delivery equity exits compute Option A P&L, integrate into summary/ticker, and support delete."""
    app.state.db_path = temp_db
    client = TestClient(app)
    # Create DABUR & TMPV delivery exits
    r1 = client.post(
        "/api/backoffice/delivery-adjustments",
        json={
            "underlying": "DABUR",
            "fno_contract": "DABUR26NOV420PE",
            "fno_strike": 420.0,
            "fno_expiry": "2026-11-23",
            "qty": 1250,
            "equity_sell_price": 404.05,
            "equity_sell_date": "2026-11-25",
            "equity_order_id": "1100000004009422",
            "equity_trade_ids": "200700604",
            "charges": 2686.66,
            "console_fifo_pnl": -31020.20,
            "reason": "MISSED_ROLLOVER_DELIVERY",
        },
    )
    assert r1.status_code == 200
    item1 = r1.json()["item"]
    assert item1["economic_pnl"] == pytest.approx(-22624.16, abs=1e-2)
    assert item1["equity_handoff_status"] == "BOOKED_IN_OPTIONS"

    r2 = client.post(
        "/api/backoffice/delivery-adjustments",
        json={
            "underlying": "TMPV",
            "fno_contract": "TMPV26NOV320PE",
            "fno_strike": 320.0,
            "fno_expiry": "2026-11-23",
            "qty": 1600,
            "equity_sell_price": 258.15,
            "equity_sell_date": "2026-11-25",
            "equity_order_id": "1300000002889418",
            "charges": 2537.64,
            "console_fifo_pnl": -109417.61,
        },
    )
    assert r2.status_code == 200
    item2 = r2.json()["item"]
    assert item2["economic_pnl"] == pytest.approx(-101497.64, abs=1e-2)

    # Verify summary includes delivery_equity_pnl = -124121.80 and separate DELIVERY_CHARGES row
    sum_resp = client.get("/api/backoffice/summary")
    assert sum_resp.status_code == 200
    body = sum_resp.json()
    assert body["unified_summary"]["delivery_equity_price_pnl"] == pytest.approx(-118897.50, abs=1e-2)
    assert body["unified_summary"]["delivery_equity_charges"] == pytest.approx(5224.30, abs=1e-2)
    assert body["unified_summary"]["delivery_equity_pnl"] == pytest.approx(-124121.80, abs=1e-2)
    assert body["unified_summary"]["delivery_adjustments_count"] == 2
    assert len(body["delivery_adjustments"]) == 2
    dabur_ticker = [t for t in body["ticker_pnl"] if t["ticker"] == "DABUR"][0]
    assert any(c["source"] == "DELIVERY_CHARGES" and c["realized_pnl"] == pytest.approx(-2686.66, abs=1e-2) for c in dabur_ticker["contracts"])

    # Delete one and verify cleanup
    del_resp = client.delete(f"/api/backoffice/delivery-adjustments/{item1['id']}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    list_resp = client.get("/api/backoffice/delivery-adjustments")
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] == 1
