"""Tests for Unit U8: Retrospective Rulebook Audit & Lessons Learnt."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import get_settings
from app.db import db_session, init_db
from app.main import create_app
from app.services.retrospective import LessonCreateRequest, create_lesson


def _build_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path]:
    db_file = tmp_path / "u8_test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    get_settings.cache_clear()
    init_db(db_file)
    app = create_app()
    return TestClient(app), db_file


def test_premature_exit_missed_profit_and_discipline_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Premature exit below decay target flags PREMATURE_EXIT and calculates missed profit."""
    client, db_file = _build_client(tmp_path, monkeypatch)
    with client:
        with db_session(db_file) as conn:
            conn.execute(
                """
                INSERT INTO trades_history (
                    symbol, strike, option_type, expiry, side, qty,
                    entry_price, exit_price, realized_pnl, decay_pct, exit_reason
                )
                VALUES ('DABUR', 510, 'PE', '26DEC', 'SELL', 500, 100.0, 80.0, 10000.0, 20.0, 'IMPATIENCE')
                """
            )

        resp = client.get("/api/retrospective/audit")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_trades_audited"] == 1
        assert data["violations_count"] == 1
        assert data["discipline_score_pct"] < 100.0
        # Expected target = 50%, actual = 20% -> (30 / 100) * 100 * 500 = 15000.0
        assert data["total_missed_profit_inr"] == 15000.0
        assert len(data["findings"]) == 1
        finding = data["findings"][0]
        assert finding["rule_violated"] == "PREMATURE_EXIT"
        assert finding["missed_profit_inr"] == 15000.0
        assert "Hold for target decay unless thesis breaks." in data["recommendations"]


def test_clean_trade_scores_100_percent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trade closed at or above decay target produces 0 violations and 100% discipline score."""
    client, db_file = _build_client(tmp_path, monkeypatch)
    with client:
        with db_session(db_file) as conn:
            conn.execute(
                """
                INSERT INTO trades_history (
                    symbol, strike, option_type, expiry, side, qty,
                    entry_price, exit_price, realized_pnl, decay_pct, exit_reason
                )
                VALUES ('HDFCBANK', 1600, 'PE', '26DEC', 'SELL', 550, 40.0, 18.0, 12100.0, 55.0, 'DECAY_TARGET_BOOKED')
                """
            )

        resp = client.get("/api/retrospective/audit")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_trades_audited"] == 1
        assert data["violations_count"] == 0
        assert data["discipline_score_pct"] == 100.0
        assert data["total_missed_profit_inr"] == 0.0
        assert data["findings"] == []


def test_lessons_crud_and_append_to_doc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify GET/POST /api/lessons and optional markdown append."""
    client, db_file = _build_client(tmp_path, monkeypatch)
    with client:
        empty_resp = client.get("/api/lessons")
        assert empty_resp.status_code == 200
        assert empty_resp.json()["count"] == 0

        post_resp = client.post(
            "/api/lessons",
            json={
                "category": "IMPATIENCE",
                "title": "Exited DABUR 510 PE at 20% decay",
                "description": "Closed early instead of waiting for 50% GTT.",
                "mistake_type": "EARLY_EXIT",
                "rule_added": "Enforce Decay Lock modal",
                "append_to_doc": False,
            },
        )
        assert post_resp.status_code == 200
        created = post_resp.json()["lesson"]
        assert created["title"] == "Exited DABUR 510 PE at 20% decay"
        assert created["category"] == "IMPATIENCE"

        list_resp = client.get("/api/lessons")
        assert list_resp.status_code == 200
        body = list_resp.json()
        assert body["count"] == 1
        assert body["lessons"][0]["id"] == created["id"]

        # Test append_to_doc using an isolated temp markdown file
        temp_doc = tmp_path / "LESSONS_TEST.md"
        temp_doc.write_text("# Lessons\n", encoding="utf-8")
        appended = create_lesson(
            req=LessonCreateRequest(
                category="DISCIPLINE",
                title="Do not roll down strike",
                description="Kept same strike during pullback.",
                rule_added="Same-Strike Validator",
                append_to_doc=True,
            ),
            db_path=db_file,
            lessons_doc_path=temp_doc,
        )
        doc_text = temp_doc.read_text(encoding="utf-8")
        assert f"LL-{appended['id']:03d}" in doc_text
        assert "Do not roll down strike" in doc_text
