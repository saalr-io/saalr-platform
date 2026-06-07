from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from saalr_core.marketdata.backfill import backfill_symbol
from saalr_core.marketdata.provider import ProviderError

from ..market.service import MarketService


def require_dev(request: Request) -> None:
    """Block all dev-seed routes unless the API is running in dev auth mode."""
    if request.app.state.settings.auth_provider != "dev":
        raise HTTPException(status_code=404, detail="not found")


router = APIRouter(prefix="/v1/dev", tags=["dev"], dependencies=[Depends(require_dev)])


class SeedBarsBody(BaseModel):
    ticker: str
    days: int = 400


class SeedChainBody(BaseModel):
    ticker: str


def _norm_ticker(ticker: str) -> str:
    t = ticker.strip().upper()
    if not t or not t.isalpha():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "RESOURCE_NOT_FOUND", "message": "unknown ticker"}},
        )
    return t


@router.post("/seed/bars")
async def seed_bars(body: SeedBarsBody, request: Request) -> dict:
    ticker = _norm_ticker(body.ticker)
    days = max(1, min(body.days, 3650))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    sm = request.app.state.sessionmaker
    try:
        async with sm() as session:
            async with session.begin():
                n = await backfill_symbol(
                    session, request.app.state.aggregates_provider, ticker, "US", start, today
                )
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "MARKET_DATA_PROVIDER_UNAVAILABLE", "message": str(exc)}},
        ) from exc
    return {"symbol": ticker, "rows_upserted": n, "first": start.isoformat(), "last": today.isoformat()}


@router.post("/seed/chain")
async def seed_chain(body: SeedChainBody, request: Request) -> dict:
    ticker = _norm_ticker(body.ticker)
    s = request.app.state
    svc = MarketService(s.market_provider, s.rate_provider, s.redis, s.vol_surface_ttl)
    sm = s.sessionmaker
    try:
        async with sm() as session:
            async with session.begin():
                payload = await svc.capture_snapshot(session, ticker, "US")
                total = (await session.execute(
                    text("SELECT count(DISTINCT ts) FROM options_chain_snapshots "
                         "WHERE underlying = :u AND market = :m"),
                    {"u": ticker, "m": "US"},
                )).scalar_one()
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "MARKET_DATA_PROVIDER_UNAVAILABLE", "message": str(exc)}},
        ) from exc
    return {
        "ticker": ticker,
        "as_of": payload["as_of"],
        "contracts": len(payload["contracts"]),
        "total_snapshots": total,
    }
