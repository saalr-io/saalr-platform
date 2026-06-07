from saalr_core.strategies.recommend import recommend
from saalr_core.strategies.templates import list_templates


def _regime(direction, vol, momentum="range_bound"):
    return {
        "direction": {"label": direction},
        "volatility": {"label": vol},
        "momentum": {"label": momentum},
    }


def test_returns_all_21_with_rationale():
    recs = recommend(_regime("bullish", "normal"), list_templates())
    assert len(recs) == 21
    assert all(r["rationale"] for r in recs)
    assert all({"template_key", "name", "score", "risk", "market_view"} <= set(r) for r in recs)


def test_high_vol_neutral_favors_defined_short_vol():
    recs = recommend(_regime("neutral", "high"), list_templates())
    by = {r["template_key"]: r for r in recs}
    # iron condor (neutral, short_vol, defined) beats the equivalent naked short strangle
    assert by["iron_condor"]["score"] > by["short_strangle"]["score"]
    assert by["iron_condor"]["score"] > by["short_straddle"]["score"]
    top5 = [r["template_key"] for r in recs[:5]]
    assert "iron_condor" in top5 or "iron_butterfly" in top5


def test_strong_bullish_low_vol_tops_a_bullish_structure():
    recs = recommend(_regime("strong_bullish", "low"), list_templates())
    assert recs[0]["market_view"] == "bullish"


def test_deterministic_order():
    a = [r["template_key"] for r in recommend(_regime("bullish", "normal"), list_templates())]
    b = [r["template_key"] for r in recommend(_regime("bullish", "normal"), list_templates())]
    assert a == b
