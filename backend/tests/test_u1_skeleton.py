"""Unit U1 validation tests: FastAPI skeleton, config loader, SQLite schema, and .gitignore."""

import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient

from app.config import PROJECT_ROOT, load_rules_config
from app.db import init_db
from app.main import create_app


EXPECTED_TABLES = {
    "positions",
    "staged_orders",
    "paper_trades",
    "lessons_log",
    "trades_history",
}


def test_health_and_rules_endpoints(tmp_path: Path, monkeypatch) -> None:
    """FastAPI boots via lifespan, initializes SQLite, and exposes non-secret config."""
    db_file = tmp_path / "u1_test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            health_resp = client.get("/health")
            assert health_resp.status_code == 200
            health_data = health_resp.json()
            assert health_data["status"] == "ok"
            assert health_data["db_initialized"] is True
            assert health_data["capital_tier"] == "25L"
            assert health_data["max_naked_positions"] == 4
            assert health_data["max_hedged_positions"] == 6

            rules_resp = client.get("/api/config/rules")
            assert rules_resp.status_code == 200
            rules_data = rules_resp.json()
            assert rules_data["capital"]["tier"] == "25L"
            assert rules_data["entry_triggers"]["order_type"] == "LIMIT"
            assert rules_data["entry_triggers"]["max_option_bid_ask_spread_pct"] == 5.0
            assert rules_data["rollover"]["allow_roll_down_strike"] is False
            assert "KITE_API_KEY" not in rules_data
            assert "KITE_API_SECRET" not in rules_data
    finally:
        get_settings.cache_clear()


def test_rules_yaml_fallback_and_override(tmp_path: Path) -> None:
    """load_rules_config falls back to config/rules.example.yaml when rules.yaml is absent."""
    missing_path = tmp_path / "missing_rules.yaml"
    fallback_cfg = load_rules_config(missing_path)
    assert fallback_cfg.capital.tier == "25L"
    assert fallback_cfg.capital.max_naked_positions == 4

    custom_path = tmp_path / "custom_rules.yaml"
    custom_path.write_text(
        "capital:\n  tier: '12L'\n  max_naked_positions: 2\n  max_hedged_positions: 3\n",
        encoding="utf-8",
    )
    custom_cfg = load_rules_config(custom_path)
    assert custom_cfg.capital.tier == "12L"
    assert custom_cfg.capital.max_naked_positions == 2


def test_sqlite_init_creates_expected_tables(tmp_path: Path) -> None:
    """init_db creates all 5 core tables in SQLite."""
    db_file = tmp_path / "schema_check.db"
    resolved = init_db(db_file)
    assert resolved.exists()

    conn = sqlite3.connect(str(resolved))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        ).fetchall()
        table_names = {row[0] for row in rows}
    finally:
        conn.close()

    assert EXPECTED_TABLES.issubset(table_names)


def test_env_is_gitignored() -> None:
    """Verify .env is listed in .gitignore."""
    gitignore_path = PROJECT_ROOT / ".gitignore"
    assert gitignore_path.exists()
    lines = [line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()]
    assert ".env" in lines
