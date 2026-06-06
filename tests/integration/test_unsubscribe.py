import httpx
from sqlalchemy import text
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_unsubscribe_flips_opt_in_and_is_idempotent(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            await c.get("/me", headers={"Authorization": "Bearer dev:unsub@x.com"})
        async with admin_engine.begin() as conn:
            await conn.execute(text("UPDATE users SET marketing_opt_in=true WHERE email='unsub@x.com'"))
            tok = (await conn.execute(text("SELECT unsubscribe_token FROM users WHERE email='unsub@x.com'"))).scalar_one()
        async with _client(app) as c:
            r1 = await c.get(f"/unsubscribe?token={tok}")
            r2 = await c.get(f"/unsubscribe?token={tok}")  # idempotent
            bad = await c.get("/unsubscribe?token=00000000-0000-0000-0000-000000000000")
            malformed = await c.get("/unsubscribe?token=not-a-uuid")
    assert r1.status_code == 200 and r1.json()["unsubscribed"] is True
    assert r2.status_code == 200
    assert bad.status_code == 200  # neutral, no enumeration
    assert malformed.status_code == 200
    async with admin_engine.begin() as conn:
        opt = (await conn.execute(text("SELECT marketing_opt_in FROM users WHERE email='unsub@x.com'"))).scalar_one()
    assert opt is False
