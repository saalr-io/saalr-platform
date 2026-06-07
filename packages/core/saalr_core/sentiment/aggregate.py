from __future__ import annotations

from datetime import datetime

from .types import ScoredHeadline

_BULL_THRESHOLD = 0.15
_BEAR_THRESHOLD = -0.15


def aggregate_sentiment(
    scored: list[ScoredHeadline],
    as_of: datetime,
    half_life_hours: float = 72.0,
    min_weight: float = 0.1,
) -> dict:
    """Time-decayed, confidence-weighted mean sentiment (LLD §4.3). Returns the neutral
    floor (score 0.0, confident False) when the accumulated weight is below min_weight —
    never forcing a directional signal from thin or stale data."""
    total_score = 0.0
    total_weight = 0.0
    for h in scored:
        # Floor age at 0: a future-dated headline (clock skew / wire-service timestamps)
        # must not get time_weight > 1 and outweigh present news.
        age_hours = max(0.0, (as_of - h.published_at).total_seconds() / 3600.0)
        time_weight = 0.5 ** (age_hours / half_life_hours)
        weight = time_weight * h.confidence
        total_score += h.score * weight
        total_weight += weight

    n = len(scored)
    if total_weight < min_weight:
        return {
            "score": 0.0,
            "label": "neutral",
            "confident": False,
            "n_headlines": n,
            "total_weight": total_weight,
            "as_of": as_of.isoformat(),
        }

    score = max(-1.0, min(1.0, total_score / total_weight))
    label = "bullish" if score > _BULL_THRESHOLD else "bearish" if score < _BEAR_THRESHOLD else "neutral"
    return {
        "score": score,
        "label": label,
        "confident": True,
        "n_headlines": n,
        "total_weight": total_weight,
        "as_of": as_of.isoformat(),
    }
