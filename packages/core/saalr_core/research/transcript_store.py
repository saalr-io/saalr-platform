from __future__ import annotations

from typing import Protocol, runtime_checkable

from saalr_core.db.session import tenant_session
from saalr_core.research import transcript_repo


@runtime_checkable
class TranscriptStore(Protocol):
    async def save(self, *, tenant_id, note_id, steps: list[dict]) -> None: ...
    async def load(self, *, tenant_id, note_id) -> list[dict] | None: ...


class DbTranscriptStore:
    """Postgres-backed transcript store. Each method opens its own tenant session, so the
    TranscriptStore interface stays backend-agnostic (an S3TranscriptStore swaps in later)."""

    def __init__(self, sessionmaker) -> None:
        self._sm = sessionmaker

    async def save(self, *, tenant_id, note_id, steps: list[dict]) -> None:
        async with tenant_session(self._sm, tenant_id) as s:
            await transcript_repo.insert_transcript(s, tenant_id=tenant_id, note_id=note_id, steps=steps)

    async def load(self, *, tenant_id, note_id) -> list[dict] | None:
        async with tenant_session(self._sm, tenant_id) as s:
            return await transcript_repo.get_transcript(s, note_id)


def make_transcript_store(settings, sessionmaker) -> TranscriptStore:
    """DB store now; the S3 branch is deferred to the AWS-foundation slice."""
    return DbTranscriptStore(sessionmaker)
