from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_ml.forecast import vol_forecast

from ..auth import Principal
from . import repo
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
    redis = request.app.state.redis
    ttl = request.app.state.vol_forecast_ttl
    key = f"mdq:volfc:v1:{market}:{ticker}:{horizon}"

    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    closes = await repo.load_closes(session, ticker, market)
    try:
        result = vol_forecast(np.asarray(closes, dtype=float), horizon)
    except ValueError as exc:
        raise HTTPException(
            422, {"error": {"code": "INSUFFICIENT_HISTORY", "message": str(exc)}}
        ) from exc

    payload = {
        "ticker": ticker,
        "market": market,
        "as_of": datetime.now(timezone.utc).isoformat(),
        **result,
    }

    await repo.record_validation(
        session,
        model_name="garch",
        market=market,
        cohort_label=f"{ticker}:{repo.today_str()}",
        baseline_name="hv21",
        status="passed" if result["primary_model"] == "garch" else "failed",
        metric_summary_json={**result["validation"], "params": result["params"]},
    )

    await redis.set(key, json.dumps(payload), ex=ttl)
    return payload
