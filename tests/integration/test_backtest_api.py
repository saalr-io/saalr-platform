from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.db.session import create_engine, create_sessionmaker
from backtest_worker.consumer import run_consumer

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, start, prices):
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


_OPTION = {"kind": "option", "option_type": "CALL", "side": "BUY", "strike": 100,
           "expiry": "2025-03-01", "qty": 1, "entry_price": None}


async def _make_strategy(c, headers, underlying="AAPL"):
    body = {"name": "BT", "config": {"underlying": underlying, "legs": [_OPTION]}, "market": "US"}
    r = await c.post("/v1/strategies", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["strategy_id"]


async def test_post_returns_202_then_get_is_queued(app_sessionmaker, admin_engine):
    # clean the shared stream + create the app (lifespan ensure_group on a clean stream)
    r0 = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r0.delete("saalr:bt:jobs:v1")
    await r0.aclose()
    await _seed_bars(admin_engine, "AAPL", datetime(2025, 1, 1, tzinfo=timezone.utc),
                     [100.0 + i * 0.3 for i in range(80)])

    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-api@x.com"}
            sid = await _make_strategy(c, h)
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-02-01", "end_date": "2025-03-10"}, headers=h)
            assert r.status_code == 202, r.text
            body = r.json()
            assert body["status"] == "queued"
            assert body["poll_url"] == f"/v1/backtests/{body['backtest_id']}"
            assert body["estimated_duration_seconds"] >= 5

            poll = await c.get(body["poll_url"], headers=h)
            assert poll.status_code == 200 and poll.json()["status"] == "queued"


async def test_idempotency_key_returns_same_backtest(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-idem@x.com"}
            sid = await _make_strategy(c, h)
            req = {"start_date": "2025-02-01", "end_date": "2025-03-10"}
            hk = {**h, "Idempotency-Key": "fixed-key-123"}
            r1 = await c.post(f"/v1/strategies/{sid}/backtest", json=req, headers=hk)
            r2 = await c.post(f"/v1/strategies/{sid}/backtest", json=req, headers=hk)
            assert r1.status_code == 202 and r2.status_code == 202
            assert r1.json()["backtest_id"] == r2.json()["backtest_id"]


async def test_validation_end_before_start_is_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-val@x.com"}
            sid = await _make_strategy(c, h)
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-03-10", "end_date": "2025-02-01"}, headers=h)
            assert r.status_code == 422


async def test_get_other_tenant_backtest_is_404(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            ha = {"Authorization": "Bearer dev:bt-a@x.com"}
            hb = {"Authorization": "Bearer dev:bt-b@x.com"}
            sid = await _make_strategy(c, ha)
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-02-01", "end_date": "2025-03-10"}, headers=ha)
            bt_id = r.json()["backtest_id"]
            # tenant B must not see tenant A's backtest
            other = await c.get(f"/v1/backtests/{bt_id}", headers=hb)
            assert other.status_code == 404


async def _run_worker_once():
    settings_url = os.environ["APP_DATABASE_URL"]
    engine = create_engine(settings_url)
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await run_consumer(redis, create_sessionmaker(engine), "test-consumer",
                           block_ms=1000, count=10, once=True)
    finally:
        await redis.aclose()
        await engine.dispose()


async def test_end_to_end_post_consume_poll_succeeds(app_sessionmaker, admin_engine):
    r0 = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r0.delete("saalr:bt:jobs:v1")
    await r0.aclose()
    await _seed_bars(admin_engine, "AAPL", datetime(2025, 1, 1, tzinfo=timezone.utc),
                     [100.0 + i * 0.3 for i in range(80)])

    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-e2e@x.com"}
            sid = await _make_strategy(c, h)
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-02-01", "end_date": "2025-03-10",
                                   "include_costs": False}, headers=h)
            poll_url = r.json()["poll_url"]

            await _run_worker_once()

            done = await c.get(poll_url, headers=h)
            assert done.status_code == 200
            data = done.json()
            assert data["status"] == "succeeded", data
            assert "sharpe" in data["metrics"]
            assert "equity_series" in data
            assert len(data["equity_series"]) > 0
            assert set(data["equity_series"][0].keys()) == {"date", "equity"}
            assert data["trade_log_url"] is None


async def test_end_to_end_failed_when_no_bars(app_sessionmaker, admin_engine):
    r0 = aioredis.from_url(REDIS_URL, decode_responses=True)
    await r0.delete("saalr:bt:jobs:v1")
    await r0.aclose()

    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bt-e2e-fail@x.com"}
            sid = await _make_strategy(c, h, underlying="ZZZZ")  # no bars
            r = await c.post(f"/v1/strategies/{sid}/backtest",
                             json={"start_date": "2025-02-01", "end_date": "2025-03-10"}, headers=h)
            poll_url = r.json()["poll_url"]

            await _run_worker_once()

            done = await c.get(poll_url, headers=h)
            assert done.json()["status"] == "failed"
            assert done.json()["error"]["code"] == "BACKTEST_FAILED"
