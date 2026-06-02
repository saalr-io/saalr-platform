from __future__ import annotations

from saalr_core.rag.index import reindex_catalog


async def run_reindex(sessionmaker, provider, catalog, *, model: str) -> int:
    """Rebuild the content embeddings index in a single transaction (content is non-RLS)."""
    async with sessionmaker() as session, session.begin():
        return await reindex_catalog(session, provider, catalog, model=model)
