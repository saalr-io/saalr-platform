from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from . import service
from .gating import require_ml_forecast

router = APIRouter(prefix="/v1/market", tags=["forecast"])


def _validate(ticker: str, market: str) -> None:
    if not ticker or not ticker.isalpha():
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "unknown ticker"}})
    if market not in ("US",):
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": "unsupported market"}})


@router.get("/vol-forecast")
async def vol_forecast_endpoint(
    request: Request,
    ticker: str = Query(...),
    market: str = Query("US"),
    horizon: int = Query(10, ge=1, le=30),
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    _validate(ticker, market)
    ticker = ticker.upper()
    session, _principal = ctx
    try:
        return await service.get_or_compute_forecast(
            request.app.state.redis,
            request.app.state.sessionmaker,
            session,
            ticker,
            market,
            horizon,
            request.app.state.vol_forecast_ttl,
        )
    except ValueError as exc:
        raise HTTPException(
            422, {"error": {"code": "INSUFFICIENT_HISTORY", "message": str(exc)}}
        ) from exc
