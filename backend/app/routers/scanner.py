"""Dhool Chaat After-Market Scanner API router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.config import RulesConfig, load_rules_config
from app.kite_client import KiteService
from app.routers.kite import get_kite_service
from app.services.fundamentals import (
    evaluate_fundamental_checks,
    evaluate_fundamental_pass,
    fetch_and_cache_fundamentals,
    hydrate_scanner_cache,
)
from app.services.scanner import (
    DhoolChaatScanner,
    ScannerResponse,
    StockCandidateInput,
)
from app.services.universe import CapTier, ScannerSlicer

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


class HydrateScannerRequest(BaseModel):
    """Request payload for hydrating scanner technicals/fundamentals cache."""

    symbols: list[str] | None = None
    include_indices: bool = True
    fetch_fundamentals: bool = False


def get_rules(request: Request) -> RulesConfig:
    """Return loaded RulesConfig from app state or load from YAML."""
    return getattr(request.app.state, "rules", load_rules_config())


@router.get("/candidates", response_model=ScannerResponse)
def get_scanner_candidates(
    include_rejected: bool = Query(default=True),
    universe_type: ScannerSlicer | None = Query(default=None),
    cap_tier: CapTier | None = Query(default=None),
    ppm_tier: str | None = Query(default=None),
    min_ath_drop_pct: float | None = Query(default=None, ge=0),
    min_52w_drop_pct: float | None = Query(default=None, ge=0),
    min_dma200_drop_pct: float | None = Query(default=None, ge=0),
    red_candle_only: bool = Query(default=False),
    min_intraday_drop_pct: float | None = Query(default=None, ge=0),
    max_spread_pct: float | None = Query(default=None, ge=0),
    refresh_live_quotes: bool = Query(default=False),
    rules: RulesConfig = Depends(get_rules),
    kite_service: KiteService = Depends(get_kite_service),
) -> ScannerResponse:
    """Scan F40 / E40 / All NSE F&O / INDICES universe (no S200) against Dhool Chaat + High-Vol Theta rules."""
    scanner = DhoolChaatScanner(rules=rules, kite_service=kite_service)
    return scanner.scan(
        include_rejected=include_rejected,
        universe_type=universe_type,
        cap_tier=cap_tier,
        ppm_tier=ppm_tier,
        min_ath_drop_pct=min_ath_drop_pct,
        min_52w_drop_pct=min_52w_drop_pct,
        min_dma200_drop_pct=min_dma200_drop_pct,
        red_candle_only=red_candle_only,
        min_intraday_drop_pct=min_intraday_drop_pct,
        max_spread_pct=max_spread_pct,
        refresh_live_quotes=refresh_live_quotes,
    )


@router.post("/evaluate", response_model=ScannerResponse)
def evaluate_candidates(
    candidates: list[StockCandidateInput],
    include_rejected: bool = Query(default=True),
    rules: RulesConfig = Depends(get_rules),
    kite_service: KiteService = Depends(get_kite_service),
) -> ScannerResponse:
    """Evaluate a custom list of StockCandidateInput against RulesConfig."""
    scanner = DhoolChaatScanner(rules=rules, kite_service=kite_service)
    return scanner.evaluate_list(candidates, include_rejected=include_rejected)


@router.post("/hydrate")
def hydrate_scanner(
    payload: HydrateScannerRequest | None = Body(default=None),
    kite_service: KiteService = Depends(get_kite_service),
) -> dict[str, Any]:
    """Hydrate scanner_technicals_cache (and optionally fundamentals_cache) for universe + indices."""
    req = payload or HydrateScannerRequest()
    return hydrate_scanner_cache(
        symbols=req.symbols,
        include_indices=req.include_indices,
        fetch_fundamentals=req.fetch_fundamentals,
        kite_service=kite_service,
    )


@router.post("/fundamentals/{symbol}")
def refresh_symbol_fundamentals(symbol: str) -> dict[str, Any]:
    """Fetch & cache Screener.in fundamentals on-demand for a single stock without auto-rejecting rows."""
    try:
        record = fetch_and_cache_fundamentals(symbol)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch Screener.in fundamentals for {symbol.upper()}: {exc}",
        ) from exc
    return {
        "symbol": record["symbol"],
        "fundamentals": record,
        "fundamental_checks": evaluate_fundamental_checks(record),
        "fundamental_passed": evaluate_fundamental_pass(record),
    }
