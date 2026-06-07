import httpx
from sqlalchemy import text
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_marketing_audience_view_lists_user(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            await c.get("/me", headers={"Authorization": "Bearer dev:aud1@x.com"})
    async with admin_engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT email, tier, marketing_opt_in, has_strategy FROM marketing_audience WHERE email=:e"),
            {"e": "aud1@x.com"})).mappings().first()
    assert row is not None
    assert row["tier"] == "free" and row["marketing_opt_in"] is False
    assert row["has_strategy"] is False
