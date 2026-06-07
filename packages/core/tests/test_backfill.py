from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from saalr_core.marketdata.aggregates import BarRow
from saalr_core.marketdata.backfill import backfill_symbol, upsert_bars


class FakeResult:
    pass


class FakeSession:
    """Records execute() calls without touching a database."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    async def execute(self, stmt, params=None):
        self.calls.append((stmt, params))
        return FakeResult()


class FakeAgg:
    def __init__(self, rows: list[BarRow]) -> None:
        self._rows = rows
        self.args: tuple | None = None

    async def get_daily_bars(self, symbol, start, end, market="US"):
        self.args = (symbol, start, end, market)
        return self._rows


def _bar(d: str) -> BarRow:
    return BarRow(
        ts=datetime.fromisoformat(d).replace(tzinfo=timezone.utc),
        symbol="AAPL", market="US", interval="1d",
        open=1.0, high=2.0, low=0.5, close=1.5, volume=100,
    )


@pytest.mark.asyncio
async def test_upsert_bars_empty_is_noop():
    s = FakeSession()
    n = await upsert_bars(s, [])
    assert n == 0
    assert s.calls == []


@pytest.mark.asyncio
async def test_upsert_bars_executes_once_with_all_rows():
    s = FakeSession()
    n = await upsert_bars(s, [_bar("2026-01-02"), _bar("2026-01-03")])
    assert n == 2
    assert len(s.calls) == 1
    _stmt, params = s.calls[0]
    assert isinstance(params, list) and len(params) == 2
    assert params[0]["symbol"] == "AAPL" and params[0]["interval"] == "1d"


@pytest.mark.asyncio
async def test_backfill_symbol_fetches_then_upserts():
    s = FakeSession()
    agg = FakeAgg([_bar("2026-01-02")])
    n = await backfill_symbol(s, agg, "AAPL", "US", date(2026, 1, 1), date(2026, 1, 5))
    assert n == 1
    assert agg.args == ("AAPL", date(2026, 1, 1), date(2026, 1, 5), "US")
    assert len(s.calls) == 1
