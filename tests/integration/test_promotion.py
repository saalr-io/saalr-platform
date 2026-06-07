from uuid import uuid4

import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _tenant_id(c, h):
    return (await c.get("/me", headers=h)).json()["tenant"]["id"]


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
                           {"t": tenant_id})


_STRAT = {"name": "S", "config": {"underlying": "AAPL",
          "legs": [{"kind": "option", "option_type": "CALL", "side": "BUY",
                    "strike": 100, "expiry": "2026-12-18", "qty": 1, "entry_price": 6.0}]}}


async def _new_strategy(c, h):
    return (await c.post("/v1/strategies", json=_STRAT, headers=h)).json()["strategy_id"]


async def _to_paper(c, h, sid):
    await c.post(f"/v1/strategies/{sid}/transition", json={"target_state": "backtested"}, headers=h)
    r = await c.post(f"/v1/strategies/{sid}/transition", json={"target_state": "paper"}, headers=h)
    assert r.json()["state"] == "paper"


async def _paper_account(c, h):
    return (await c.post("/v1/broker-accounts", json={"account_label": "P"}, headers=h)).json()["broker_account_id"]


async def _seed_paper_order(admin_engine, tenant_id, strategy_id, broker_account_id, days_ago):
    async with admin_engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO orders (order_id, tenant_id, strategy_id, broker_account_id, symbol,
                                side, qty, order_type, time_in_force, status, created_at)
            VALUES (:oid, :t, :s, :b, 'AAPL', 'buy', 1, 'market', 'day', 'filled',
                    now() - make_interval(days => :d))
        """), {"oid": str(uuid4()), "t": tenant_id, "s": strategy_id, "b": broker_account_id, "d": days_ago})


async def test_challenge_returns_token(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pr1@x.com"}
            sid = await _new_strategy(c, h)
            r = await c.post(f"/v1/strategies/{sid}/promote/challenge", headers=h)
            assert r.status_code == 200 and r.json()["expires_in"] == 300 and r.json()["step_up_token"]


async def test_promote_not_in_paper_409(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pr2@x.com"}
            sid = await _new_strategy(c, h)  # draft
            r = await c.post(f"/v1/strategies/{sid}/promote", headers=h)
            assert r.status_code == 409 and r.json()["detail"]["error"]["code"] == "STRATEGY_NOT_IN_PAPER"


async def test_promote_free_tier_402(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pr3@x.com"}
            sid = await _new_strategy(c, h)
            await _to_paper(c, h, sid)
            r = await c.post(f"/v1/strategies/{sid}/promote", headers=h)
            assert r.status_code == 402
            assert r.json()["detail"]["error"]["code"] == "ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO"


async def test_promote_insufficient_history_409(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pr4@x.com"}
            sid = await _new_strategy(c, h)
            await _to_paper(c, h, sid)
            await _make_pro(admin_engine, await _tenant_id(c, h))
            r = await c.post(f"/v1/strategies/{sid}/promote", headers=h)
            assert r.status_code == 409
            body = r.json()["detail"]["error"]
            assert body["code"] == "STRATEGY_INSUFFICIENT_PAPER_HISTORY"
            assert body["details"] == {"days_traded": 0, "days_required": 14}


async def test_promote_requires_step_up_401(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pr5@x.com"}
            sid = await _new_strategy(c, h)
            await _to_paper(c, h, sid)
            tid = await _tenant_id(c, h)
            await _make_pro(admin_engine, tid)
            acct = await _paper_account(c, h)
            await _seed_paper_order(admin_engine, tid, sid, acct, days_ago=15)
            r = await c.post(f"/v1/strategies/{sid}/promote", headers=h)  # no X-Step-Up-Token
            assert r.status_code == 401 and r.json()["detail"]["error"]["code"] == "AUTH_MFA_REQUIRED"


async def test_promote_happy_path_and_token_single_use(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pr6@x.com"}
            sid = await _new_strategy(c, h)
            await _to_paper(c, h, sid)
            tid = await _tenant_id(c, h)
            await _make_pro(admin_engine, tid)
            acct = await _paper_account(c, h)
            await _seed_paper_order(admin_engine, tid, sid, acct, days_ago=15)
            token = (await c.post(f"/v1/strategies/{sid}/promote/challenge", headers=h)).json()["step_up_token"]
            r = await c.post(f"/v1/strategies/{sid}/promote", headers={**h, "X-Step-Up-Token": token})
            assert r.status_code == 200 and r.json()["state"] == "live"
            # replaying the consumed token -> 409 (strategy now live, not paper)
            r2 = await c.post(f"/v1/strategies/{sid}/promote", headers={**h, "X-Step-Up-Token": token})
            assert r2.status_code == 409
    async with admin_engine.begin() as conn:
        prom = (await conn.execute(text(
            "SELECT promoted_to_live_at FROM strategies WHERE strategy_id=:s"), {"s": sid})).scalar_one()
        assert prom is not None
        n = (await conn.execute(text(
            "SELECT count(*) FROM audit_log WHERE action='strategy.promoted' AND target_id=:s"),
            {"s": sid})).scalar_one()
        assert n == 1


async def test_transition_paper_to_live_blocked(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pr7@x.com"}
            sid = await _new_strategy(c, h)
            await _to_paper(c, h, sid)
            r = await c.post(f"/v1/strategies/{sid}/transition", json={"target_state": "live"}, headers=h)
            assert r.status_code == 409
            assert r.json()["detail"]["error"]["code"] == "STRATEGY_USE_PROMOTE_ENDPOINT"


async def test_resume_paused_to_live_allowed(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:pr8@x.com"}
            sid = await _new_strategy(c, h)
            async with admin_engine.begin() as conn:
                await conn.execute(text("UPDATE strategies SET state='paused' WHERE strategy_id=:s"),
                                   {"s": sid})
            r = await c.post(f"/v1/strategies/{sid}/transition", json={"target_state": "live"}, headers=h)
            assert r.status_code == 200 and r.json()["state"] == "live"
