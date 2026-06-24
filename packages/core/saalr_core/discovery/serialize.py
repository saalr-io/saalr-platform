from __future__ import annotations

from saalr_core.strategies.types import OptionLeg

from .types import Candidate

DISCLOSURE_BLOCK_ID = "disc_analytics_v1"   # COMPLY-4: frontend can't render without it

# COMPLY-1: imperative / recommendation phrasing forbidden in any user-facing string.
FORBIDDEN = (
    "buy", "sell", "we recommend", "you should", "best trade", "act now",
    "buy now", "sell now", "guaranteed", "can't lose",
)

_PROFILE_PHRASE = {
    "ev_to_risk": "EV-to-max-loss",
    "pop": "probability of profit",
    "ev_absolute": "expected value",
}


def assert_compliant(text: str) -> None:
    low = text.lower()
    hits = [p for p in FORBIDDEN if p in low]
    if hits:
        raise ValueError(f"COMPLY-1 violation: forbidden phrasing {hits} in {text!r}")


def serialize_candidate(cand: Candidate, metrics: dict, rank: int, profile: str) -> dict:
    legs = [
        {"option_type": leg.option_type.value, "side": leg.side.value,
         "strike": leg.strike, "expiry": leg.expiry, "qty": leg.qty}
        for leg in cand.config.legs if isinstance(leg, OptionLeg)
    ]
    summary = f"Ranked #{rank} by {_PROFILE_PHRASE.get(profile, profile)} under your filters."
    assert_compliant(summary)                       # COMPLY-1 enforced at build time
    public_metrics = {k: v for k, v in metrics.items() if not k.startswith("_")}
    return {
        "rank": rank,
        "template": cand.template_key,
        "legs": legs,
        "metrics": public_metrics,
        "score": public_metrics.get("ev_to_risk") if profile == "ev_to_risk"
                 else (public_metrics.get("pop") if profile == "pop" else public_metrics.get("ev")),
        "score_profile": profile,                   # COMPLY-2
        "summary": summary,
    }
