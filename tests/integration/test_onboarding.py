import httpx
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_onboarding_complete_and_idempotent(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ob1@x.com"}
            assert (await c.get("/onboarding", headers=h)).json() == {"steps": [], "all_done": False}
            r = await c.post("/onboarding/complete", json={"step": "build_strategy"}, headers=h)
            assert r.status_code == 200 and "build_strategy" in r.json()["steps"]
            await c.post("/onboarding/complete", json={"step": "build_strategy"}, headers=h)  # idempotent
            got = (await c.get("/onboarding", headers=h)).json()
            assert got["steps"].count("build_strategy") == 1 and got["all_done"] is False
            bad = await c.post("/onboarding/complete", json={"step": "nope"}, headers=h)
            assert bad.status_code == 400


async def test_onboarding_is_tenant_isolated(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            await c.post("/onboarding/complete", json={"step": "see_regime"},
                         headers={"Authorization": "Bearer dev:ob-a@x.com"})
            other = (await c.get("/onboarding", headers={"Authorization": "Bearer dev:ob-b@x.com"})).json()
    assert other["steps"] == []
