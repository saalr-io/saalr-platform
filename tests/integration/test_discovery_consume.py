# tests/integration/test_discovery_consume.py
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest_asyncio
import redis.asyncio as aioredis
from sqlalchemy import text

from discovery_worker.consumer import run_consumer
from saalr_core.db.session import tenant_session
from saalr_core.discovery import repo
from saalr_core.ids import new_id
from saalr_core.queue import discovery_queue as q

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest_asyncio.fixture
async def redis():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield r
    await r.aclose()


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
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""),
                {"ts": ts, "sym": symbol, "o": Decimal(str(px)), "h": Decimal(str(px + 1)),
                 "l": Decimal(str(px - 1)), "c": Decimal(str(px)), "v": 1000},
            )


class _FakeMarket:
    async def _computed_chain(self, session, ticker, market):
        contracts = []
        for k in range(80, 121, 5):
            for t in ("CALL", "PUT"):
                contracts.append({"expiry": "2026-07-10", "strike": float(k), "type": t,
                                  "bid": 1.9, "ask": 2.1, "last": 2.0, "volume": 50,
                                  "open_interest": 500, "ours": {"iv": 0.3}, "vendor": {}})
        return {"ticker": ticker, "market": market, "as_of": "2026-06-10T20:00:00Z",
                "spot": 100.0, "div_yield": 0.0, "contracts": contracts}


async def test_enqueue_consume_persists_results(app_sessionmaker, admin_engine, redis):
    _uid, tid = await _bootstrap_tenant(admin_engine, "disc-consume@x.com", "ct_disc_consume")
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    await _seed_bars(admin_engine, "AAPL", start, [90.0 + i * 0.15 for i in range(80)])

    await redis.delete(q.STREAM)
    await q.ensure_group(redis)   # group MUST exist before enqueue (xreadgroup ">" only sees later msgs)
    async with tenant_session(app_sessionmaker, tid) as s:
        did = await repo.create_discovery(s, tid, "AAPL", "US",
                                          {"dte_min": 0, "dte_max": 60, "profile": "ev_to_risk",
                                           "top_n": 5, "families": ["bull_put_spread"]})
    await q.enqueue(redis, tid, did)
    await run_consumer(redis, app_sessionmaker, "w-test", _FakeMarket(),
                       rate_for=lambda t: 0.05, once=True, block_ms=200)

    async with tenant_session(app_sessionmaker, tid) as s:
        row = await repo.get_discovery(s, did)
    assert row.status == "succeeded", f"got {row.status}: {row.error_message}"
    assert "results" in row.result_json
    assert row.result_json["scoring_profile"] == "ev_to_risk"
    assert row.as_of is not None
