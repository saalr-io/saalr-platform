from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import numpy as np

from saalr_ml.price_forecast import price_forecast

from . import repo


async def get_or_compute_price_forecast(
    redis, sessionmaker, session, ticker: str, market: str, horizon: int, ttl: int,
    *, closes: list[float] | None = None,
) -> dict:
    """Redis-cached ARIMA+LSTM+naive price forecast. Heavy training runs in a worker thread so it
    never blocks the event loop; persists per-model validation rows; raises ValueError on
    < 250 closes (the caller maps it to 422)."""
    key = f"mdq:pricefc:v1:{market}:{ticker}:{horizon}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    if closes is None:
        closes = await repo.load_closes(session, ticker, market)
    result = await asyncio.to_thread(price_forecast, np.asarray(closes, dtype=float), horizon)

    payload = {
        "ticker": ticker, "market": market,
        "as_of": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    mae = {m["model"]: m["holdout_mae"] for m in result["models"]}
    async with sessionmaker() as vsession, vsession.begin():
        for model_name in ("arima", "lstm"):
            await repo.record_validation(
                vsession,
                model_name=model_name,
                market=market,
                cohort_label=f"{ticker}:{repo.today_str()}",
                baseline_name="naive",
                status="passed" if result["primary_model"] == model_name else "failed",
                metric_summary_json={"holdout_mae": mae[model_name],
                                     "n_origins": result["validation"]["n_origins"]},
            )
    await redis.set(key, json.dumps(payload), ex=ttl)
    return payload
