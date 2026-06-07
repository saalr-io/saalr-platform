import httpx
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_me_includes_account_fields(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            me = (await c.get("/me", headers={"Authorization": "Bearer dev:acc1@x.com"})).json()
    assert me["marketing_opt_in"] is False and me["preferred_tz"] and me["deletion_requested"] is False


async def test_opt_in_profile_and_deletion(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:acc2@x.com"}
            await c.get("/me", headers=h)
            assert (await c.post("/me/marketing/opt-in", json={"opt_in": True}, headers=h)).status_code == 200
            assert (await c.get("/me", headers=h)).json()["marketing_opt_in"] is True
            assert (await c.patch("/me/profile", json={"preferred_tz": "America/New_York"}, headers=h)).status_code == 200
            assert (await c.get("/me", headers=h)).json()["preferred_tz"] == "America/New_York"
            bad = await c.patch("/me/profile", json={"nope": "x"}, headers=h)
            assert bad.status_code == 422
            assert (await c.post("/me/request-deletion", headers=h)).json()["requested"] is True
            assert (await c.get("/me", headers=h)).json()["deletion_requested"] is True
