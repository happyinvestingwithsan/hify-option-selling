"""Zerodha Kite Connect OAuth, live P&L, orders, trades sync, margins, and quotes router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.kite_client import KiteService

router = APIRouter(prefix="/api/kite", tags=["kite"])


class SessionExchangeRequest(BaseModel):
    """Payload for exchanging a Zerodha Kite request_token via SPA."""

    request_token: str = Field(..., min_length=1, description="Daily Kite OAuth request_token")


def get_kite_service() -> KiteService:
    """Dependency returning a KiteService configured from current settings."""
    return KiteService()


@router.get("/login-url")
def get_login_url(service: KiteService = Depends(get_kite_service)) -> dict[str, Any]:
    """Return the Zerodha Kite OAuth login URL."""
    return service.get_login_url()


@router.get("/callback")
def kite_oauth_callback(
    request_token: str = Query(..., min_length=1),
    redirect_to: str | None = Query(default=None),
    service: KiteService = Depends(get_kite_service),
) -> Any:
    """Exchange Kite request_token for an access_token and persist session."""
    try:
        status = service.exchange_request_token(request_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Kite session exchange failed: {type(exc).__name__}") from exc

    if redirect_to:
        return RedirectResponse(url=redirect_to, status_code=302)
    return status


@router.post("/session")
def exchange_session(
    payload: SessionExchangeRequest,
    service: KiteService = Depends(get_kite_service),
) -> dict[str, Any]:
    """Exchange request_token from JSON body for SPA convenience."""
    try:
        return service.exchange_request_token(payload.request_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Kite session exchange failed: {type(exc).__name__}") from exc


@router.get("/status")
def get_kite_status(service: KiteService = Depends(get_kite_service)) -> dict[str, Any]:
    """Return current Kite connection and dry-run/live mode status."""
    return service.get_status()


@router.get("/margins")
def get_kite_margins(service: KiteService = Depends(get_kite_service)) -> dict[str, Any]:
    """Return equity margins (available cash, collateral pledged, utilised, total)."""
    return service.get_margins()


@router.get("/pnl")
def get_kite_pnl(service: KiteService = Depends(get_kite_service)) -> dict[str, Any]:
    """Return realized P&L, unrealized MTM, total P&L, and open positions count."""
    return service.get_pnl()


@router.get("/orders")
def get_kite_orders(service: KiteService = Depends(get_kite_service)) -> dict[str, Any]:
    """Return open/pending orders and active GTT triggers."""
    return service.get_orders()


@router.get("/trades")
def get_kite_trades(service: KiteService = Depends(get_kite_service)) -> dict[str, Any]:
    """Fetch open positions and closed trades, sync to SQLite, and return both."""
    return service.get_trades_and_sync()


@router.get("/quote")
def get_kite_quote(
    symbols: str = Query(..., min_length=1, description="Comma-separated Kite instrument symbols"),
    service: KiteService = Depends(get_kite_service),
) -> dict[str, Any]:
    """Fetch read-only quotes with best bid/ask and bid_ask_spread_pct."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="At least one symbol is required.")
    return service.get_quote(symbol_list)
