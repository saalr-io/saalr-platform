from saalr_core.research.agents import (
    ANALYST_ROLES,
    build_analyst_prompt,
    build_pm_prompt,
    build_trader_prompt,
)
from saalr_core.research.note import ResearchInputs


def _inputs(spot=50.0, vol={"primary_model": "garch"}, sentiment={"label": "bullish"}):
    return ResearchInputs("AAPL", "US", spot, vol, sentiment,
                          [("greeks-delta", "Delta", "Delta measures exposure.")])


def test_analyst_roles_are_the_four_expected():
    assert ANALYST_ROLES == ("fundamentals", "sentiment", "technical", "risk")


def test_each_analyst_prompt_has_guardrail_and_signals():
    for role in ANALYST_ROLES:
        system, user = build_analyst_prompt(role, _inputs())
        assert "Do not invent" in system
        assert "AAPL" in user
    # the fundamentals role must explicitly flag the missing financials
    fsys, _ = build_analyst_prompt("fundamentals", _inputs())
    assert "NOT provided" in fsys or "not provided" in fsys


def test_analyst_prompt_annotates_missing_signal():
    _system, user = build_analyst_prompt("technical", _inputs(vol=None))
    assert "unavailable" in user


def test_trader_prompt_includes_all_analyst_memos():
    memos = {"fundamentals": "F-memo", "sentiment": "S-memo",
             "technical": "T-memo", "risk": "R-memo"}
    system, user = build_trader_prompt(_inputs(), memos)
    assert "Do not invent" in system
    for m in ("F-memo", "S-memo", "T-memo", "R-memo"):
        assert m in user


def test_pm_prompt_lists_sections_and_includes_memos():
    memos = {"fundamentals": "F", "sentiment": "S", "technical": "T",
             "risk": "R", "trader": "Thesis-X"}
    system, user = build_pm_prompt(_inputs(), memos)
    for sec in ("Overview", "Volatility", "Sentiment", "Risks", "Summary"):
        assert sec in system
    assert "Thesis-X" in user and "F" in user
