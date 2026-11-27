"""Isolated Paper / Strategy Lab API router (Unit U5).

Strictly isolated from live order/GTT placement and cancellation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import RulesConfig, load_rules_config
from app.kite_client import KiteService
from app.services.paper_lab import (
    PaperCloseRequest,
    PaperLabError,
    PaperRolloverRequest,
    PaperSimulateTickRequest,
    PaperTradeCreateRequest,
    close_paper_trade,
    create_paper_trade,
    list_paper_trades,
    simulate_ato_and_decay,
    simulate_same_strike_rollover,
)

router = APIRouter(prefix="/api/paper", tags=["paper"])


def get_rules(request: Request) -> RulesConfig:
    """Return loaded RulesConfig from app state or load from YAML."""
    return getattr(request.app.state, "rules", load_rules_config())


def get_db_path(request: Request) -> str | Path | None:
    """Return configured db_path from app state if present."""
    return getattr(request.app.state, "db_path", None)


def get_read_only_kite_service() -> KiteService:
    """Return KiteService instance used strictly for read-only quote lookups."""
    return KiteService()


@router.get("/trades")
def get_paper_trades(
    status: str | None = Query(default=None),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """List simulated Paper Lab trades and portfolio summary."""
    return list_paper_trades(status=status, db_path=db_path)


@router.post("/trades")
def post_paper_trade(
    payload: PaperTradeCreateRequest,
    rules: RulesConfig = Depends(get_rules),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Create a simulated Paper Lab trade in local SQLite."""
    try:
        trade = create_paper_trade(req=payload, rules=rules, db_path=db_path)
        return {"status": trade["status"], "trade": trade}
    except PaperLabError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.post("/trades/{trade_id}/simulate")
def post_simulate_trade(
    trade_id: int,
    payload: PaperSimulateTickRequest,
    rules: RulesConfig = Depends(get_rules),
    kite_service: KiteService = Depends(get_read_only_kite_service),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Simulate ATO trigger activation and option decay for a Paper Lab trade."""
    try:
        return simulate_ato_and_decay(
            trade_id=trade_id,
            req=payload,
            rules=rules,
            kite_service=kite_service,
            db_path=db_path,
        )
    except PaperLabError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.post("/trades/{trade_id}/rollover")
def post_rollover_trade(
    trade_id: int,
    payload: PaperRolloverRequest,
    rules: RulesConfig = Depends(get_rules),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Simulate Same-Strike Rollover or Far-Month Future pivot in local SQLite."""
    try:
        return simulate_same_strike_rollover(
            trade_id=trade_id,
            req=payload,
            rules=rules,
            db_path=db_path,
        )
    except PaperLabError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.post("/trades/{trade_id}/close")
def post_close_trade(
    trade_id: int,
    payload: PaperCloseRequest,
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Close a Paper Lab trade and record realized P&L and early-exit flags."""
    try:
        return close_paper_trade(trade_id=trade_id, req=payload, db_path=db_path)
    except PaperLabError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc
