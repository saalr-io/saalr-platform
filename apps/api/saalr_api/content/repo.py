from __future__ import annotations

from sqlalchemy import select

from saalr_core.db.models.content import UserProgress
from saalr_core.ids import new_id


async def get_progress(session, user_id, module_slug) -> UserProgress | None:
    return (await session.execute(
        select(UserProgress).where(
            UserProgress.user_id == user_id, UserProgress.module_slug == module_slug)
    )).scalar_one_or_none()


async def list_progress(session, user_id) -> list[UserProgress]:
    return list((await session.execute(
        select(UserProgress).where(UserProgress.user_id == user_id)
    )).scalars().all())


async def upsert_progress(session, *, tenant_id, user_id, module_slug, status, now,
                          existing=None) -> UserProgress:
    # `existing` lets a caller that already fetched the row skip a redundant SELECT.
    row = existing if existing is not None else await get_progress(session, user_id, module_slug)
    if row is None:
        row = UserProgress(
            progress_id=new_id(), tenant_id=tenant_id, user_id=user_id, module_slug=module_slug,
            status=status, started_at=now,
            completed_at=now if status == "completed" else None, updated_at=now,
        )
        session.add(row)
    else:
        if status == "completed" and row.status != "completed":
            row.status = "completed"
            row.completed_at = now
        # never downgrade a completed module back to in_progress
        row.updated_at = now
    await session.flush()
    return row
