"""Dynamic Universe Manager (F40, E40, and All NSE F&O — strictly NO S200)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db import db_session
from app.kite_client import KiteService

UniverseType = Literal["F40", "E40", "NSE_FNO"]
ScannerSlicer = Literal["F40", "E40", "NSE_FNO", "INDICES"]
CapTier = Literal["large", "mid", "small"]

BASELINE_INDICES: list[dict[str, Any]] = [
    {
        "symbol": "NIFTY",
        "kite_spot": "NSE:NIFTY 50",
        "nfo_prefix": "NIFTY",
        "lot_size": 75,
        "sector": "Index",
        "cap_tier": "large",
        "instrument_type": "INDEX",
    },
    {
        "symbol": "BANKNIFTY",
        "kite_spot": "NSE:NIFTY BANK",
        "nfo_prefix": "BANKNIFTY",
        "lot_size": 30,
        "sector": "Index",
        "cap_tier": "large",
        "instrument_type": "INDEX",
    },
    {
        "symbol": "FINNIFTY",
        "kite_spot": "NSE:NIFTY FIN SERVICE",
        "nfo_prefix": "FINNIFTY",
        "lot_size": 65,
        "sector": "Index",
        "cap_tier": "large",
        "instrument_type": "INDEX",
    },
    {
        "symbol": "MIDCPNIFTY",
        "kite_spot": "NSE:NIFTY MID SELECT",
        "nfo_prefix": "MIDCPNIFTY",
        "lot_size": 120,
        "sector": "Index",
        "cap_tier": "mid",
        "instrument_type": "INDEX",
    },
]

# Baseline F40 (Flagship 40) & E40 (Emerging 40) — standalone copy, zero coupling.
BASELINE_F40: list[tuple[str, str, CapTier]] = [
    ("BAJAJ-AUTO", "AUTO", "large"),
    ("MARUTI", "AUTO", "large"),
    ("AXISBANK", "BANKS", "large"),
    ("HDFCBANK", "BANKS", "large"),
    ("ICICIBANK", "BANKS", "large"),
    ("KOTAKBANK", "BANKS", "large"),
    ("SBIN", "BANKS", "large"),
    ("LT", "CONGLOMERATE", "large"),
    ("RELIANCE", "CONGLOMERATE", "large"),
    ("TITAN", "CONSUMER PRODUCTS", "large"),
    ("HINDUNILVR", "FMCG", "large"),
    ("ITC", "FMCG", "large"),
    ("NESTLEIND", "FMCG", "large"),
    ("PIDILITIND", "FMCG", "large"),
    ("HCLTECH", "IT", "large"),
    ("INFY", "IT", "large"),
    ("TCS", "IT", "large"),
    ("BAJAJFINSV", "NBFC", "large"),
    ("BAJAJHLDNG", "NON-BANKING", "large"),
    ("BAJFINANCE", "NBFC", "large"),
    ("HDFCAMC", "NON-BANKING-AMC", "large"),
    ("HDFCLIFE", "NON-BANKING-INSURANCE", "large"),
    ("ASIANPAINT", "PAINT", "large"),
    ("HAVELLS", "CONSUMER PRODUCTS", "large"),
    ("PAGEIND", "CONSUMER PRODUCTS", "mid"),
    ("VOLTAS", "CONSUMER PRODUCTS", "mid"),
    ("COLPAL", "FMCG", "large"),
    ("DABUR", "FMCG", "large"),
    ("MARICO", "FMCG", "large"),
    ("PGHH", "FMCG", "mid"),
    ("ICICIGI", "NON-BANKING", "large"),
    ("NAM-INDIA", "NON-BANKING-AMC", "mid"),
    ("ICICILIFE", "NON-BANKING-INSURANCE", "large"),
    ("BERGEPAINT", "PAINT", "mid"),
    ("ABBOTINDIA", "PHARMA", "mid"),
    ("GLAXO", "PHARMA", "mid"),
    ("BATAINDIA", "CONSUMER PRODUCTS", "small"),
    ("GILLETTE", "FMCG", "mid"),
    ("PFIZER", "PHARMA", "small"),
    ("SANOFI", "PHARMA", "small"),
]

BASELINE_E40: list[tuple[str, str, CapTier]] = [
    ("EICHERMOT", "AUTO", "large"),
    ("HYUNDAI", "AUTO", "large"),
    ("M&M", "AUTO", "large"),
    ("VBL", "BEVERAGES", "large"),
    ("ULTRACEMCO", "CEMENT", "large"),
    ("DMART", "CONSUMER PRODUCT", "large"),
    ("GODREJCP", "CONSUMER PRODUCT", "large"),
    ("BSE", "FINANCIAL SERVICES", "mid"),
    ("JIOFIN", "FINANCIAL SERVICES", "large"),
    ("ADANIPORTS", "INFRA", "large"),
    ("CIPLA", "PHARMA", "large"),
    ("BOSCHLTD", "AUTO", "large"),
    ("MRF", "AUTO", "large"),
    ("UNITDSPR", "BEVERAGES", "large"),
    ("RADICO", "BEVERAGES", "mid"),
    ("UBL", "BEVERAGES", "mid"),
    ("BLUESTARCO", "CONSUMER PRODUCT", "mid"),
    ("DIXON", "CONSUMER PRODUCT", "mid"),
    ("BAJAJHFL", "FINANCIAL SERVICES", "mid"),
    ("MCX", "FINANCIAL SERVICES", "mid"),
    ("APOLLOHOSP", "HEALTHCARE", "large"),
    ("FORTIS", "HEALTHCARE", "mid"),
    ("INDHOTEL", "HOTEL", "large"),
    ("ITCHOTELS", "HOTEL", "mid"),
    ("JSWINFRA", "INFRA", "mid"),
    ("ACC", "CEMENT", "mid"),
    ("AWL", "CONSUMER PRODUCT", "mid"),
    ("HONAUT", "CONSUMER PRODUCT", "mid"),
    ("KAJARIACER", "CONSUMER PRODUCT", "small"),
    ("RELAXO", "CONSUMER PRODUCT", "small"),
    ("CDSL", "FINANCIAL SERVICES", "mid"),
    ("ANGELONE", "FINANCIAL SERVICES", "small"),
    ("CAMS", "FINANCIAL SERVICES", "small"),
    ("MEDANTA", "HEALTHCARE", "mid"),
    ("QUESS", "MANPOWER", "small"),
    ("TEAMLEASE", "MANPOWER", "small"),
    ("ASTRAZEN", "PHARMA", "small"),
    ("ERIS", "PHARMA", "small"),
    ("LALPATHLAB", "PHARMA", "small"),
    ("TMPV", "AUTO", "large"),
]


class UniverseStockInput(BaseModel):
    symbol: str = Field(..., min_length=1)
    cap_tier: CapTier = "large"
    sector: str = ""
    lot_size: int = 0


class UniverseReconcileRequest(BaseModel):
    universe_type: UniverseType
    stocks: list[UniverseStockInput]
    reason: str = "manual_update"


def seed_f40_e40_if_empty(db_path: str | Path | None = None) -> dict[str, int]:
    """Seed F40 and E40 baselines into universe_stocks if empty (idempotent)."""
    inserted = {"F40": 0, "E40": 0}
    with db_session(db_path) as conn:
        for u_type, rows in (("F40", BASELINE_F40), ("E40", BASELINE_E40)):
            existing = conn.execute(
                "SELECT COUNT(*) AS cnt FROM universe_stocks WHERE universe_type = ?",
                (u_type,),
            ).fetchone()["cnt"]
            if existing == 0:
                for symbol, sector, cap_tier in rows:
                    conn.execute(
                        """
                        INSERT INTO universe_stocks (symbol, universe_type, cap_tier, sector, is_active)
                        VALUES (?, ?, ?, ?, 1)
                        """,
                        (symbol.upper(), u_type, cap_tier, sector),
                    )
                    conn.execute(
                        """
                        INSERT INTO universe_changelog (symbol, universe_type, action, reason)
                        VALUES (?, ?, 'ADDED', 'baseline_seed')
                        """,
                        (symbol.upper(), u_type),
                    )
                    inserted[u_type] += 1
    return inserted


def reconcile_universe_list(
    universe_type: UniverseType,
    incoming: list[UniverseStockInput],
    reason: str = "sync",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Diff incoming list against active universe_stocks and log ADDED/RESTORED/REMOVED."""
    if universe_type not in ("F40", "E40", "NSE_FNO"):
        raise ValueError(f"Unsupported universe '{universe_type}'. Only F40, E40, NSE_FNO allowed (no S200).")

    incoming_map: dict[str, UniverseStockInput] = {}
    for item in incoming:
        sym = item.symbol.strip().upper()
        if sym:
            incoming_map[sym] = UniverseStockInput(
                symbol=sym,
                cap_tier=item.cap_tier,
                sector=item.sector,
                lot_size=item.lot_size,
            )

    added: list[str] = []
    restored: list[str] = []
    removed: list[str] = []

    with db_session(db_path) as conn:
        rows = conn.execute(
            "SELECT symbol, is_active FROM universe_stocks WHERE universe_type = ?",
            (universe_type,),
        ).fetchall()
        existing_active = {r["symbol"]: bool(r["is_active"]) for r in rows}

        # Additions & restorations
        for sym, item in incoming_map.items():
            if sym not in existing_active:
                conn.execute(
                    """
                    INSERT INTO universe_stocks (symbol, universe_type, cap_tier, sector, lot_size, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (sym, universe_type, item.cap_tier, item.sector, item.lot_size),
                )
                conn.execute(
                    """
                    INSERT INTO universe_changelog (symbol, universe_type, action, reason)
                    VALUES (?, ?, 'ADDED', ?)
                    """,
                    (sym, universe_type, reason),
                )
                added.append(sym)
            elif not existing_active[sym]:
                conn.execute(
                    """
                    UPDATE universe_stocks
                    SET is_active = 1, cap_tier = ?, sector = COALESCE(NULLIF(?, ''), sector),
                        lot_size = CASE WHEN ? > 0 THEN ? ELSE lot_size END,
                        removed_at = NULL
                    WHERE symbol = ? AND universe_type = ?
                    """,
                    (item.cap_tier, item.sector, item.lot_size, item.lot_size, sym, universe_type),
                )
                conn.execute(
                    """
                    INSERT INTO universe_changelog (symbol, universe_type, action, reason)
                    VALUES (?, ?, 'RESTORED', ?)
                    """,
                    (sym, universe_type, reason),
                )
                restored.append(sym)
            else:
                conn.execute(
                    """
                    UPDATE universe_stocks
                    SET lot_size = CASE WHEN ? > 0 THEN ? ELSE lot_size END
                    WHERE symbol = ? AND universe_type = ?
                    """,
                    (item.lot_size, item.lot_size, sym, universe_type),
                )

        # Removals
        for sym, is_active in existing_active.items():
            if is_active and sym not in incoming_map:
                conn.execute(
                    """
                    UPDATE universe_stocks
                    SET is_active = 0, removed_at = datetime('now')
                    WHERE symbol = ? AND universe_type = ?
                    """,
                    (sym, universe_type),
                )
                conn.execute(
                    """
                    INSERT INTO universe_changelog (symbol, universe_type, action, reason)
                    VALUES (?, ?, 'REMOVED', ?)
                    """,
                    (sym, universe_type, reason),
                )
                removed.append(sym)

    return {
        "universe_type": universe_type,
        "total_active": len(incoming_map),
        "added": sorted(added),
        "restored": sorted(restored),
        "removed": sorted(removed),
    }


def sync_nse_fno_from_kite(
    kite_service: KiteService | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Sync All NSE F&O stock underlyings from kite.instruments('NFO') with In/Out diffing."""
    seed_f40_e40_if_empty(db_path=db_path)
    service = kite_service or KiteService()
    if not service.is_connected() or service.kite is None:
        return {
            "synced": False,
            "mode": "offline",
            "message": "Kite not connected; connect daily OAuth to sync live NFO instruments.",
        }

    instruments = service.kite.instruments("NFO")
    # Build cap_tier lookup from F40/E40/fundamentals_cache
    cap_lookup: dict[str, CapTier] = {}
    with db_session(db_path) as conn:
        for r in conn.execute("SELECT symbol, cap_tier FROM universe_stocks WHERE is_active = 1"):
            cap_lookup[r["symbol"]] = r["cap_tier"]  # type: ignore[assignment]
        for r in conn.execute("SELECT symbol, cap_tier FROM fundamentals_cache"):
            cap_lookup[r["symbol"]] = r["cap_tier"]  # type: ignore[assignment]

    fno_stocks: dict[str, UniverseStockInput] = {}
    index_names = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}
    for inst in instruments:
        name = str(inst.get("name") or "").strip().upper()
        seg = str(inst.get("segment") or "").upper()
        if not name or name in index_names or "NFO" not in seg:
            continue
        lot_size = int(inst.get("lot_size") or 0)
        if name not in fno_stocks:
            fno_stocks[name] = UniverseStockInput(
                symbol=name,
                cap_tier=cap_lookup.get(name, "large"),
                lot_size=lot_size,
            )

    result = reconcile_universe_list(
        universe_type="NSE_FNO",
        incoming=list(fno_stocks.values()),
        reason="kite_nfo_sync",
        db_path=db_path,
    )
    return {"synced": True, "mode": "live", **result}


def list_universe_stocks(
    universe_type: UniverseType | None = None,
    cap_tier: CapTier | None = None,
    include_removed: bool = False,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return universe stocks filtered by universe (F40/E40/NSE_FNO) and cap_tier (large/mid/small)."""
    seed_f40_e40_if_empty(db_path=db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if universe_type:
        clauses.append("universe_type = ?")
        params.append(universe_type)
    if cap_tier:
        clauses.append("cap_tier = ?")
        params.append(cap_tier)
    if not include_removed:
        clauses.append("is_active = 1")

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db_session(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT symbol, universe_type, cap_tier, sector, lot_size, is_active, added_at, removed_at
            FROM universe_stocks
            {where_sql}
            ORDER BY universe_type, symbol
            """,
            tuple(params),
        ).fetchall()
    return [dict(r) for r in rows]


def get_universe_changelog(
    universe_type: UniverseType | None = None,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return recent In/Out additions, restorations, and removals."""
    seed_f40_e40_if_empty(db_path=db_path)
    with db_session(db_path) as conn:
        if universe_type:
            rows = conn.execute(
                """
                SELECT id, symbol, universe_type, action, reason, changed_at
                FROM universe_changelog
                WHERE universe_type = ?
                ORDER BY id DESC LIMIT ?
                """,
                (universe_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, symbol, universe_type, action, reason, changed_at
                FROM universe_changelog
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def list_indices() -> list[dict[str, Any]]:
    """Return baseline F&O index definitions for scanner INDICES slicer."""
    return [dict(item) for item in BASELINE_INDICES]
