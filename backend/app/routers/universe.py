"""Universe API routes (F40, E40, All NSE F&O + Cap Slicers + In/Out Changelog)."""

from fastapi import APIRouter, Query

from app.services.universe import (
    CapTier,
    UniverseReconcileRequest,
    UniverseType,
    get_universe_changelog,
    list_universe_stocks,
    reconcile_universe_list,
    sync_nse_fno_from_kite,
)

router = APIRouter(prefix="/api/universe", tags=["universe"])


@router.get("")
def get_universe(
    universe_type: UniverseType | None = Query(default=None),
    cap_tier: CapTier | None = Query(default=None),
    include_removed: bool = Query(default=False),
) -> dict:
    """List active stocks filtered by universe (F40/E40/NSE_FNO) and cap_tier (large/mid/small)."""
    items = list_universe_stocks(
        universe_type=universe_type,
        cap_tier=cap_tier,
        include_removed=include_removed,
    )
    return {"count": len(items), "items": items}


@router.post("/reconcile")
def reconcile_universe(payload: UniverseReconcileRequest) -> dict:
    """Update F40, E40, or NSE_FNO list and record In/Out changelog."""
    return reconcile_universe_list(
        universe_type=payload.universe_type,
        incoming=payload.stocks,
        reason=payload.reason,
    )


@router.post("/sync-fno")
def sync_fno() -> dict:
    """Sync All NSE F&O underlyings from live Kite NFO instruments."""
    return sync_nse_fno_from_kite()


@router.get("/changelog")
def universe_changelog(
    universe_type: UniverseType | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """Return dynamic In/Out changelog for F40, E40, and NSE_FNO."""
    items = get_universe_changelog(universe_type=universe_type, limit=limit)
    return {"count": len(items), "items": items}
