# Live-trading promotion (OMS-4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate the paper→live strategy promotion behind a step-up token (MFA-recent), a live-trading entitlement, and a ≥14-day paper track record, via a dedicated `/promote` endpoint.

**Architecture:** A pure `evaluate_promotion(...)` in `saalr_core/strategies/promotion.py` decides the gates (no DB/Redis/clock). The API layer feeds it the strategy state, the tier's `brokers` entitlement, the timestamp of the strategy's first paper order, and whether a single-use Redis step-up token verified. A `/promote/challenge` endpoint issues the token; `/promote` runs the gates, sets `promoted_to_live_at`, and writes a `strategy.promoted` audit row. The generic `/transition` endpoint refuses paper→live.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Postgres+RLS, Redis (`redis.asyncio`), pytest.

**Spec:** `docs/superpowers/specs/2026-06-02-live-promotion-oms4-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- DB tests need Postgres on **55432** and Redis on **6379**. Prefix pytest with:
  `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <args>`
- Error shape across the API: `HTTPException(status, {"error": {"code", "message"}})` → client sees `resp.json()["detail"]["error"]["code"]`.
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore`, `uv.lock`, or `tools/`. Never read/print/commit `.env`.

---

### Task 1: Pure promotion gates (`saalr_core/strategies/promotion.py`)

**Files:**
- Create: `packages/core/saalr_core/strategies/promotion.py`
- Test: `packages/core/tests/test_promotion.py`

This is pure (no DB/Redis/clock — `now` is injected), unit-tested in the default gate.

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_promotion.py`:

```python
from datetime import datetime, timedelta, timezone

from saalr_core.strategies.promotion import PromotionDecision, evaluate_promotion

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)


def _eval(state="paper", brokers=2, first=NOW - timedelta(days=20), step_up_ok=True):
    return evaluate_promotion(state, brokers, first, NOW, step_up_ok)


def test_all_gates_pass():
    d = _eval()
    assert isinstance(d, PromotionDecision) and d.ok and d.code is None


def test_not_in_paper_fails_first():
    d = _eval(state="backtested")
    assert not d.ok and d.code == "STRATEGY_NOT_IN_PAPER"


def test_entitlement_gate():
    d = _eval(brokers=0)
    assert not d.ok and d.code == "ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO"


def test_no_paper_orders_is_insufficient():
    d = _eval(first=None)
    assert not d.ok and d.code == "STRATEGY_INSUFFICIENT_PAPER_HISTORY"
    assert d.details == {"days_traded": 0, "days_required": 14}


def test_thirteen_days_insufficient():
    d = _eval(first=NOW - timedelta(days=13, hours=23))
    assert not d.ok and d.code == "STRATEGY_INSUFFICIENT_PAPER_HISTORY"
    assert d.details["days_traded"] == 13


def test_exactly_fourteen_days_ok():
    d = _eval(first=NOW - timedelta(days=14))
    assert d.ok


def test_missing_step_up_is_mfa_required():
    d = _eval(step_up_ok=False)
    assert not d.ok and d.code == "AUTH_MFA_REQUIRED"


def test_gate_order_entitlement_before_history():
    # free tier AND no history -> entitlement reported first
    d = evaluate_promotion("paper", 0, None, NOW, False)
    assert d.code == "ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_promotion.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_core.strategies.promotion`.

- [ ] **Step 3: Implement**

Create `packages/core/saalr_core/strategies/promotion.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PromotionDecision:
    ok: bool
    code: str | None = None
    message: str | None = None
    details: dict | None = None


def evaluate_promotion(state: str, brokers_entitlement: int,
                       first_paper_order_at: datetime | None, now: datetime,
                       step_up_ok: bool, min_paper_days: int = 14) -> PromotionDecision:
    """Pure paper->live promotion gate. Returns the first failing gate, else ok=True.

    Order: in-paper-state -> live-trading entitlement -> 14-day paper track record -> step-up (MFA).
    `now` and `first_paper_order_at` are injected so this is deterministic and DB/Redis-free.
    """
    if state != "paper":
        return PromotionDecision(False, "STRATEGY_NOT_IN_PAPER",
                                 "only a paper strategy can be promoted to live")
    if brokers_entitlement <= 0:
        return PromotionDecision(False, "ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO",
                                 "live trading requires a Pro or Premium plan")
    days_traded = (now - first_paper_order_at).days if first_paper_order_at is not None else 0
    if first_paper_order_at is None or days_traded < min_paper_days:
        return PromotionDecision(False, "STRATEGY_INSUFFICIENT_PAPER_HISTORY",
                                 f"needs {min_paper_days} days of paper trading before going live",
                                 {"days_traded": days_traded, "days_required": min_paper_days})
    if not step_up_ok:
        return PromotionDecision(False, "AUTH_MFA_REQUIRED",
                                 "step-up verification required to go live")
    return PromotionDecision(True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest packages/core/tests/test_promotion.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/strategies/promotion.py packages/core/tests/test_promotion.py
git add packages/core/saalr_core/strategies/promotion.py packages/core/tests/test_promotion.py
git commit -m "feat(strategies): pure evaluate_promotion gates for paper->live"
```

---

### Task 2: Step-up token (`apps/api/saalr_api/strategies/stepup.py`)

**Files:**
- Create: `apps/api/saalr_api/strategies/stepup.py`
- Test: `tests/test_stepup.py`

Redis single-use token, mirrors `apps/api/saalr_api/auth/magic.py`. Tested with an in-memory fake (no real Redis, no DB needed). The test lives at `tests/test_stepup.py` (NOT under `tests/integration/`) on purpose: the integration conftest has a session-autouse `_migrate` fixture that would otherwise force a DB connection for this pure test.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stepup.py`:

```python
from saalr_api.strategies.stepup import issue_step_up, verify_step_up


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def getdel(self, key):
        return self.store.pop(key, None)


async def test_issue_then_verify_consumes_single_use():
    r = _FakeRedis()
    token = await issue_step_up(r, "user-1")
    assert token
    assert await verify_step_up(r, "user-1", token) is True
    assert await verify_step_up(r, "user-1", token) is False  # single-use


async def test_blank_token_is_false():
    assert await verify_step_up(_FakeRedis(), "user-1", None) is False
    assert await verify_step_up(_FakeRedis(), "user-1", "") is False


async def test_token_is_scoped_to_user():
    r = _FakeRedis()
    token = await issue_step_up(r, "user-1")
    assert await verify_step_up(r, "user-2", token) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_stepup.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_api.strategies.stepup`.

- [ ] **Step 3: Implement**

Create `apps/api/saalr_api/strategies/stepup.py`:

```python
from __future__ import annotations

import secrets

from redis.asyncio import Redis

_PREFIX = "stepup:promote:"
_TTL_SECONDS = 300  # "MFA recent within 5 minutes"


async def issue_step_up(redis: Redis, user_id) -> str:
    """Issue a single-use step-up token for the user, valid for 5 minutes."""
    token = secrets.token_urlsafe(32)
    await redis.set(f"{_PREFIX}{user_id}:{token}", "1", ex=_TTL_SECONDS)
    return token


async def verify_step_up(redis: Redis, user_id, token) -> bool:
    """Atomically consume the token (single-use). False if blank/absent/expired."""
    if not token:
        return False
    return bool(await redis.getdel(f"{_PREFIX}{user_id}:{token}"))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_stepup.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/strategies/stepup.py tests/test_stepup.py
git add apps/api/saalr_api/strategies/stepup.py tests/test_stepup.py
git commit -m "feat(strategies): Redis single-use step-up token (5-min TTL)"
```

---

### Task 3: Promotion API — repo helpers, endpoints, `/transition` guard

**Files:**
- Modify: `apps/api/saalr_api/strategies/repo.py` (add `first_paper_order_at`, `record_promotion`, `write_strategy_audit`)
- Modify: `apps/api/saalr_api/strategies/router.py` (add `/promote/challenge`, `/promote`; guard `/transition`)
- Test: `tests/integration/test_promotion.py`

Needs Postgres on 55432 + Redis on 6379 (the app lifespan connects to `settings.redis_url`). Use the DB env prefix from the conventions block.

- [ ] **Step 1: Write the failing integration tests**

Create `tests/integration/test_promotion.py`:

```python
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
            # replaying the consumed token -> 401
            r2 = await c.post(f"/v1/strategies/{sid}/promote", headers={**h, "X-Step-Up-Token": token})
            assert r2.status_code == 409  # now live, not paper -> NOT_IN_PAPER (token already consumed too)
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
```

- [ ] **Step 2: Run to verify it fails**

Run (with the DB env prefix): `uv run pytest tests/integration/test_promotion.py -q`
Expected: FAIL (no `/promote` routes → 404/405; the transition-block test fails because paper→live currently succeeds).

- [ ] **Step 3: Add the repo helpers**

In `apps/api/saalr_api/strategies/repo.py`, change the imports line `from sqlalchemy import select` to:

```python
from sqlalchemy import select, text
```

Add this import after the existing model import:

```python
from saalr_core.db.models.audit import AuditLog
```

Append these functions to the file:

```python
async def first_paper_order_at(session: AsyncSession, strategy_id: UUID):
    """Timestamp of the strategy's earliest paper order (RLS-scoped), or None."""
    row = (await session.execute(text(
        "SELECT MIN(o.created_at) AS first FROM orders o "
        "JOIN broker_accounts b ON b.broker_account_id = o.broker_account_id "
        "WHERE o.strategy_id = :sid AND b.broker = 'paper'"),
        {"sid": str(strategy_id)})).first()
    return row.first if row else None


async def record_promotion(session: AsyncSession, row: Strategy, now) -> Strategy:
    row.state = "live"
    row.promoted_to_live_at = now
    await session.flush()
    return row


async def write_strategy_audit(session: AsyncSession, *, tenant_id, user_id, strategy_id,
                               action, before, after, request_id) -> None:
    session.add(AuditLog(
        audit_id=new_id(), tenant_id=tenant_id, user_id=user_id, action=action,
        target_type="strategy", target_id=strategy_id, before_state=before, after_state=after,
        request_id=request_id,
    ))
    await session.flush()
```

- [ ] **Step 4: Add the endpoints + transition guard to the router**

In `apps/api/saalr_api/strategies/router.py`:

Change the imports. Replace:
```python
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
```
with:
```python
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
```

Add these imports alongside the other `saalr_core` imports:
```python
from saalr_core.ids import new_id
from saalr_core.strategies.promotion import evaluate_promotion
```
and alongside `from . import repo, service`:
```python
from .stepup import issue_step_up, verify_step_up
```

Add this module-level constant after `router = APIRouter(...)`:
```python
_PROMO_STATUS = {
    "STRATEGY_NOT_IN_PAPER": 409,
    "ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO": 402,
    "STRATEGY_INSUFFICIENT_PAPER_HISTORY": 409,
    "AUTH_MFA_REQUIRED": 401,
}
```

Replace the entire `do_transition` handler with this version (adds the paper→live guard and keeps everything else):
```python
@router.post("/{strategy_id}/transition")
async def do_transition(strategy_id: UUID, body: TransitionIn,
                        ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    try:
        current = StrategyState(row.state)
        target = StrategyState(body.target_state)
    except ValueError as exc:
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": str(exc)}})
    if current == StrategyState.PAPER and target == StrategyState.LIVE:
        raise HTTPException(409, {"error": {"code": "STRATEGY_USE_PROMOTE_ENDPOINT",
                                            "message": "promote paper->live via POST /promote"}})
    try:
        new_state = transition(current, target)
    except IllegalTransition as exc:
        raise HTTPException(409, {"error": {"code": "STRATEGY_ILLEGAL_TRANSITION", "message": str(exc)}})
    await repo.update_strategy(session, row, state=new_state.value)
    return _out(row)
```

Add these two handlers immediately after `do_transition` (before the `archive` handler):
```python
@router.post("/{strategy_id}/promote/challenge")
async def promote_challenge(strategy_id: UUID, request: Request,
                            ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    token = await issue_step_up(request.app.state.redis, principal.user_id)
    return {"step_up_token": token, "expires_in": 300}


@router.post("/{strategy_id}/promote")
async def promote(strategy_id: UUID, request: Request,
                  x_step_up_token: str | None = Header(default=None, alias="X-Step-Up-Token"),
                  ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    step_up_ok = await verify_step_up(request.app.state.redis, principal.user_id, x_step_up_token)
    first = await repo.first_paper_order_at(session, strategy_id)
    brokers = entitlements_for(principal.tier)["brokers"]
    now = datetime.now(timezone.utc)
    decision = evaluate_promotion(row.state, brokers, first, now, step_up_ok)
    if not decision.ok:
        err: dict = {"code": decision.code, "message": decision.message}
        if decision.details:
            err["details"] = decision.details
        raise HTTPException(_PROMO_STATUS[decision.code], {"error": err})
    request_id = request.headers.get("X-Request-Id") or str(new_id())
    await repo.record_promotion(session, row, now)
    await repo.write_strategy_audit(session, tenant_id=principal.tenant_id, user_id=principal.user_id,
                                    strategy_id=strategy_id, action="strategy.promoted",
                                    before={"state": "paper"}, after={"state": "live"},
                                    request_id=request_id)
    return _out(row)
```

> `entitlements_for` is already imported at the top of `router.py`. `_out`, `_not_found`, `StrategyState`, `IllegalTransition`, `transition`, `repo` are already in scope.

- [ ] **Step 5: Run to verify the suite passes**

Run (DB env prefix): `uv run pytest tests/integration/test_promotion.py -q`
Expected: PASS (8 passed).

- [ ] **Step 6: Regression — the existing strategies suite still passes**

Run (DB env prefix): `uv run pytest tests/integration/test_strategies.py -q`
Expected: PASS (the prior strategy CRUD/transition tests are unaffected).

- [ ] **Step 7: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/strategies tests/integration/test_promotion.py
git add apps/api/saalr_api/strategies/repo.py apps/api/saalr_api/strategies/router.py tests/integration/test_promotion.py
git commit -m "feat(strategies): /promote endpoint with MFA step-up + 14-day gate; block paper->live transition"
```

---

## Final verification (after all tasks)

- [ ] Core gate: `uv run pytest packages/core/tests/test_promotion.py -q` — 8 passed.
- [ ] Step-up unit (no DB): `uv run pytest tests/test_stepup.py -q` — 3 passed.
- [ ] Default integration (DB env prefix): `uv run pytest tests/integration/test_promotion.py tests/integration/test_strategies.py -q` — all green.
- [ ] Lint: `uvx ruff check packages/core/saalr_core/strategies apps/api/saalr_api/strategies tests/integration/test_promotion.py tests/test_stepup.py` — clean.
- [ ] Final code-review subagent over the whole slice diff.

## Self-review notes
- **No migration:** the 14-day gate reads `orders` (joined to `broker_accounts.broker='paper'`); the entitlement reuses `brokers>0`; `promoted_to_live_at` + `audit_log` already exist. Confirmed against the spec.
- **Gate order** matches the spec exactly (state → entitlement → history → MFA), and the happy-path test's token-replay assertion is 409 (the strategy is `live` after the first call, so the state gate fires before MFA — and the token was consumed regardless).
- **`paused→live` stays ungated** (only `current==paper and target==live` is blocked in `/transition`); the resume test covers it.
