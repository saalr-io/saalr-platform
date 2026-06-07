from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from saalr_api.backtests.schemas import BacktestRequest, estimated_duration_seconds


def test_request_parses_dates_and_defaults():
    r = BacktestRequest(start_date="2025-01-01", end_date="2025-06-30")
    assert r.start_date == date(2025, 1, 1) and r.end_date == date(2025, 6, 30)
    assert r.initial_capital == 100_000.0 and r.include_costs is True


def test_request_rejects_end_before_start():
    with pytest.raises(ValidationError):
        BacktestRequest(start_date="2025-06-30", end_date="2025-01-01")
    with pytest.raises(ValidationError):
        BacktestRequest(start_date="2025-01-01", end_date="2025-01-01")  # equal not allowed


def test_estimated_duration_bounds():
    assert estimated_duration_seconds(date(2025, 1, 1), date(2025, 1, 2)) == 5  # floor
    assert estimated_duration_seconds(date(2020, 1, 1), date(2025, 1, 1)) == 120  # cap
    mid = estimated_duration_seconds(date(2025, 1, 1), date(2025, 7, 1))  # ~181 days // 7 = 25
    assert mid == 25
