import httpx

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_cors_allows_tauri_origin(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.get("/healthz", headers={"Origin": "http://tauri.localhost"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://tauri.localhost"


async def test_cors_omits_header_for_disallowed_origin(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.get("/healthz", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") is None
