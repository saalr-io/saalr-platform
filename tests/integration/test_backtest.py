# tests/integration/test_backtest.py
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from backtest_worker import service
from saalr_core.db.session import tenant_session
from saalr_core.ids import new_id


async def _bootstrap_tenant(admin_engine, email: str, cuid: str):
    uid, tid, sid = new_id(), new_id(), new_id()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("SELECT auth_bootstrap(:uid, :tid, :sid, :cuid, :email)"),
            {"uid": str(uid), "tid": str(tid), "sid": str(sid), "cuid": cuid, "email": email},
        )
    return uid, tid


async def _seed_bars(admin_engine, symbol: str, start: datetime, prices: list[float]):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol = :s"), {"s": symbol})
        for i, px in enumerate(prices):
            ts = start + timedelta(days=i)
            await conn.execute(
                text(
                    """INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                       VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""
                ),
                {"ts": ts, "sym": symbol, "o": Decimal(str(px)), "h": Decimal(str(px + 1)),
                 "l": Decimal(str(px - 1)), "c": Decimal(str(px)), "v": 1000},
            )


async def _seed_strategy(app_sessionmaker, tid, uid, underlying: str):
    sid = new_id()
    config = {
        "underlying": underlying,
        "legs": [
            {"kind": "option", "option_type": "CALL", "side": "BUY",
             "strike": 100, "expiry": "2025-03-01", "qty": 1, "entry_price": None}
        ],
    }
    async with tenant_session(app_sessionmaker, tid) as s:
        await s.execute(
            text(
                """INSERT INTO strategies (strategy_id, tenant_id, user_id, name, state, config_json, market)
                   VALUES (:sid,:tid,:uid,'BT','draft', CAST(:cfg AS JSONB), 'US')"""
            ),
            {"sid": str(sid), "tid": str(tid), "uid": str(uid), "cfg": json.dumps(config)},
        )
    return sid


async def test_backtest_succeeds_and_persists(app_sessionmaker, admin_engine):
    uid, tid = await _bootstrap_tenant(admin_engine, "bt-ok@x.com", "ct_bt_ok")
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await _seed_bars(admin_engine, "AAPL", start, [100.0 + i * 0.3 for i in range(80)])
    sid = await _seed_strategy(app_sessionmaker, tid, uid, "AAPL")

    bt_id, outcome = await service.create_and_run(
        app_sessionmaker, tid, sid,
        {"start": "2025-02-01", "end": "2025-03-10", "vol_lookback": 20, "include_costs": False},
    )
    assert outcome["status"] == "succeeded"

    async with tenant_session(app_sessionmaker, tid) as s:
        row = (
            await s.execute(
                text("SELECT status, metrics_json FROM backtests WHERE backtest_id = :b"),
                {"b": str(bt_id)},
            )
        ).first()
    assert row.status == "succeeded"
    assert row.metrics_json["model"] == "bsm"
    assert row.metrics_json["iv_source"] == "realized_vol"
    assert row.metrics_json["approximate"] is True
    assert "sharpe" in row.metrics_json["metrics"]


async def test_backtest_fails_when_no_bars(app_sessionmaker, admin_engine):
    uid, tid = await _bootstrap_tenant(admin_engine, "bt-nobars@x.com", "ct_bt_nobars")
    sid = await _seed_strategy(app_sessionmaker, tid, uid, "ZZZZ")  # no bars seeded

    bt_id, outcome = await service.create_and_run(
        app_sessionmaker, tid, sid, {"start": "2025-02-01", "end": "2025-03-10"}
    )
    assert outcome["status"] == "failed"

    async with tenant_session(app_sessionmaker, tid) as s:
        row = (
            await s.execute(
                text("SELECT status, error_message FROM backtests WHERE backtest_id = :b"),
                {"b": str(bt_id)},
            )
        ).first()
    assert row.status == "failed"
    assert row.error_message
