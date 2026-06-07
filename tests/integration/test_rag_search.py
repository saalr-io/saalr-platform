import httpx

from saalr_api.main import create_app
from saalr_content.loader import load_catalog
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.rag.index import reindex_catalog


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _build_index(app, provider):
    async with app.state.sessionmaker() as s, s.begin():
        await reindex_catalog(s, provider, load_catalog(), model=provider.model_name)


async def test_hybrid_ranks_on_topic_module_first(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        provider = HashEmbeddingProvider()
        app.state.embedding_provider = provider
        await _build_index(app, provider)
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rag1@x.com"}
            r = await c.get("/content/search", params={"q": "theta time decay", "mode": "hybrid"}, headers=h)
            assert r.status_code == 200
            results = r.json()["results"]
            assert results[0]["slug"] == "theta-time-decay"
            assert "score" in results[0] and "locked" in results[0]


async def test_semantic_mode_returns_relevant_module(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        provider = HashEmbeddingProvider()
        app.state.embedding_provider = provider
        await _build_index(app, provider)
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rag2@x.com"}
            r = await c.get("/content/search", params={"q": "implied volatility", "mode": "semantic"}, headers=h)
            assert r.status_code == 200
            assert r.json()["results"][0]["slug"] == "implied-volatility"


async def test_bad_mode_400(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rag3@x.com"}
            r = await c.get("/content/search", params={"q": "theta", "mode": "bogus"}, headers=h)
            assert r.status_code == 400
            assert r.json()["detail"]["error"]["code"] == "VALIDATION_INVALID_PARAMETER"


async def test_hybrid_falls_back_to_keyword_without_provider(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = None  # no provider -> keyword fallback
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rag4@x.com"}
            r = await c.get("/content/search", params={"q": "theta", "mode": "hybrid"}, headers=h)
            assert r.status_code == 200
            results = r.json()["results"]
            assert results and results[0]["slug"] and "score" in results[0]


class _MalformedProvider:
    """Returns the wrong number of vectors — the endpoint must degrade, not 500."""
    model_name = "hash-v1"
    dim = 1536

    async def embed(self, texts):
        return []


async def test_malformed_provider_degrades_not_500(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = _MalformedProvider()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:rag5@x.com"}
            r = await c.get("/content/search", params={"q": "theta", "mode": "semantic"}, headers=h)
            assert r.status_code == 200  # keyword fallback, never a 500
            assert "results" in r.json()
