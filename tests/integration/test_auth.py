import httpx
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.db.session import tenant_session


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_dev_login_and_me_bootstrap(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.post("/auth/dev/login", json={"email": "Alice@Acme.com"})
            assert r.status_code == 200
            token = r.json()["token"]
            assert token == "dev:alice@acme.com"

            me = await c.get("/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            body = me.json()
            assert body["user"]["email"] == "alice@acme.com"
            assert body["tenant"]["display_name"] == "alice"
            assert body["tier"] == "free"
            assert body["entitlements"]["brokers"] == 0
            assert body["entitlements"]["research_agent"] is False


async def test_dev_premium_email_defaults_to_premium(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            me = (await c.get("/me", headers={"Authorization": "Bearer dev:founder@saalr.com"})).json()
    assert me["tier"] == "premium"
    assert me["entitlements"]["vol_surface"] is True
    assert me["entitlements"]["ml_forecast"] is True


async def test_dev_premium_survives_subscriptions_truncate(admin_engine, app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:founder@saalr.com"}
            first = (await c.get("/me", headers=h)).json()
            assert first["tier"] == "premium"
            # Integration suites TRUNCATE subscriptions on the shared DB; the founder must
            # not be stranded on free — the resolver re-applies premium on the next call.
            async with admin_engine.begin() as conn:
                await conn.execute(text("TRUNCATE subscriptions CASCADE"))
            again = (await c.get("/me", headers=h)).json()
    assert again["tier"] == "premium"
    assert again["tenant"]["id"] == first["tenant"]["id"]


async def test_me_is_idempotent(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:bob@x.com"}
            first = (await c.get("/me", headers=h)).json()
            second = (await c.get("/me", headers=h)).json()
    assert first["tenant"]["id"] == second["tenant"]["id"]
    # exactly one tenant exists for bob
    async with tenant_session(app_sessionmaker, first["tenant"]["id"]) as s:
        count = (await s.execute(text("SELECT count(*) FROM tenants"))).scalar_one()
    assert count == 1


async def test_rls_isolation_between_principals(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            ta = (await c.get("/me", headers={"Authorization": "Bearer dev:a@x.com"})).json()["tenant"]["id"]
            tb = (await c.get("/me", headers={"Authorization": "Bearer dev:b@x.com"})).json()["tenant"]["id"]
    assert ta != tb
    # principal A's session sees only A's tenant
    async with tenant_session(app_sessionmaker, ta) as s:
        rows = {str(r[0]) for r in (await s.execute(text("SELECT tenant_id FROM tenants"))).all()}
    assert rows == {ta}


async def test_missing_token_is_401(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.get("/me")
    assert r.status_code == 401
    assert r.json()["detail"]["error"]["code"] == "AUTH_INVALID_TOKEN"


async def test_garbage_token_is_401(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.get("/me", headers={"Authorization": "Bearer nonsense"})
    assert r.status_code == 401
