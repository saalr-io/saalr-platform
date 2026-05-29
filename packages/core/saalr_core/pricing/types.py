from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OptionKind(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


@dataclass(frozen=True)
class OptionParams:
    """Inputs to a pricing model. Rates/yields are decimals (0.05 = 5%); t_years in years."""

    spot: float
    strike: float
    t_years: float
    rate: float
    sigma: float
    div_yield: float
    kind: OptionKind


@dataclass(frozen=True)
class Greeks:
    """Per trader conventions: theta per calendar day, vega per 1 vol point (0.01),
    rho per 1 rate point (0.01). delta/gamma are raw."""

    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    iv: float | None = None


@dataclass(frozen=True)
class ContractGreeks:
    """A single option contract: market quote + OUR computed numbers + the VENDOR's."""

    expiry: str  # ISO date YYYY-MM-DD
    strike: float
    kind: OptionKind
    bid: float | None
    ask: float | None
    last: float | None
    volume: int | None
    open_interest: int | None
    ours: Greeks
    vendor_iv: float | None
    vendor_delta: float | None
    vendor_gamma: float | None
    vendor_theta: float | None
    vendor_vega: float | None
