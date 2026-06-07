from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.sentiment import repo as sentiment_repo

from ..auth import Principal
from ..forecast.gating import require_news_sentiment

router = APIRouter(prefix="/v1/market", tags=["sentiment"])


@router.get("/sentiment")
async def get_sentiment(
    ticker: str = Query(...),
    market: str = Query("US"),
    ctx: tuple[AsyncSession, Principal] = Depends(require_news_sentiment),
) -> dict:
    if not ticker or not ticker.isalpha():
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "unknown ticker"}})
    if market not in ("US",):
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": "unsupported market"}})
    session, _principal = ctx
    ticker = ticker.upper()
    row = await sentiment_repo.latest_sentiment(session, ticker, market)
    if row is None:
        return {
            "ticker": ticker, "market": market, "score": 0.0, "label": "neutral",
            "confident": False, "n_headlines": 0, "has_data": False,
            "computed_at": None, "as_of": None,
        }
    return {
        "ticker": ticker, "market": market, "score": row["score"], "label": row["label"],
        "confident": row["confident"], "n_headlines": row["n_headlines"], "has_data": True,
        "computed_at": row["computed_at"].isoformat(), "as_of": row["as_of"].isoformat(),
    }
