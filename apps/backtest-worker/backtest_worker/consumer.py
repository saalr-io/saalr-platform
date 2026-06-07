from __future__ import annotations

import logging

from saalr_core.queue.backtest_queue import Job, ack, claim_stale, consume_batch, ensure_group

from .service import run_backtest

log = logging.getLogger("saalr.backtest.consumer")


async def _process(redis, sessionmaker, job: Job) -> None:
    try:
        await run_backtest(sessionmaker, job.tenant_id, job.backtest_id)
    except Exception:  # noqa: BLE001 - poison guard: run_backtest persists in-pipeline failures itself
        log.exception("backtest job %s failed unexpectedly", job.backtest_id)
    finally:
        await ack(redis, job.msg_id)


async def run_consumer(
    redis,
    sessionmaker,
    consumer: str,
    block_ms: int = 5000,
    count: int = 10,
    once: bool = False,
    claim_min_idle_ms: int = 60_000,
) -> None:
    await ensure_group(redis)
    # reclaim + reprocess jobs left pending by a crashed worker
    for job in await claim_stale(redis, consumer, claim_min_idle_ms, count):
        await _process(redis, sessionmaker, job)
    while True:
        for job in await consume_batch(redis, consumer, block_ms, count):
            await _process(redis, sessionmaker, job)
        if once:
            return
