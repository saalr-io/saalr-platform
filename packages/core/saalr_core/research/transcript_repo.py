from __future__ import annotations

from sqlalchemy import select

from saalr_core.db.models.research import ResearchTranscript
from saalr_core.ids import new_id


async def insert_transcript(session, *, tenant_id, note_id, steps: list) -> None:
    session.add(ResearchTranscript(
        transcript_id=new_id(), tenant_id=tenant_id, note_id=note_id, transcript_json=steps))
    await session.flush()


async def get_transcript(session, note_id) -> list | None:
    return (await session.execute(
        select(ResearchTranscript.transcript_json).where(ResearchTranscript.note_id == note_id)
    )).scalar_one_or_none()
