from __future__ import annotations

from saalr_core.research.note import ResearchInputs

ANALYST_ROLES = ("fundamentals", "sentiment", "technical", "risk")

_GUARDRAIL = (
    "Use ONLY the provided signals and memos. When a signal is unavailable, say so explicitly. "
    "Do not invent data, prices, or recommendations; this is educational analysis, not advice."
)

_ANALYST_SYSTEMS = {
    "fundamentals": (
        "You are the Fundamentals analyst on a Saalr research team. Detailed financial statements "
        "(revenue, earnings, ratios) are NOT provided to you — do NOT invent any. Explicitly state "
        "that fundamentals data is unavailable, then give a brief qualitative note on what a reader "
        "should research. " + _GUARDRAIL
    ),
    "sentiment": (
        "You are the Sentiment analyst on a Saalr research team. From the sentiment signal and any "
        "concept excerpts, summarize the market mood in 2-4 sentences. " + _GUARDRAIL
    ),
    "technical": (
        "You are the Technical analyst on a Saalr research team. From the spot price and the GARCH "
        "volatility forecast, comment on the price and volatility regime in 2-4 sentences. " + _GUARDRAIL
    ),
    "risk": (
        "You are the Risk analyst on a Saalr research team. From the volatility forecast and the "
        "other signals, describe the key risks and sources of uncertainty in 2-4 sentences. " + _GUARDRAIL
    ),
}

_TRADER_SYSTEM = (
    "You are the Trader on a Saalr research team. Given the analyst memos, articulate a concise "
    "educational thesis in 2-4 sentences. Note where the analysts disagree. This is not advice. "
    + _GUARDRAIL
)

_PM_SYSTEM = (
    "You are the Portfolio Manager on a Saalr research team. Synthesize the analyst memos and the "
    "trader's thesis into a concise markdown research note with these sections: Overview, "
    "Volatility, Sentiment, Risks, Summary. " + _GUARDRAIL
)


def _signals_block(inputs: ResearchInputs) -> str:
    lines = [f"Ticker: {inputs.ticker} ({inputs.market})", "", "Signals:"]
    lines.append(f"- Spot: {inputs.spot}" if inputs.spot is not None else "- Spot: unavailable")
    lines.append(f"- Volatility forecast (GARCH): {inputs.vol_forecast}"
                 if inputs.vol_forecast is not None else "- Volatility forecast: unavailable")
    lines.append(f"- Sentiment: {inputs.sentiment}"
                 if inputs.sentiment is not None else "- Sentiment: no recent sentiment")
    lines += ["", "Concept excerpts:"]
    if inputs.content_excerpts:
        for i, (slug, _title, content) in enumerate(inputs.content_excerpts, 1):
            lines.append(f"[{i}] ({slug}) {content}")
    else:
        lines.append("(none)")
    return "\n".join(lines)


def _memo_block(memos: dict[str, str], roles) -> str:
    return "\n\n".join(f"## {role.capitalize()} memo\n{memos[role]}"
                       for role in roles if role in memos)


def build_analyst_prompt(role: str, inputs: ResearchInputs) -> tuple[str, str]:
    """(system, user) for one analyst role, grounded in the composed signals."""
    return _ANALYST_SYSTEMS[role], _signals_block(inputs)


def build_trader_prompt(inputs: ResearchInputs, memos: dict[str, str]) -> tuple[str, str]:
    user = _signals_block(inputs) + "\n\nAnalyst memos:\n\n" + _memo_block(memos, ANALYST_ROLES)
    return _TRADER_SYSTEM, user


def build_pm_prompt(inputs: ResearchInputs, memos: dict[str, str]) -> tuple[str, str]:
    user = (_signals_block(inputs) + "\n\nTeam memos:\n\n"
            + _memo_block(memos, (*ANALYST_ROLES, "trader")))
    return _PM_SYSTEM, user
