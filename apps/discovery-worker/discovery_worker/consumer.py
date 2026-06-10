from __future__ import annotations

import logging

from saalr_core.queue.discovery_queue import Job, ack, claim_stale, consume_batch, ensure_group

from .service import run_discovery_job

log = logging.getLogger("saalr.discovery.consumer")


async def _process(redis, sessionmaker, job: Job, market_service, rate_for) -> None:
    try:
        await run_discovery_job(sessionmaker, job.tenant_id, job.discovery_id, market_service, rate_for)
    except Exception:  # noqa: BLE001 - poison guard: run_discovery_job persists failures itself
        log.exception("discovery job %s failed unexpectedly", job.discovery_id)
    finally:
        await ack(redis, job.msg_id)


async def run_consumer(redis, sessionmaker, consumer: str, market_service, rate_for,
                       block_ms: int = 5000, count: int = 10, once: bool = False,
                       claim_min_idle_ms: int = 60_000) -> None:
    await ensure_group(redis)
    for job in await claim_stale(redis, consumer, claim_min_idle_ms, count):
        await _process(redis, sessionmaker, job, market_service, rate_for)
    while True:
        for job in await consume_batch(redis, consumer, block_ms, count):
            await _process(redis, sessionmaker, job, market_service, rate_for)
        if once:
            return
