from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal


async def require_ml_forecast(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    _session, principal = ctx
    if not entitlements_for(principal.tier)["ml_forecast"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": {
                    "code": "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO",
                    "message": "volatility forecasting requires a Pro or Premium plan",
                }
            },
        )
    yield ctx


async def require_price_forecast(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    _session, principal = ctx
    if not entitlements_for(principal.tier)["price_forecast"]:
        raise HTTPException(
            status_code=402,
            detail={"error": {"code": "ENTITLEMENT_PRICE_FORECAST_REQUIRES_PREMIUM",
                              "message": "AI price forecasts require a Premium plan"}},
        )
    yield ctx


async def require_news_sentiment(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    _session, principal = ctx
    if not entitlements_for(principal.tier)["news_sentiment"]:
        raise HTTPException(
            status_code=402,
            detail={"error": {"code": "ENTITLEMENT_NEWS_SENTIMENT_REQUIRES_PRO",
                              "message": "news sentiment requires a Pro or Premium plan"}},
        )
    yield ctx
