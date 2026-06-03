from uuid import UUID, uuid4

import httpx

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.research import repo as note_repo
from saalr_core.research.transcript_store import DbTranscriptStore, make_transcript_store


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _me(c, h):
    body = (await c.get("/me", headers=h)).json()
    return UUID(body["tenant"]["id"]), UUID(body["user"]["id"])


_STEPS = [{"role": "fundamentals", "memo": "F"}, {"role": "pm", "memo": "P"}]


async def test_db_store_save_then_load(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            tid, uid = await _me(c, {"Authorization": "Bearer dev:ts1@x.com"})
            async with tenant_session(app.state.sessionmaker, tid) as s:
                note_id = await note_repo.create_queued_run(
                    s, tenant_id=tid, user_id=uid, ticker="AAPL", market="US")
            store = DbTranscriptStore(app.state.sessionmaker)
            await store.save(tenant_id=tid, note_id=note_id, steps=_STEPS)
            assert await store.load(tenant_id=tid, note_id=note_id) == _STEPS
            assert await store.load(tenant_id=tid, note_id=uuid4()) is None


async def test_make_transcript_store_returns_db_store(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        store = make_transcript_store(object(), app.state.sessionmaker)
        assert isinstance(store, DbTranscriptStore)
