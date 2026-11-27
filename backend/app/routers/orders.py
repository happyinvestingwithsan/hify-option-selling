"""ATO / GTT Staging, Guardrails, Rollover, Decay Lock & Kill Switch API router."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import RulesConfig, load_rules_config
from app.kite_client import KiteService
from app.routers.kite import get_kite_service
from app.services.guardrails import (
    ApproveOrderRequest,
    DecayCheckRequest,
    DecayLockResult,
    GuardrailViolationError,
    KillSwitchRequest,
    OrderStageRequest,
    RolloverStageRequest,
    approve_staged_order,
    check_decay_lock,
    check_physical_delivery_guard,
    get_capital_capacity,
    list_staged_orders,
    stage_ato_gtt_order,
    stage_rollover_order,
    trigger_kill_switch,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])


def get_rules(request: Request) -> RulesConfig:
    """Return loaded RulesConfig from app state or load from YAML."""
    return getattr(request.app.state, "rules", load_rules_config())


def get_db_path(request: Request) -> str | Path | None:
    """Return configured db_path from app state if present."""
    return getattr(request.app.state, "db_path", None)


@router.get("/capacity")
def get_capacity(
    nifty_at_ath: bool = False,
    rules: RulesConfig = Depends(get_rules),
    kite_service: KiteService = Depends(get_kite_service),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Capital-First capacity check: Aukaat slots, Nifty ATH 50% cut, and Kite margin."""
    return get_capital_capacity(
        rules=rules,
        kite_service=kite_service,
        nifty_at_ath=nifty_at_ath,
        db_path=db_path,
    )


@router.get("/delivery-check")
def delivery_check(
    days_to_expiry: int,
    option_type: str = "PE",
    moneyness: str = "ITM",
    rules: RulesConfig = Depends(get_rules),
) -> dict[str, Any]:
    """Check Physical Delivery Guard for near-expiry options."""
    return check_physical_delivery_guard(
        days_to_expiry=days_to_expiry,
        option_type=option_type.upper(),  # type: ignore[arg-type]
        moneyness=moneyness.upper(),  # type: ignore[arg-type]
        rules=rules,
    )


@router.get("/staged")
def get_staged_orders(
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """List all staged ATO/GTT orders."""
    orders = list_staged_orders(db_path=db_path)
    return {"count": len(orders), "orders": orders}


@router.post("/stage")
def stage_order(
    payload: OrderStageRequest,
    rules: RulesConfig = Depends(get_rules),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Validate hard guardrails and stage a Limit-only ATO/GTT order."""
    try:
        order = stage_ato_gtt_order(request=payload, rules=rules, db_path=db_path)
        return {"status": "STAGED", "order": order}
    except GuardrailViolationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.post("/{order_id}/approve")
def approve_order(
    order_id: int,
    payload: ApproveOrderRequest,
    kite_service: KiteService = Depends(get_kite_service),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Explicitly approve a staged order (dry-run or live-prepared, never auto-fired)."""
    try:
        return approve_staged_order(
            order_id=order_id,
            confirm_manual_approval=payload.confirm_manual_approval,
            execute_live=payload.execute_live,
            kite_service=kite_service,
            db_path=db_path,
        )
    except GuardrailViolationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.post("/rollover")
def rollover_order(
    payload: RolloverStageRequest,
    rules: RulesConfig = Depends(get_rules),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Validate Same-Strike Rollover Lock and stage rollover or Far-Month Future order."""
    try:
        order = stage_rollover_order(request=payload, rules=rules, db_path=db_path)
        return {"status": "STAGED", "order": order}
    except GuardrailViolationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc


@router.post("/decay-check", response_model=DecayLockResult)
def decay_check(
    payload: DecayCheckRequest,
    rules: RulesConfig = Depends(get_rules),
    db_path: str | Path | None = Depends(get_db_path),
) -> DecayLockResult:
    """Evaluate Decay Lock target and log early-exit override reason if provided."""
    return check_decay_lock(
        days_held=payload.days_held,
        decay_pct=payload.decay_pct,
        is_expiry_week=payload.is_expiry_week,
        override_reason=payload.override_reason,
        rules=rules,
        db_path=db_path,
        position_id=payload.position_id,
    )


@router.post("/kill-switch")
def kill_switch(
    payload: KillSwitchRequest,
    kite_service: KiteService = Depends(get_kite_service),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Trigger emergency Kill Switch to cancel all staged orders and live pending orders/GTTs."""
    try:
        return trigger_kill_switch(
            confirm_kill=payload.confirm_kill,
            kite_service=kite_service,
            db_path=db_path,
        )
    except GuardrailViolationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_dict()) from exc
