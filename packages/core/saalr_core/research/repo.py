from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update

from saalr_core.db.models.research import ResearchNote
from saalr_core.ids import new_id


async def create_queued_run(session, *, tenant_id, user_id, ticker, market) -> UUID:
    note_id = new_id()
    session.add(ResearchNote(
        note_id=note_id, tenant_id=tenant_id, user_id=user_id, ticker=ticker,
        market=market, status="queued",
    ))
    await session.flush()
    return note_id


async def mark_running(session, note_id) -> None:
    await session.execute(
        update(ResearchNote).where(ResearchNote.note_id == note_id).values(status="running")
    )


async def save_succeeded(session, note_id, *, summary, signals, sources, model,
                         prompt_tokens, completion_tokens, cost_usd) -> None:
    await session.execute(
        update(ResearchNote).where(ResearchNote.note_id == note_id).values(
            status="succeeded", summary=summary, signals_json=signals, sources_json=sources,
            model=model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
            cost_usd=cost_usd, error_message=None,
        )
    )


async def save_failed(session, note_id, code: str) -> None:
    await session.execute(
        update(ResearchNote).where(ResearchNote.note_id == note_id).values(
            status="failed", error_message=code
        )
    )


async def recent_succeeded_note(session, ticker, market, since) -> ResearchNote | None:
    return (await session.execute(
        select(ResearchNote).where(
            ResearchNote.ticker == ticker, ResearchNote.market == market,
            ResearchNote.status == "succeeded", ResearchNote.created_at >= since)
        .order_by(ResearchNote.created_at.desc()).limit(1)
    )).scalar_one_or_none()


async def in_flight_run(session, ticker, market) -> ResearchNote | None:
    return (await session.execute(
        select(ResearchNote).where(
            ResearchNote.ticker == ticker, ResearchNote.market == market,
            ResearchNote.status.in_(("queued", "running")))
        .order_by(ResearchNote.created_at.desc()).limit(1)
    )).scalar_one_or_none()


async def count_runs_today(session, tenant_id, since) -> int:
    return (await session.execute(
        select(func.count()).select_from(ResearchNote).where(
            ResearchNote.tenant_id == tenant_id, ResearchNote.created_at >= since,
            ResearchNote.status != "failed")
    )).scalar_one()


async def list_succeeded_notes(session, limit, cursor) -> list[ResearchNote]:
    stmt = (select(ResearchNote).where(ResearchNote.status == "succeeded")
            .order_by(ResearchNote.created_at.desc(), ResearchNote.note_id.desc()))
    if cursor is not None:
        created_at, nid = cursor
        stmt = stmt.where(
            (ResearchNote.created_at < created_at)
            | ((ResearchNote.created_at == created_at) & (ResearchNote.note_id < nid))
        )
    return list((await session.execute(stmt.limit(limit))).scalars().all())


async def get_note(session, note_id) -> ResearchNote | None:
    return await session.get(ResearchNote, note_id)
