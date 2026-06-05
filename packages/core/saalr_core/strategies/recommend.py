from __future__ import annotations

# How much a template's market_view is worth given the detected direction.
_DIR_POINTS = {
    "strong_bullish": {"bullish": 3, "neutral": 1, "volatile": 1, "bearish": -2},
    "bullish": {"bullish": 3, "neutral": 1, "volatile": 1, "bearish": -2},
    "neutral": {"neutral": 3, "bullish": 1, "bearish": 1, "volatile": 1},
    "bearish": {"bearish": 3, "neutral": 1, "volatile": 1, "bullish": -2},
    "strong_bearish": {"bearish": 3, "neutral": 1, "volatile": 1, "bullish": -2},
}
# How much a template's vol_view is worth given the detected volatility level.
_VOL_POINTS = {
    "high": {"short_vol": 3, "neutral": 1, "long_vol": -1},
    "low": {"long_vol": 3, "neutral": 1, "short_vol": -1},
    "normal": {"neutral": 2, "short_vol": 1, "long_vol": 1},
}

_DIR_PHRASE = {
    "strong_bullish": "a strong bullish", "bullish": "a bullish", "neutral": "a neutral",
    "bearish": "a bearish", "strong_bearish": "a strong bearish",
}


def _rationale(direction: str, vol: str, has_bonus: bool, risk: str) -> str:
    bits = [f"Fits {_DIR_PHRASE[direction]} view in {vol} vol"]
    if has_bonus:
        bits.append("aligned with momentum")
    bits.append("defined risk" if risk == "defined" else "undefined risk — size carefully")
    return "; ".join(bits) + "."


def recommend(regime: dict, templates: list[dict]) -> list[dict]:
    """Rank templates by how well their tags fit the regime, with a retail-safety bias.

    Pure: `regime` needs only direction/volatility/momentum labels; `templates` is the
    output of templates.list_templates(). Returns every template scored + a rationale,
    sorted by score desc then key asc (deterministic)."""
    direction = regime["direction"]["label"]
    vol = regime["volatility"]["label"]
    momentum = regime["momentum"]["label"]
    dpts = _DIR_POINTS[direction]
    vpts = _VOL_POINTS[vol]

    out = []
    for t in templates:
        dp = dpts.get(t["market_view"], 0)
        vp = vpts.get(t["vol_view"], 0)
        bonus = 0
        if momentum == "trending" and t["market_view"] == "volatile":
            bonus = 1
        elif momentum == "range_bound" and t["market_view"] == "neutral":
            bonus = 1
        penalty = (2 if t["risk"] == "undefined" else 0) + (1 if t["complexity"] == "advanced" else 0)
        score = dp + vp + bonus - penalty
        out.append({
            "template_key": t["key"], "name": t["name"], "score": score,
            "market_view": t["market_view"], "vol_view": t["vol_view"], "net": t["net"],
            "risk": t["risk"], "complexity": t["complexity"],
            "rationale": _rationale(direction, vol, bool(bonus), t["risk"]),
        })
    out.sort(key=lambda r: (-r["score"], r["template_key"]))
    return out
