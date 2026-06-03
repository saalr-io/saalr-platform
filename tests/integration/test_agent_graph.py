from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo
from saalr_core.llm.cost import BudgetExceeded
from saalr_core.llm.gateway import ChatGateway
from saalr_core.llm.metered import metered_complete
from saalr_core.rag.chat import StubChatProvider
from saalr_core.research.graph import run_agent_graph
from saalr_core.research.note import ResearchInputs

_EXPECTED_PURPOSES = {f"research_agent:{r}" for r in
                      ("fundamentals", "sentiment", "technical", "risk", "trader", "pm")}


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _me(c, h):
    body = (await c.get("/me", headers=h)).json()
    return UUID(body["tenant"]["id"]), UUID(body["user"]["id"])


async def test_run_agent_graph_makes_six_metered_calls(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            tid, uid = await _me(c, {"Authorization": "Bearer dev:graph1@x.com"})
            inputs = ResearchInputs("AAPL", "US", 50.0, None, None, [])
            note_id = uuid4()
            res = await run_agent_graph(
                app.state.sessionmaker, tid, uid, inputs=inputs,
                gateway=ChatGateway([StubChatProvider()]), cap=Decimal("10"), note_id=note_id)
            assert res.note_markdown
            assert res.model == "stub-chat" and res.provider == "stub"
            assert res.prompt_tokens > 0
            async with admin_engine.begin() as conn:
                rows = (await conn.execute(
                    text("SELECT purpose, note_id FROM llm_usage WHERE tenant_id=:t"),
                    {"t": str(tid)})).all()
            assert {r.purpose for r in rows} == _EXPECTED_PURPOSES
            assert all(str(r.note_id) == str(note_id) for r in rows)


async def test_metered_complete_raises_when_over_budget(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            tid, uid = await _me(c, {"Authorization": "Bearer dev:graph2@x.com"})
            async with tenant_session(app.state.sessionmaker, tid) as s:
                await llm_repo.record_usage(s, tenant_id=tid, user_id=uid, provider="x",
                                            model="gpt-4o-mini", prompt_tokens=1, completion_tokens=1,
                                            cost_usd=Decimal("11"), purpose="seed")
            with pytest.raises(BudgetExceeded):
                await metered_complete(
                    app.state.sessionmaker, tid, uid, gateway=ChatGateway([StubChatProvider()]),
                    cap=Decimal("10"), purpose="test", note_id=uuid4(), system="s", user="u")
