from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from ingest_worker import repo, service
from saalr_core.marketdata.aggregates import BarRow


async def test_instruments_table_exists_and_writable(app_sessionmaker):
    async with app_sessionmaker() as s:
        async with s.begin():
            await s.execute(text("TRUNCATE instruments"))
            await s.execute(
                text("INSERT INTO instruments (symbol, market, name) VALUES ('AAPL','US','Apple')")
            )
        async with s.begin():
            n = (await s.execute(text("SELECT count(*) FROM instruments WHERE symbol='AAPL'"))).scalar_one()
    assert n == 1


def _bar(ts, symbol="AAPL", market="US", close=100.0):
    return BarRow(ts=ts, symbol=symbol, market=market, interval="1d",
                  open=close - 1, high=close + 1, low=close - 2, close=close, volume=1000)


class StubAggs:
    """Returns one daily bar per calendar day in [start, end]."""
    def __init__(self):
        self.calls = []

    async def get_daily_bars(self, symbol, start, end, market="US"):
        self.calls.append((symbol, start, end))
        out, d = [], start
        while d <= end:
            ts = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            out.append(_bar(ts, symbol, market, close=100.0 + d.day))
            d += timedelta(days=1)
        return out


async def test_add_instrument_idempotent(app_sessionmaker):
    async with app_sessionmaker() as s:
        async with s.begin():
            await s.execute(text("TRUNCATE instruments"))
            await repo.add_instrument(s, "MSFT", "US", "Microsoft")
            await repo.add_instrument(s, "MSFT", "US", "Microsoft Corp")
        async with s.begin():
            active = await repo.list_active_instruments(s)
    assert [(i.symbol, i.name) for i in active] == [("MSFT", "Microsoft Corp")]


async def test_bars_upsert_is_idempotent(admin_engine, app_sessionmaker):
    ts = datetime(2025, 1, 2, tzinfo=timezone.utc)
    async with admin_engine.begin() as admin:
        await admin.execute(text("TRUNCATE bars"))
    async with app_sessionmaker() as s:
        async with s.begin():
            await repo.upsert_bars(s, [_bar(ts, close=101.0)])
            await repo.upsert_bars(s, [_bar(ts, close=102.0)])
        async with s.begin():
            n = (await s.execute(text("SELECT count(*) FROM bars WHERE symbol='AAPL'"))).scalar_one()
            c = (await s.execute(text("SELECT close FROM bars WHERE symbol='AAPL'"))).scalar_one()
    assert n == 1 and float(c) == 102.0


async def test_backfill_then_incremental_appends(admin_engine, app_sessionmaker):
    stub = StubAggs()
    async with admin_engine.begin() as admin:
        await admin.execute(text("TRUNCATE bars"))
        await admin.execute(text("TRUNCATE instruments"))
    async with app_sessionmaker() as s:
        async with s.begin():
            await repo.add_instrument(s, "AAPL", "US", "Apple")
            await service.backfill_symbol(s, stub, "AAPL", "US", date(2025, 1, 1), date(2025, 1, 3))
        async with s.begin():
            n1 = (await s.execute(text("SELECT count(*) FROM bars WHERE symbol='AAPL'"))).scalar_one()
        async with s.begin():
            counts = await service.run_incremental(s, stub, default_days=30, today=date(2025, 1, 6))
        async with s.begin():
            n2 = (await s.execute(text("SELECT count(*) FROM bars WHERE symbol='AAPL'"))).scalar_one()
    assert n1 == 3
    assert counts["AAPL"] == 3
    assert n2 == 6
