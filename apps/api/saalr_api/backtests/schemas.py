from __future__ import annotations

from datetime import date

from pydantic import BaseModel, model_validator


class BacktestRequest(BaseModel):
    start_date: date
    end_date: date
    initial_capital: float = 100_000.0
    include_costs: bool = True

    @model_validator(mode="after")
    def _end_after_start(self) -> "BacktestRequest":
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


def estimated_duration_seconds(start: date, end: date) -> int:
    """A rough hint for clients; not a guarantee."""
    days = (end - start).days
    return min(120, max(5, days // 7))
