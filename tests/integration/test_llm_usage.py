from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import httpx

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _me(c, h):
    body = (await c.get("/me", headers=h)).json()
    return UUID(body["tenant"]["id"]), UUID(body["user"]["id"])


async def test_record_and_month_to_date_sum(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:llm1@x.com"}
            tid, uid = await _me(c, h)
            async with tenant_session(app.state.sessionmaker, tid) as s:
                await llm_repo.record_usage(s, tenant_id=tid, user_id=uid, provider="stub",
                                            model="stub-chat", prompt_tokens=10, completion_tokens=5,
                                            cost_usd=Decimal("0.30"), purpose="research_note")
                await llm_repo.record_usage(s, tenant_id=tid, user_id=uid, provider="openai",
                                            model="gpt-4o-mini", prompt_tokens=10, completion_tokens=5,
                                            cost_usd=Decimal("0.45"), purpose="research_note")
            now = datetime.now(timezone.utc)
            async with tenant_session(app.state.sessionmaker, tid) as s:
                mtd = await llm_repo.month_to_date_cost(s, tid, now - timedelta(days=400))
                assert mtd == Decimal("0.750000")
                future = await llm_repo.month_to_date_cost(s, tid, now + timedelta(days=1))
                assert future == Decimal("0")
