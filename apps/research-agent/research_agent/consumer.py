from __future__ import annotations

import logging

from saalr_core.queue.research_queue import ack, claim_stale, consume_batch, ensure_group

from .service import run_research_job

log = logging.getLogger("saalr.research.consumer")


async def _process(redis, sessionmaker, job, *, chat_provider, embedding_provider, catalog) -> None:
    try:
        await run_research_job(
            sessionmaker, job.tenant_id, job.note_id,
            chat_provider=chat_provider, embedding_provider=embedding_provider, catalog=catalog)
    except Exception:  # noqa: BLE001 - poison guard: run_research_job persists failures itself
        log.exception("research job %s failed unexpectedly", job.note_id)
    finally:
        await ack(redis, job.msg_id)


async def run_consumer(redis, sessionmaker, consumer: str, *, chat_provider, embedding_provider,
                       catalog, block_ms: int = 5000, count: int = 10, once: bool = False,
                       claim_min_idle_ms: int = 60_000) -> None:
    await ensure_group(redis)
    for job in await claim_stale(redis, consumer, claim_min_idle_ms, count):
        await _process(redis, sessionmaker, job, chat_provider=chat_provider,
                       embedding_provider=embedding_provider, catalog=catalog)
    while True:
        for job in await consume_batch(redis, consumer, block_ms, count):
            await _process(redis, sessionmaker, job, chat_provider=chat_provider,
                           embedding_provider=embedding_provider, catalog=catalog)
        if once:
            return
