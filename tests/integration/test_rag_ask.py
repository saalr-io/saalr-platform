import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_content.loader import load_catalog
from saalr_core.rag.chat import StubChatProvider
from saalr_core.rag.embeddings import HashEmbeddingProvider
from saalr_core.rag.index import reindex_catalog

_CANNED = "I couldn't find relevant OptionsAcademy material for that question."


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
                           {"t": tenant_id})


async def _tid(c, h):
    return (await c.get("/me", headers=h)).json()["tenant"]["id"]


async def _build_index(app, provider):
    async with app.state.sessionmaker() as s, s.begin():
        await reindex_catalog(s, provider, load_catalog(), model=provider.model_name)


async def test_ask_answers_with_citations(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = StubChatProvider()
        await _build_index(app, app.state.embedding_provider)
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask1@x.com"}
            await _make_pro(admin_engine, await _tid(c, h))
            r = await c.post("/content/ask", json={"question": "what is theta?"}, headers=h)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["answer"] and body["model"] == "stub-chat"
            assert any(cit["slug"] == "theta-time-decay" for cit in body["citations"])
            assert isinstance(body["usage"]["prompt_tokens"], int)


async def test_ask_free_tier_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = StubChatProvider()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask2@x.com"}
            r = await c.post("/content/ask", json={"question": "what is theta?"}, headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_ML_FORECAST_REQUIRES_PRO"


async def test_ask_no_provider_503(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = None
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask3@x.com"}
            await _make_pro(admin_engine, await _tid(c, h))
            r = await c.post("/content/ask", json={"question": "what is theta?"}, headers=h)
            assert r.status_code == 503 and r.json()["detail"]["error"]["code"] == "FEATURE_UNAVAILABLE"


async def test_ask_empty_index_short_circuits(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = StubChatProvider()
        from sqlalchemy import delete

        from saalr_core.db.models.content import ContentEmbedding
        async with app.state.sessionmaker() as s, s.begin():
            await s.execute(delete(ContentEmbedding).where(
                ContentEmbedding.embedding_model == app.state.embedding_provider.model_name))
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask4@x.com"}
            await _make_pro(admin_engine, await _tid(c, h))
            r = await c.post("/content/ask", json={"question": "what is theta?"}, headers=h)
            assert r.status_code == 200
            body = r.json()
            assert body["answer"] == _CANNED and body["citations"] == []
            assert body["usage"] == {"prompt_tokens": 0, "completion_tokens": 0}


async def test_ask_whitespace_question_400(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.embedding_provider = HashEmbeddingProvider()
        app.state.chat_provider = StubChatProvider()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ask5@x.com"}
            await _make_pro(admin_engine, await _tid(c, h))
            r = await c.post("/content/ask", json={"question": "   "}, headers=h)
            assert r.status_code == 400
            assert r.json()["detail"]["error"]["code"] == "VALIDATION_INVALID_PARAMETER"
            # an empty string returns the same 400 + project shape (not a pydantic 422)
            r2 = await c.post("/content/ask", json={"question": ""}, headers=h)
            assert r2.status_code == 400
            assert r2.json()["detail"]["error"]["code"] == "VALIDATION_INVALID_PARAMETER"
