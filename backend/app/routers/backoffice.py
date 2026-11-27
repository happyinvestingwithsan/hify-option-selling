"""Back Office API router: Console Tradebook + P&L import & Kite trades() sync (Unit U9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, Field

from app.kite_client import KiteService
from app.services.backoffice import (
    create_delivery_adjustment,
    delete_delivery_adjustment,
    get_backoffice_summary,
    import_from_folder,
    import_pnl_xlsx,
    import_tradebook_xlsx,
    list_delivery_adjustments,
    sync_kite_daily_trades,
)


class DeliveryAdjustmentCreate(BaseModel):
    underlying: str = Field(..., min_length=1, max_length=32)
    fno_contract: str = Field(default="", max_length=64)
    fno_strike: float = Field(..., gt=0)
    fno_expiry: str = Field(default="", max_length=20)
    qty: int = Field(..., gt=0)
    equity_sell_price: float = Field(..., ge=0)
    equity_sell_date: str = Field(..., min_length=8, max_length=20)
    equity_order_id: str = Field(default="", max_length=64)
    equity_trade_ids: str = Field(default="", max_length=256)
    charges: float = Field(default=0.0, ge=0)
    console_fifo_pnl: float | None = Field(default=None)
    reason: str = Field(default="MISSED_ROLLOVER_DELIVERY", max_length=64)
    notes: str = Field(default="", max_length=500)

router = APIRouter(prefix="/api/backoffice", tags=["backoffice"])
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB


async def _read_validated_xlsx(upload: UploadFile, label: str) -> bytes:
    """Validate .xlsx filename and enforce max upload size before parsing."""
    filename = (upload.filename or "").strip()
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be an .xlsx file.",
        )
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"{label} exceeds maximum allowed size of 15 MB.",
        )
    if not data:
        raise HTTPException(status_code=400, detail=f"{label} is empty.")
    return data


def get_db_path(request: Request) -> str | Path | None:
    """Return configured db_path from app state if present."""
    return getattr(request.app.state, "db_path", None)


def get_kite_service(request: Request) -> KiteService:
    """Return a KiteService bound to app.state.db_path if configured."""
    db_path = getattr(request.app.state, "db_path", None)
    return KiteService(db_path=db_path)


@router.get("/summary")
def backoffice_summary(
    symbol: str | None = Query(default=None, description="Optional symbol filter"),
    kite_service: KiteService = Depends(get_kite_service),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Return calibrated Console P&L summary, unified Kite delta, ticker grouping, and recent fills."""
    return get_backoffice_summary(
        symbol_filter=symbol,
        db_path=db_path,
        kite_service=kite_service,
    )


@router.post("/import-local")
def backoffice_import_local(
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Import Console Tradebook and P&L .xlsx files from Console_Reports/FY2627_FNO."""
    try:
        return import_from_folder(db_path=db_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload")
async def backoffice_upload(
    tradebook_file: UploadFile | None = File(default=None),
    pnl_file: UploadFile | None = File(default=None),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Upload Console Tradebook .xlsx and/or P&L .xlsx for catch-up import."""
    if tradebook_file is None and pnl_file is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one file: tradebook_file or pnl_file.",
        )

    result: dict[str, Any] = {"tradebook": None, "pnl": None}

    try:
        if tradebook_file is not None:
            tb_bytes = await _read_validated_xlsx(tradebook_file, "tradebook_file")
            result["tradebook"] = {
                "filename": tradebook_file.filename,
                **import_tradebook_xlsx(tb_bytes, source="CONSOLE", db_path=db_path),
            }
        if pnl_file is not None:
            pnl_bytes = await _read_validated_xlsx(pnl_file, "pnl_file")
            result["pnl"] = {
                "filename": pnl_file.filename,
                **import_pnl_xlsx(pnl_bytes, db_path=db_path),
            }
    except (ValueError, BadZipFile, InvalidFileException) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result


@router.post("/sync-kite-trades")
def backoffice_sync_kite_trades(
    kite_service: KiteService = Depends(get_kite_service),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Sync today's executed NFO trades from Kite Connect trades() into console_fills."""
    return sync_kite_daily_trades(kite_service=kite_service, db_path=db_path)


@router.get("/delivery-adjustments")
def backoffice_list_delivery_adjustments(
    symbol: str | None = Query(default=None, description="Optional underlying filter"),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """List physical-delivery forced equity exit adjustments."""
    items = list_delivery_adjustments(symbol_filter=symbol, db_path=db_path)
    return {"items": items, "count": len(items)}


@router.post("/delivery-adjustments")
def backoffice_create_delivery_adjustment(
    payload: DeliveryAdjustmentCreate,
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Record a physical-delivery forced equity exit (Option A economic P&L)."""
    try:
        item = create_delivery_adjustment(
            underlying=payload.underlying,
            fno_strike=payload.fno_strike,
            qty=payload.qty,
            equity_sell_price=payload.equity_sell_price,
            equity_sell_date=payload.equity_sell_date,
            fno_contract=payload.fno_contract,
            fno_expiry=payload.fno_expiry,
            equity_order_id=payload.equity_order_id,
            equity_trade_ids=payload.equity_trade_ids,
            charges=payload.charges,
            console_fifo_pnl=payload.console_fifo_pnl,
            reason=payload.reason,
            notes=payload.notes,
            db_path=db_path,
        )
        return {"item": item}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/delivery-adjustments/{adjustment_id}")
def backoffice_delete_delivery_adjustment(
    adjustment_id: int,
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Delete a delivery equity adjustment by ID."""
    deleted = delete_delivery_adjustment(adjustment_id=adjustment_id, db_path=db_path)
    if not deleted:
        raise HTTPException(status_code=404, detail="Delivery adjustment not found.")
    return {"deleted": True, "id": adjustment_id}
