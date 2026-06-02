from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# USD per 1,000,000 tokens (prompt, completion). Estimate; the real bill is the source of truth.
_RATES: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "stub-chat": (Decimal(0), Decimal(0)),
}

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


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Estimated USD cost for a completion. Unknown model -> 0. Quantized to 6 dp."""
    rate_p, rate_c = _RATES.get(model, (Decimal(0), Decimal(0)))
    cost = (Decimal(prompt_tokens) / Decimal(1_000_000) * rate_p
            + Decimal(completion_tokens) / Decimal(1_000_000) * rate_c)
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
