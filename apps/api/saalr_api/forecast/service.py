from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from saalr_ml.forecast import vol_forecast

from . import repo


async def get_or_compute_forecast(
    redis, sessionmaker, session, ticker: str, market: str, horizon: int, ttl: int
) -> dict:
    """Return the GARCH vol-forecast payload for (ticker, market, horizon): a Redis cache
    read, else compute via vol_forecast (raises ValueError on <250 closes — the caller maps
    it to 422), persist a model_validation_runs row in its own committed session, and cache.
    Shared by the forecast endpoint and the Monte-Carlo endpoint."""
    key = f"mdq:volfc:v1:{market}:{ticker}:{horizon}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    closes = await repo.load_closes(session, ticker, market)
    result = vol_forecast(np.asarray(closes, dtype=float), horizon)

    payload = {
        "ticker": ticker,
        "market": market,
        "as_of": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    async with sessionmaker() as vsession, vsession.begin():
        await repo.record_validation(
            vsession,
            model_name="garch",
            market=market,
            cohort_label=f"{ticker}:{repo.today_str()}",
            baseline_name="hv21",
            status="passed" if result["primary_model"] == "garch" else "failed",
            metric_summary_json={**result["validation"], "params": result["params"]},
        )
    await redis.set(key, json.dumps(payload), ex=ttl)
    return payload
