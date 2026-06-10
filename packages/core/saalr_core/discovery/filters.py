from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Filters:
    min_pop: float | None = None
    max_loss: float | None = None             # in dollars; candidate max_loss must be <=
    min_open_interest: int | None = None
    max_bid_ask_pct: float | None = None


def apply_filters(scored: list[dict], f: Filters) -> list[dict]:
    """RANK-3: applied to the FULL candidate set, before any top-N truncation."""
    out = []
    for c in scored:
        m = c["metrics"]
        if f.min_pop is not None and m["pop"] < f.min_pop:
            continue
        if f.max_loss is not None and (m["max_loss"] is None or m["max_loss"] > f.max_loss):
            continue
        if f.min_open_interest is not None and m.get("min_open_interest", 0) < f.min_open_interest:
            continue
        if f.max_bid_ask_pct is not None and m.get("max_bid_ask_pct", 1.0) > f.max_bid_ask_pct:
            continue
        out.append(c)
    return out
