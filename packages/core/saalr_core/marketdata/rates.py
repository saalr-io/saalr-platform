from __future__ import annotations

import logging

import httpx

from .types import YieldCurve

_logger = logging.getLogger("saalr.marketdata.rates")
_FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED constant-maturity series -> tenor in years
_SERIES: dict[str, float] = {
    "DGS1MO": 1 / 12,
    "DGS3MO": 0.25,
    "DGS6MO": 0.5,
    "DGS1": 1.0,
    "DGS2": 2.0,
}


def latest_observation(payload: dict) -> tuple[str, float] | None:
    """Most-recent non-placeholder observation as (date, decimal_rate), or None."""
    for obs in reversed(payload.get("observations", [])):
        v = obs.get("value", ".")
        if v not in (".", "", None):
            return obs["date"], float(v) / 100.0
    return None


def build_curve(series: dict[str, tuple[str, float]]) -> YieldCurve:
    """series: series_id -> (date, decimal_rate). Returns a sorted YieldCurve."""
    points = sorted((_SERIES[sid], rate) for sid, (_d, rate) in series.items())
    curve_date = max(d for _d_unused, (d, _r) in series.items()) if series else ""
    return YieldCurve(curve_date=curve_date, points=points)


class FredRateProvider:
    def __init__(self, api_key: str | None, fallback_rate: float) -> None:
        self._api_key = api_key
        self._fallback = fallback_rate

    def _fallback_curve(self, reason: str) -> YieldCurve:
        _logger.warning("FRED unavailable (%s); using flat fallback %.4f", reason, self._fallback)
        return YieldCurve(curve_date="", points=[(1 / 12, self._fallback), (2.0, self._fallback)])

    async def get_curve(self) -> YieldCurve:
        if not self._api_key:
            return self._fallback_curve("no api key")
        series: dict[str, tuple[str, float]] = {}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for sid in _SERIES:
                    r = await client.get(
                        _FRED_URL,
                        params={
                            "series_id": sid,
                            "api_key": self._api_key,
                            "file_type": "json",
                            "sort_order": "asc",
                        },
                    )
                    r.raise_for_status()
                    obs = latest_observation(r.json())
                    if obs is not None:
                        series[sid] = obs
        except httpx.HTTPError as exc:
            return self._fallback_curve(str(exc))
        if not series:
            return self._fallback_curve("no observations")
        return build_curve(series)

    @property
    def source_name(self) -> str:
        return "fred" if self._api_key else "fallback"
