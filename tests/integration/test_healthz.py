import httpx

from saalr_api.main import create_app


async def test_healthz_reports_db_ok():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}