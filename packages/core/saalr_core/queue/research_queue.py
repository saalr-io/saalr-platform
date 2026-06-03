from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from redis.exceptions import ResponseError

STREAM = "saalr:research:jobs:v1"
GROUP = "research-workers"
_MAXLEN = 10_000


@dataclass(frozen=True)
class Job:
    msg_id: str
    tenant_id: UUID
    note_id: UUID


def _parse(entries) -> list[Job]:
    jobs: list[Job] = []
    for msg_id, fields in entries:
        if not fields:  # an entry deleted between pending and claim
            continue
        jobs.append(
            Job(
                msg_id=msg_id,
                tenant_id=UUID(fields["tenant_id"]),
                note_id=UUID(fields["note_id"]),
            )
        )
    return jobs


async def ensure_group(redis, stream: str = STREAM, group: str = GROUP) -> None:
    try:
        await redis.xgroup_create(stream, group, id="$", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def enqueue(redis, tenant_id: UUID, note_id: UUID, stream: str = STREAM) -> str:
    return await redis.xadd(
        stream,
        {"tenant_id": str(tenant_id), "note_id": str(note_id)},
        maxlen=_MAXLEN,
        approximate=True,
    )


async def consume_batch(
    redis, consumer: str, block_ms: int, count: int, stream: str = STREAM, group: str = GROUP
) -> list[Job]:
    resp = await redis.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
    if not resp:
        return []
    _stream_name, entries = resp[0]
    return _parse(entries)


async def ack(redis, msg_id: str, stream: str = STREAM, group: str = GROUP) -> None:
    await redis.xack(stream, group, msg_id)
    await redis.xdel(stream, msg_id)


async def claim_stale(
    redis, consumer: str, min_idle_ms: int, count: int, stream: str = STREAM, group: str = GROUP
) -> list[Job]:
    # Page through the pending-entries list until the cursor wraps to "0-0"; a single
    # XAUTOCLAIM returns at most `count` entries, so without this loop a crash that left
    # more than `count` jobs pending would only reclaim the first batch.
    jobs: list[Job] = []
    cursor = "0-0"
    while True:
        result = await redis.xautoclaim(
            stream, group, consumer, min_idle_ms, start_id=cursor, count=count
        )
        cursor = result[0]
        entries = result[1] if len(result) > 1 else []
        jobs.extend(_parse(entries))
        if not entries or cursor in ("0-0", "0"):
            return jobs
