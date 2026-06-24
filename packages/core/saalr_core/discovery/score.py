from __future__ import annotations

from collections.abc import Callable

WORST = float("-inf")


def _ev_to_risk(m: dict) -> float:
    r = m.get("ev_to_risk")
    return WORST if r is None else r


def _ev_absolute(m: dict) -> float:
    if m.get("max_loss") is None:
        return WORST
    return m["ev"]


def _pop_guarded(m: dict) -> float:
    """PoP-primary, but multiplied by a risk guard so a high-PoP / tiny-edge / huge-risk
    trade cannot dominate a balanced one (preserves RANK-1). Guard = clamp(ev_to_risk, 0..)."""
    if m.get("max_loss") is None or m.get("ev_to_risk") is None:
        return WORST
    guard = max(0.0, m["ev_to_risk"])
    return m["pop"] * guard


SCORE_PROFILES: dict[str, Callable[[dict], float]] = {
    "ev_to_risk": _ev_to_risk,
    "pop": _pop_guarded,
    "ev_absolute": _ev_absolute,
}


def score_for(profile: str, metrics: dict) -> float:
    if profile not in SCORE_PROFILES:
        raise KeyError(f"unknown scoring profile: {profile}")
    return SCORE_PROFILES[profile](metrics)
