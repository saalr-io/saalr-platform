from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from saalr_api.oms.marks import NoMarketData, model_mark


async def _seed_bars(admin_engine, symbol, closes, start=datetime(2025, 1, 1, tzinfo=timezone.utc)):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol=:s"), {"s": symbol})
        for i, c in enumerate(closes):
            ts = start + timedelta(days=i)
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:s,'US','1d',:c,:c,:c,:c,1000)"""),
                {"ts": ts, "s": symbol, "c": Decimal(str(c))},
            )


async def test_equity_mark_is_latest_close(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", [100, 101, 102.5])
    async with app_sessionmaker() as s:
        m = await model_mark(s, symbol="AAPL", market="US", option_type=None,
                             strike=None, expiry=None, today=date(2025, 6, 1))
    assert m == Decimal("102.5")


async def test_option_mark_is_positive_bsm(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", [100 + (i % 3) for i in range(40)])
    async with app_sessionmaker() as s:
        m = await model_mark(s, symbol="AAPL", market="US", option_type="CALL",
                             strike=Decimal("100"), expiry=date(2025, 4, 1), today=date(2025, 3, 1))
    assert m > Decimal("0")


async def test_no_bars_raises(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol='ZZZZ'"))
    async with app_sessionmaker() as s:
        with pytest.raises(NoMarketData):
            await model_mark(s, symbol="ZZZZ", market="US", option_type=None,
                             strike=None, expiry=None, today=date(2025, 6, 1))


async def test_option_nonpositive_strike_raises(app_sessionmaker, admin_engine):
    # a 0/negative strike would blow up BSM's log(spot/strike) -> must be a clean NoMarketData
    await _seed_bars(admin_engine, "AAPL", [100.0] * 40)
    async with app_sessionmaker() as s:
        with pytest.raises(NoMarketData):
            await model_mark(s, symbol="AAPL", market="US", option_type="CALL",
                             strike=Decimal("0"), expiry=date(2025, 4, 1), today=date(2025, 3, 1))
