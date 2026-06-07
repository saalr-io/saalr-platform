from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from saalr_core.marketdata.provider import ProviderError

from .gating import require_vol_surface
from .service import MarketService

router = APIRouter(prefix="/v1/market", tags=["market"])


def _service(request: Request) -> MarketService:
    s = request.app.state
    return MarketService(s.market_provider, s.rate_provider, s.redis, s.vol_surface_ttl)


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


@router.get("/iv-surface")
async def iv_surface(
    request: Request,
    ticker: str = Query(...),
    market: str = Query("US"),
    ctx: tuple[AsyncSession, Principal] = Depends(require_vol_surface),
) -> dict:
    _validate(ticker, market)
    session, _principal = ctx
    try:
        return await _service(request).iv_surface(session, ticker, market)
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "MARKET_DATA_PROVIDER_UNAVAILABLE", "message": str(exc)}},
        ) from exc


@router.get("/chain")
async def chain(
    request: Request,
    ticker: str = Query(...),
    market: str = Query("US"),
    expiry: str | None = Query(None),
    ctx: tuple[AsyncSession, Principal] = Depends(require_vol_surface),
) -> dict:
    _validate(ticker, market)
    session, _principal = ctx
    try:
        return await _service(request).chain(session, ticker, market, expiry)
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "MARKET_DATA_PROVIDER_UNAVAILABLE", "message": str(exc)}},
        ) from exc
