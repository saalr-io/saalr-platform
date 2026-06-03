from datetime import datetime, timezone
from decimal import Decimal

from saalr_core.llm.cost import (
    BudgetExceeded,
    budget_exceeded,
    estimate_cost,
    month_start,
    monthly_cap,
)


def test_estimate_cost_rates():
    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == Decimal("0.750000")
    assert estimate_cost("claude-3-5-haiku-latest", 1_000_000, 1_000_000) == Decimal("4.800000")
    assert estimate_cost("stub-chat", 1000, 1000) == Decimal("0.000000")
    assert estimate_cost("unknown", 1000, 1000) == Decimal("0.000000")


def test_budget_exceeded_boundary():
    assert budget_exceeded(Decimal("10"), Decimal("10")) is True   # spent == cap -> over
    assert budget_exceeded(Decimal("9.99"), Decimal("10")) is False
    assert issubclass(BudgetExceeded, Exception)


def test_month_start_zeroes_day_and_time():
    ms = month_start(datetime(2026, 6, 17, 13, 45, 9, 123, tzinfo=timezone.utc))
    assert ms == datetime(2026, 6, 1, 0, 0, 0, 0, tzinfo=timezone.utc)


def test_monthly_cap_reads_settings():
    class _S:
        llm_monthly_budget_usd = 10.0
    assert monthly_cap(_S()) == Decimal("10.0")
