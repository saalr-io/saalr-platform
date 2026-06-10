from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.trading import DiscoveryRun


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_discovery(session: AsyncSession, discovery_id: UUID) -> DiscoveryRun | None:
    return (
        await session.execute(select(DiscoveryRun).where(DiscoveryRun.discovery_id == discovery_id))
    ).scalar_one_or_none()


async def create_discovery(
    session: AsyncSession, tenant_id: UUID, underlying: str, market: str, request: dict,
) -> UUID:
    row = DiscoveryRun(
        tenant_id=tenant_id,
        underlying=underlying,
        market=market,
        status="queued",
        request_json=request,
    )
    session.add(row)
    await session.flush()
    return row.discovery_id


async def mark_running(session: AsyncSession, discovery_id: UUID) -> None:
    row = await get_discovery(session, discovery_id)
    if row is None:
        return
    row.status = "running"
    row.started_at = _utcnow()


async def save_result(
    session: AsyncSession,
    discovery_id: UUID,
    result_json: dict | None,
    status: str,
    error: str | None = None,
    as_of: str | None = None,
) -> None:
    row = await get_discovery(session, discovery_id)
    if row is None:
        return
    row.status = status
    row.result_json = result_json
    row.error_message = error
    if as_of is not None:
        row.as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    row.completed_at = _utcnow()
