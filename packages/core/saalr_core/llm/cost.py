from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

# USD per 1,000,000 tokens (prompt, completion). Estimates; the real bill is the source of truth.
_RATES: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "claude-3-5-haiku-latest": (Decimal("0.80"), Decimal("4.00")),
    "stub-chat": (Decimal(0), Decimal(0)),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Estimated USD cost for a completion. Unknown model -> 0. Quantized to 6 dp."""
    rate_p, rate_c = _RATES.get(model, (Decimal(0), Decimal(0)))
    cost = (Decimal(prompt_tokens) / Decimal(1_000_000) * rate_p
            + Decimal(completion_tokens) / Decimal(1_000_000) * rate_c)
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


class BudgetExceeded(Exception):
    """A tenant's month-to-date LLM spend has reached the monthly cap."""


def month_start(now: datetime) -> datetime:
    """First instant of `now`'s calendar month (preserves tzinfo)."""
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def monthly_cap(settings) -> Decimal:
    return Decimal(str(settings.llm_monthly_budget_usd))


def budget_exceeded(spent: Decimal, cap: Decimal) -> bool:
    return spent >= cap
