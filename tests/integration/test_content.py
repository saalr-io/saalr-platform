import httpx
from sqlalchemy import text

from saalr_api.main import create_app

_FREE = "what-is-an-option"
_PRO = "iron-condor-construction"


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
                           {"t": tenant_id})


async def _tid(c, h):
    return (await c.get("/me", headers=h)).json()["tenant"]["id"]


async def test_list_modules_shows_locked_and_aggregate(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu1@x.com"}
            body = (await c.get("/content/modules", headers=h)).json()
            assert body["total"] >= 6 and body["completed"] == 0
            by = {m["slug"]: m for m in body["modules"]}
            assert by[_FREE]["locked"] is False and by[_FREE]["status"] == "not_started"
            assert by[_PRO]["locked"] is True
            assert "body" not in by[_FREE]


async def test_get_free_module_marks_in_progress(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu2@x.com"}
            r = await c.get(f"/content/modules/{_FREE}", headers=h)
            assert r.status_code == 200 and r.json()["body"] and r.json()["status"] == "in_progress"
            assert (await c.get(f"/content/modules/{_FREE}", headers=h)).json()["status"] == "in_progress"
            prog = (await c.get("/content/progress", headers=h)).json()
            assert prog["in_progress"] == 1 and prog["completed"] == 0


async def test_pro_module_gated_then_unlocked(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu3@x.com"}
            r = await c.get(f"/content/modules/{_PRO}", headers=h)
            assert r.status_code == 402 and r.json()["detail"]["error"]["code"] == "ENTITLEMENT_CONTENT_REQUIRES_PRO"
            await _make_pro(admin_engine, await _tid(c, h))
            r2 = await c.get(f"/content/modules/{_PRO}", headers=h)
            assert r2.status_code == 200 and r2.json()["body"]


async def test_complete_sets_completed_and_no_downgrade(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu4@x.com"}
            r = await c.post(f"/content/modules/{_FREE}/complete", headers=h)
            assert r.status_code == 200 and r.json()["status"] == "completed" and r.json()["completed_at"]
            assert (await c.get(f"/content/modules/{_FREE}", headers=h)).json()["status"] == "completed"
            assert (await c.get("/content/progress", headers=h)).json()["completed"] == 1


async def test_complete_unknown_404_and_search_validation(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:edu5@x.com"}
            assert (await c.post("/content/modules/nope/complete", headers=h)).status_code == 404
            assert (await c.get("/content/search?q=", headers=h)).status_code == 400
            hits = (await c.get("/content/search?q=theta", headers=h)).json()["results"]
            assert hits and hits[0]["slug"] and "score" in hits[0]


async def test_progress_is_tenant_isolated(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            ha = {"Authorization": "Bearer dev:edu-a@x.com"}
            hb = {"Authorization": "Bearer dev:edu-b@x.com"}
            await c.post(f"/content/modules/{_FREE}/complete", headers=ha)
            assert (await c.get("/content/progress", headers=hb)).json()["completed"] == 0
