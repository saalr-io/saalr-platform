import httpx

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_create_alpaca_account(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp1@x.com"}
            r = await c.post("/v1/broker-accounts",
                             json={"broker": "alpaca", "account_label": "Live-ish",
                                   "credential_ref": "env:ALPACA_PAPER", "is_paper": True}, headers=h)
            assert r.status_code == 200, r.text
            assert r.json()["broker"] == "alpaca"
            assert "credential_ref" not in r.json()  # the credential pointer never leaks in the response


async def test_create_alpaca_account_requires_credential_ref(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp2@x.com"}
            r = await c.post("/v1/broker-accounts",
                             json={"broker": "alpaca", "account_label": "x"}, headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "VALIDATION_MISSING_CREDENTIAL_REF"
