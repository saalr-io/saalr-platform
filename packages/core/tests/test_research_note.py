from decimal import Decimal

from saalr_core.research.note import ResearchInputs, build_research_prompt, estimate_cost


def _inputs(spot=50.0, vol={"primary_model": "garch", "forecast_mean": 0.21},
            sentiment={"score": 0.3, "label": "bullish"}, excerpts=None):
    return ResearchInputs("AAPL", "US", spot, vol, sentiment,
                          excerpts if excerpts is not None
                          else [("greeks-delta", "The Greeks: Delta", "Delta measures exposure.")])


def test_prompt_has_sections_and_grounding():
    system, user = build_research_prompt(_inputs())
    for sec in ("Overview", "Volatility", "Sentiment", "Risks", "Summary"):
        assert sec in system
    assert "Do not invent" in system
    assert "AAPL" in user and "50.0" in user
    assert "garch" in user and "bullish" in user
    assert "Delta measures exposure." in user and "greeks-delta" in user


def test_prompt_annotates_missing_signals():
    system, user = build_research_prompt(_inputs(spot=None, vol=None, sentiment=None, excerpts=[]))
    assert "unavailable" in user  # spot + vol unavailable annotated
    assert "no recent sentiment" in user
    assert "(none)" in user  # no excerpts


def test_estimate_cost_rate_math():
    # 1M prompt + 1M completion at gpt-4o-mini ($0.15 / $0.60 per 1M)
    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == Decimal("0.750000")
    assert estimate_cost("stub-chat", 1000, 1000) == Decimal("0.000000")
    assert estimate_cost("unknown-model", 1000, 1000) == Decimal("0.000000")
