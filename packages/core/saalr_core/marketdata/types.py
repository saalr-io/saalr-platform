from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

from saalr_core.pricing.types import OptionKind


@dataclass(frozen=True)
class RawContract:
    expiry: str  # YYYY-MM-DD
    strike: float
    kind: OptionKind
    bid: float | None
    ask: float | None
    last: float | None
    volume: int | None
    open_interest: int | None
    vendor_iv: float | None
    vendor_delta: float | None
    vendor_gamma: float | None
    vendor_theta: float | None
    vendor_vega: float | None


@dataclass(frozen=True)
class RawChain:
    underlying: str
    market: str
    as_of: str  # RFC3339
    spot: float
    div_yield: float
    contracts: list[RawContract]


@dataclass(frozen=True)
class YieldCurve:
    curve_date: str  # YYYY-MM-DD
    points: list[tuple[float, float]] = field(default_factory=list)  # (t_years, rate_decimal), sorted

    def rate_for(self, t_years: float) -> float:
        pts = self.points
        if not pts:
            raise ValueError("empty yield curve")
        if t_years <= pts[0][0]:
            return pts[0][1]
        if t_years >= pts[-1][0]:
            return pts[-1][1]
        ts = [t for t, _ in pts]
        i = bisect_left(ts, t_years)
        t0, r0 = pts[i - 1]
        t1, r1 = pts[i]
        return r0 + (r1 - r0) * (t_years - t0) / (t1 - t0)
