from uuid import UUID, uuid4

import httpx

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.research import repo as note_repo
from saalr_core.research import transcript_repo


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _me(c, h):
    body = (await c.get("/me", headers=h)).json()
    return UUID(body["tenant"]["id"]), UUID(body["user"]["id"])


_STEPS = [{"role": "fundamentals", "memo": "F"}, {"role": "pm", "memo": "P"}]


async def test_insert_then_get_round_trips(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            tid, uid = await _me(c, {"Authorization": "Bearer dev:tr1@x.com"})
            async with tenant_session(app.state.sessionmaker, tid) as s:
                note_id = await note_repo.create_queued_run(
                    s, tenant_id=tid, user_id=uid, ticker="AAPL", market="US")
            async with tenant_session(app.state.sessionmaker, tid) as s:
                await transcript_repo.insert_transcript(
                    s, tenant_id=tid, note_id=note_id, steps=_STEPS)
            async with tenant_session(app.state.sessionmaker, tid) as s:
                got = await transcript_repo.get_transcript(s, note_id)
                assert got == _STEPS
                assert await transcript_repo.get_transcript(s, uuid4()) is None
