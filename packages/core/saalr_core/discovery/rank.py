from __future__ import annotations

from .score import score_for


def rank_and_truncate(scored: list[dict], profile: str, top_n: int) -> list[dict]:
    """RANK-4: deterministic order from (-score, template_key, sorted strikes). RANK-1
    follows from the dominance-guarded score. Truncation happens only AFTER filtering."""
    def key(c: dict):
        s = score_for(profile, c["metrics"])
        strikes = tuple(sorted(c["metrics"].get("_strikes", ())))
        return (-s, c["template_key"], strikes)
    return sorted(scored, key=key)[:top_n]
