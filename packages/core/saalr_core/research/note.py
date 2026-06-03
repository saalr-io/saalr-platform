from __future__ import annotations

from dataclasses import dataclass

from saalr_core.llm.cost import estimate_cost  # noqa: F401  (canonical home is llm.cost)

_SYSTEM = (
    "You are a Saalr research analyst. Write a concise markdown research note with these sections: "
    "Overview, Volatility, Sentiment, Risks, Summary. Use ONLY the signals and concept excerpts "
    "provided. When a signal is unavailable, say so explicitly. Do not invent data, prices, or "
    "recommendations; this is educational analysis, not advice."
)


@dataclass(frozen=True)
class ResearchInputs:
    ticker: str
    market: str
    spot: float | None
    vol_forecast: dict | None
    sentiment: dict | None
    content_excerpts: list[tuple[str, str, str]]  # (slug, title, content)


def build_research_prompt(inputs: ResearchInputs) -> tuple[str, str]:
    """Pure: (system, user) grounding the note in the composed signals + concept excerpts."""
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
    return _SYSTEM, "\n".join(lines)
