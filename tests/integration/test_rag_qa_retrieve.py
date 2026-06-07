# content_embeddings is NOT in the autouse _truncate fixture (non-RLS). reindex_catalog
# deletes-by-model before inserting, so this test is self-cleaning.
from saalr_content.loader import load_catalog
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.rag.index import reindex_catalog
from saalr_core.rag.qa import RetrievedChunk, retrieve_context


async def test_retrieve_context_returns_content_ordered(app_sessionmaker, admin_engine):
    provider = HashEmbeddingProvider()
    catalog = load_catalog()
    async with app_sessionmaker() as s, s.begin():
        await reindex_catalog(s, provider, catalog, model=provider.model_name)
    (qvec,) = await provider.embed(["theta time decay"])
    async with app_sessionmaker() as s:
        chunks = await retrieve_context(s, qvec, model=provider.model_name, k=3)
    assert chunks and isinstance(chunks[0], RetrievedChunk)
    assert chunks[0].module_slug == "theta-time-decay"
    assert chunks[0].content  # content populated
    assert len(chunks) >= 2  # enough rows to actually exercise ordering
    assert all(chunks[i].distance <= chunks[i + 1].distance for i in range(len(chunks) - 1))


async def test_retrieve_context_empty_index_returns_empty(app_sessionmaker, admin_engine):
    provider = HashEmbeddingProvider()
    async with app_sessionmaker() as s, s.begin():
        # wipe this model's rows so the index is empty for this query
        from sqlalchemy import delete

        from saalr_core.db.models.content import ContentEmbedding
        await s.execute(delete(ContentEmbedding).where(
            ContentEmbedding.embedding_model == provider.model_name))
    (qvec,) = await provider.embed(["theta"])
    async with app_sessionmaker() as s:
        assert await retrieve_context(s, qvec, model=provider.model_name, k=3) == []
