# tests/integration/test_backtest_queue.py
import os

import pytest_asyncio
import redis.asyncio as aioredis

from saalr_core.ids import new_id
from saalr_core.queue import backtest_queue as q

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


@pytest_asyncio.fixture
async def redis():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield r
    await r.aclose()


async def test_ensure_group_idempotent(redis):
    stream = f"test:bt:{new_id()}"
    try:
        await q.ensure_group(redis, stream=stream, group="g")
        await q.ensure_group(redis, stream=stream, group="g")  # must not raise (BUSYGROUP swallowed)
    finally:
        await redis.delete(stream)


async def test_enqueue_consume_ack_roundtrip(redis):
    stream = f"test:bt:{new_id()}"
    try:
        await q.ensure_group(redis, stream=stream, group="g")
        tid, bid = new_id(), new_id()
        await q.enqueue(redis, tid, bid, stream=stream)
        jobs = await q.consume_batch(redis, "c1", block_ms=200, count=10, stream=stream, group="g")
        assert len(jobs) == 1
        assert jobs[0].tenant_id == tid and jobs[0].backtest_id == bid
        assert (await redis.xpending(stream, "g"))["pending"] == 1
        await q.ack(redis, jobs[0].msg_id, stream=stream, group="g")
        assert (await redis.xpending(stream, "g"))["pending"] == 0
    finally:
        await redis.delete(stream)


async def test_consume_batch_empty_on_timeout(redis):
    stream = f"test:bt:{new_id()}"
    try:
        await q.ensure_group(redis, stream=stream, group="g")
        assert await q.consume_batch(redis, "c1", block_ms=50, count=10, stream=stream, group="g") == []
    finally:
        await redis.delete(stream)


async def test_claim_stale_reclaims_unacked(redis):
    stream = f"test:bt:{new_id()}"
    try:
        await q.ensure_group(redis, stream=stream, group="g")
        tid, bid = new_id(), new_id()
        await q.enqueue(redis, tid, bid, stream=stream)
        await q.consume_batch(redis, "c1", block_ms=200, count=10, stream=stream, group="g")  # c1 never acks
        claimed = await q.claim_stale(redis, "c2", min_idle_ms=0, count=10, stream=stream, group="g")
        assert len(claimed) == 1 and claimed[0].backtest_id == bid
    finally:
        await redis.delete(stream)
