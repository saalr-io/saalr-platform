# content_embeddings is NOT in the autouse _truncate fixture (it is non-RLS / non-tenant).
# Every test here writes via reindex_catalog first, which deletes the model's rows before
# inserting — so the tests are self-cleaning. A read-only test would see prior rows; reindex first.
from saalr_content.loader import load_catalog
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.rag.index import reindex_catalog, semantic_search


async def test_reindex_then_semantic_search(app_sessionmaker, admin_engine):
    provider = HashEmbeddingProvider()
    catalog = load_catalog()
    async with app_sessionmaker() as s, s.begin():
        n = await reindex_catalog(s, provider, catalog, model=provider.model_name)
    assert n == len(catalog.modules)

    # a query of a module's own distinctive term should return that module first
    (qvec,) = await provider.embed(["theta time decay"])
    async with app_sessionmaker() as s:
        hits = await semantic_search(s, qvec, model=provider.model_name, limit=3)
    assert hits and hits[0][0] == "theta-time-decay"
    assert hits[0][1] <= hits[-1][1]  # ascending cosine distance


async def test_reindex_is_idempotent(app_sessionmaker, admin_engine):
    provider = HashEmbeddingProvider()
    catalog = load_catalog()
    async with app_sessionmaker() as s, s.begin():
        await reindex_catalog(s, provider, catalog, model=provider.model_name)
    async with app_sessionmaker() as s, s.begin():
        n2 = await reindex_catalog(s, provider, catalog, model=provider.model_name)
    # full rebuild deletes-then-inserts: still exactly one row per module, no duplicates
    assert n2 == len(catalog.modules)
