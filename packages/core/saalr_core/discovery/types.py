from __future__ import annotations

from dataclasses import dataclass

from saalr_core.strategies.types import OptionType, StrategyConfig


@dataclass(frozen=True)
class Quote:
    """One raw option quote off a snapshot, before gating."""
    expiry: str            # YYYY-MM-DD
    strike: float
    kind: OptionType
    bid: float | None
    ask: float | None
    iv: float | None
    volume: int | None
    open_interest: int | None


@dataclass(frozen=True)
class CleanContract:
    """A quote that passed the DATA-3 sanity gate; carries a usable mid."""
    expiry: str
    strike: float
    kind: OptionType
    mid: float
    iv: float | None
    volume: int | None
    open_interest: int | None


@dataclass(frozen=True)
class CleanChain:
    underlying: str
    as_of: str
    spot: float
    div_yield: float
    contracts: tuple[CleanContract, ...]

    def expiries(self) -> list[str]:
        return sorted({c.expiry for c in self.contracts})

    def strikes_for_expiry(self, expiry: str) -> list[float]:
        return sorted({c.strike for c in self.contracts if c.expiry == expiry})

    def contract(self, expiry: str, strike: float, kind: OptionType) -> CleanContract | None:
        for c in self.contracts:
            if c.expiry == expiry and c.strike == strike and c.kind is kind:
                return c
        return None


@dataclass(frozen=True)
class Candidate:
    """A concrete, priced strategy proposed by the generator."""
    template_key: str
    config: StrategyConfig   # legs carry entry_price = mid
    expiry: str
    dte: int


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    metrics: dict            # net_premium, max_profit/loss, breakevens, pop, ev, greeks, ...
    score: float | None
    score_profile: str


@dataclass(frozen=True)
class DiscoveryResult:
    underlying: str
    as_of: str
    scoring_profile: str
    regime: dict
    results: list[dict]              # serialized, ranked, compliance-safe
    baseline: dict
    data_quality_report: list[dict]
    disclosure_block_id: str
