from __future__ import annotations

from .types import CleanContract, Quote

_PAYOFF_TOL = 1e-6


def clean_quotes(quotes: list[Quote]) -> tuple[list[CleanContract], list[dict]]:
    """DATA-3: exclude zero-bid, crossed (bid>ask), and missing/stale quotes.

    Returns (clean contracts with mid, dropped report). The dropped report is
    diagnostic only and never reaches user-facing results.
    """
    clean: list[CleanContract] = []
    dropped: list[dict] = []
    for q in quotes:
        if q.bid is None or q.ask is None:
            dropped.append(_drop(q, "missing_quote"))
            continue
        if q.bid <= 0:
            dropped.append(_drop(q, "zero_bid"))
            continue
        if q.bid > q.ask:
            dropped.append(_drop(q, "crossed"))
            continue
        mid = (q.bid + q.ask) / 2.0
        clean.append(
            CleanContract(q.expiry, q.strike, q.kind, mid=mid, iv=q.iv,
                          volume=q.volume, open_interest=q.open_interest)
        )
    return clean, dropped


def _drop(q: Quote, reason: str) -> dict:
    return {"expiry": q.expiry, "strike": q.strike, "kind": q.kind.value, "reason": reason}


def is_free_lunch(net_premium: float, curve: list[tuple[float, float]]) -> bool:
    """RANK-2: a net-credit position (net_premium < 0) whose expiry payoff is
    non-negative at every evaluated terminal price is an arbitrage in the DATA
    (a bad quote), never alpha. Must be quarantined, never ranked."""
    if net_premium >= 0:  # debit -> cannot be a free lunch
        return False
    return all(pnl >= -_PAYOFF_TOL for _, pnl in curve)
