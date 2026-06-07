from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.strategies.types import OptionLeg
from saalr_core.sentiment import repo as sentiment_repo
from saalr_ml.montecarlo import monte_carlo_pop, sentiment_adjusted_drift

from ..auth import Principal
from ..forecast import repo as forecast_repo
from ..forecast import service as forecast_service
from ..forecast.gating import require_ml_forecast
from .schemas import MonteCarloRequest

SENTIMENT_MAX_AGE_HOURS = 168

router = APIRouter(prefix="/v1/strategies", tags=["montecarlo"])


def _err(code: str, msg: str, status: int = 422) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message": msg}})


@router.post("/montecarlo")
async def montecarlo(
    body: MonteCarloRequest,
    request: Request,
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    session, _principal = ctx
    config = body.config.to_domain()
    legs = config.legs
    underlying = config.underlying.upper()
    market = body.market
    if market not in ("US",):
        raise _err("VALIDATION_INVALID_PARAMETER", "unsupported market", 400)

    today = datetime.now(timezone.utc).date()
    option_expiries = [date.fromisoformat(leg.expiry) for leg in legs if isinstance(leg, OptionLeg)]
    if not option_expiries:
        raise _err("VALIDATION_NO_EXPIRY", "strategy has no option legs with an expiry")
    days = (min(option_expiries) - today).days
    if days < 1:
        raise _err("VALIDATION_NO_EXPIRY", "nearest option expiry is not in the future")
    t_years = days / 365.0

    closes = await forecast_repo.load_closes(session, underlying, market)
    if not closes:
        raise _err("INSUFFICIENT_HISTORY", f"no bars for {underlying}")
    spot = closes[-1]

    if body.sigma is not None:
        sigma = float(body.sigma)
        sigma_source = "override"
    else:
        try:
            payload = await forecast_service.get_or_compute_forecast(
                request.app.state.redis,
                request.app.state.sessionmaker,
                session,
                underlying,
                market,
                days,
                request.app.state.vol_forecast_ttl,
                closes=closes,  # reuse the spot load; keeps spot + sigma on one snapshot
            )
        except ValueError as exc:
            raise _err("INSUFFICIENT_HISTORY", str(exc)) from exc
        sigma = float(np.mean(payload["primary_forecast"])) / 100.0
        sigma_source = "garch"

    curve = await request.app.state.rate_provider.get_curve()
    rate = curve.rate_for(t_years) if t_years > 0 else 0.0

    drift_adjust = 0.0
    sentiment_out: dict = {"applied": False, "reason": "not_requested"}
    if body.use_sentiment:
        sent = await sentiment_repo.latest_sentiment(session, underlying, market)
        if sent is None:
            sentiment_out = {"applied": False, "reason": "no_data"}
        elif not sent["confident"]:
            sentiment_out = {"applied": False, "reason": "low_confidence"}
        else:
            age_h = (datetime.now(timezone.utc) - sent["computed_at"]).total_seconds() / 3600.0
            if age_h > SENTIMENT_MAX_AGE_HOURS:
                sentiment_out = {"applied": False, "reason": "stale"}
            else:
                drift_adjust = sentiment_adjusted_drift(sent["score"], sigma, t_years)
                sentiment_out = {
                    "applied": True, "score": sent["score"], "label": sent["label"],
                    "computed_at": sent["computed_at"].isoformat(),
                }

    result = monte_carlo_pop(
        legs, spot, t_years, sigma, rate, drift_adjust=drift_adjust, paths=body.paths, seed=body.seed
    )
    return {
        **result,
        "underlying": underlying,
        "market": market,
        "spot": spot,
        "sigma": sigma,
        "sigma_source": sigma_source,
        "horizon_days": days,
        "rate": rate,
        "sentiment": sentiment_out,
    }
