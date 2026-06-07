from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal
from . import service

router = APIRouter(prefix="/v1/market", tags=["regime"])


def _validate(ticker: str, market: str) -> None:
    if not ticker or not ticker.isalpha():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": "unknown ticker"}},
        )
    if market not in ("US",):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": "unsupported market"}},
        )


@router.get("/regime")
async def regime_endpoint(
    request: Request,
    ticker: str = Query(...),
    market: str = Query("US"),
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> dict:
    _validate(ticker, market)
    ticker = ticker.upper()
    session, principal = ctx
    has_premium = bool(entitlements_for(principal.tier)["ml_forecast"])
    try:
        return await service.get_or_compute_regime(
            request.app.state.redis, session, ticker, market, has_premium,
            request.app.state.regime_ttl,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "INSUFFICIENT_HISTORY", "message": str(exc)}},
        ) from exc
