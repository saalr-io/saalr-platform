from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ONBOARDING_STEPS = ("build_strategy", "see_regime", "paper_trade", "read_lesson")


async def list_steps(session: AsyncSession, tenant_id: UUID) -> list[str]:
    rows = (await session.execute(
        text("SELECT step FROM onboarding_progress WHERE tenant_id = :t"),
        {"t": str(tenant_id)},
    )).scalars().all()
    return list(rows)


async def mark_step(session: AsyncSession, tenant_id: UUID, step: str) -> None:
    await session.execute(
        text("INSERT INTO onboarding_progress (tenant_id, step) VALUES (:t, :s) "
             "ON CONFLICT (tenant_id, step) DO NOTHING"),
        {"t": str(tenant_id), "s": step},
    )
