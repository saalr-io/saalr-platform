from __future__ import annotations

from sqlalchemy import select

from saalr_core.db.models.research import ResearchNote
from saalr_core.ids import new_id


async def recent_note(session, ticker, market, since) -> ResearchNote | None:
    """Newest note for (ticker, market) created at/after `since` (RLS-scoped)."""
    return (await session.execute(
        select(ResearchNote)
        .where(ResearchNote.ticker == ticker, ResearchNote.market == market,
               ResearchNote.created_at >= since)
        .order_by(ResearchNote.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def insert_note(session, *, tenant_id, user_id, ticker, market, summary, signals, sources,
                      model, prompt_tokens, completion_tokens, cost_usd) -> ResearchNote:
    row = ResearchNote(
        note_id=new_id(), tenant_id=tenant_id, user_id=user_id, ticker=ticker, market=market,
        summary=summary, signals_json=signals, sources_json=sources, model=model,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cost_usd=cost_usd,
    )
    session.add(row)
    await session.flush()
    return row


async def list_notes(session, limit, cursor) -> list[ResearchNote]:
    stmt = select(ResearchNote).order_by(ResearchNote.created_at.desc(), ResearchNote.note_id.desc())
    if cursor is not None:
        created_at, nid = cursor
        stmt = stmt.where(
            (ResearchNote.created_at < created_at)
            | ((ResearchNote.created_at == created_at) & (ResearchNote.note_id < nid))
        )
    return list((await session.execute(stmt.limit(limit))).scalars().all())


async def get_note(session, note_id) -> ResearchNote | None:
    return await session.get(ResearchNote, note_id)
