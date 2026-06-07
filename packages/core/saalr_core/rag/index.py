from __future__ import annotations

from sqlalchemy import delete, select

from saalr_core.db.models.content import ContentEmbedding
from saalr_core.ids import new_id

from .chunk import chunk_module


async def reindex_catalog(session, provider, catalog, *, model: str) -> int:
    """Full rebuild of the index for `model`: delete its rows, then embed + insert each module's
    chunk(s). Returns the number of chunks written."""
    await session.execute(delete(ContentEmbedding).where(ContentEmbedding.embedding_model == model))
    count = 0
    for module in catalog.modules:
        chunks = chunk_module(module)
        vectors = await provider.embed([c.content for c in chunks])
        for chunk, vector in zip(chunks, vectors):
            session.add(ContentEmbedding(
                chunk_id=new_id(), module_slug=chunk.module_slug, chunk_index=chunk.chunk_index,
                content=chunk.content, embedding=vector, embedding_model=model,
            ))
            count += 1
    await session.flush()
    return count


async def semantic_search(
    session, query_vector, *, model: str, limit: int
) -> list[tuple[str, float]]:
    """Cosine kNN over the index for `model`. Returns (module_slug, distance) ascending."""
    distance = ContentEmbedding.embedding.cosine_distance(query_vector)
    rows = (await session.execute(
        select(ContentEmbedding.module_slug, distance.label("distance"))
        .where(ContentEmbedding.embedding_model == model)
        .order_by(distance)
        .limit(limit)
    )).all()
    return [(row.module_slug, float(row.distance)) for row in rows]
