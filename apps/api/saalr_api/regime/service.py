from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from saalr_core.marketdata.bars import load_closes
from saalr_core.sentiment import repo as sentiment_repo
from saalr_core.strategies.recommend import recommend
from saalr_core.strategies.templates import list_templates
from saalr_ml.forecast import vol_forecast
from saalr_ml.regime import classify_regime, vol_trend_label


async def _premium_signals(session, ticker: str, market: str, closes, realized_vol: float) -> dict:
    vol_trend = {"label": "stable", "available": False, "detail": "needs 250+ daily bars"}
    try:
        fc = vol_forecast(np.asarray(closes, dtype=float), 10)
        garch_mean = float(np.mean(fc["primary_forecast"]))
        vol_trend = {
            "label": vol_trend_label(garch_mean, realized_vol), "available": True,
            "detail": f"GARCH 10-day forecast {garch_mean:.1f}% vs realized {realized_vol:.1f}%",
        }
    except ValueError:
        pass

    srow = await sentiment_repo.latest_sentiment(session, ticker, market)
    if srow is None:
        sentiment = {"label": "neutral", "score": 0.0, "available": False,
                     "n_headlines": 0, "detail": "no recent scored headlines"}
    else:
        sentiment = {
            "label": srow["label"], "score": srow["score"], "available": True,
            "n_headlines": srow["n_headlines"],
            "detail": f"{srow['n_headlines']} headlines, score {srow['score']:+.2f}",
        }
    return {"vol_trend": vol_trend, "sentiment": sentiment}


async def get_or_compute_regime(redis, session, ticker: str, market: str,
                                has_premium: bool, ttl: int) -> dict:
    """Regime + recommendations for (ticker, market). Cache read, else load free bars,
    classify (ValueError <60 closes → caller maps 422), conditionally enrich with the
    premium layer, recommend, cache. Cache key includes the tier so a free read never
    serves premium fields and vice versa."""
    key = f"mdq:regime:v1:{market}:{ticker}:{'premium' if has_premium else 'base'}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)

    closes = await load_closes(session, ticker, market)
    regime = classify_regime(closes)

    if has_premium:
        regime["premium"] = await _premium_signals(
            session, ticker, market, closes, regime["volatility"]["realized_vol"])
    else:
        regime["premium"] = None
    regime["premium_available"] = has_premium

    recommendations = recommend(regime, list_templates())
    payload = {
        "ticker": ticker, "market": market,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "regime": regime, "recommendations": recommendations, "approximate": True,
    }
    await redis.set(key, json.dumps(payload), ex=ttl)
    return payload
