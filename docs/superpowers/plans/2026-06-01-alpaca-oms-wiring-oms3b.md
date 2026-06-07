# Alpaca OMS wiring + reconciliation (OMS-3b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `broker='alpaca'` work end-to-end — place an order that rests `submitted` at Alpaca, then a reconciliation worker polls and fills it (executions + positions) and advances `last_reconciled_at`.

**Architecture:** A `CredentialResolver` (env-prefix) builds an `AlpacaAdapter` from a broker_account's `credential_ref`. `place_order` routes `broker=='alpaca'` to a synchronous submit (no fill; rests `submitted`); shared OMS row-CRUD moves to `saalr_core/oms/repo.py` so a new `apps/oms-worker` can call a pure `reconcile_account(session, adapter, account)` without depending on `saalr-api`. Adapter construction goes through an injectable `app.state.alpaca_adapter_factory` so the default test gate never installs alpaca-py.

**Tech Stack:** Python 3.12, uv workspace, SQLAlchemy 2.0 async, FastAPI, alpaca-py (optional extra), Postgres+RLS (`tenant_session` GUC), pytest.

**Spec:** `docs/superpowers/specs/2026-06-01-alpaca-oms-wiring-oms3b-design.md`

**Conventions for every task:**
- Tests/lint run from the repo root `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`.
- DB tests need Postgres on **55432**; the env override is already in place for this repo (`ADMIN_DATABASE_URL`/`APP_DATABASE_URL`). Integration tests live under `tests/integration` and use the `app_sessionmaker`/`admin_engine` fixtures.
- Default gate: `uv run pytest` (alpaca-py NOT installed). Worker tests: `uv run --package saalr-oms-worker pytest apps/oms-worker/tests`.
- Lint: `uvx ruff check`. Line length 100.
- Commit footer line: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Do NOT stage `.gitignore`, `tools/equity-screener/...`, or `uv.lock` changes. Never print/commit `.env`.

---

### Task 1: Credential resolver + adapter factory (`saalr_brokers/credentials.py`)

**Files:**
- Create: `packages/brokers/saalr_brokers/credentials.py`
- Test: `packages/brokers/tests/test_credentials.py`

This module is alpaca-free at import time (it imports `AlpacaAdapter`, whose alpaca imports are lazy), so its tests run under the default gate with no alpaca-py installed.

- [ ] **Step 1: Write the failing test**

Create `packages/brokers/tests/test_credentials.py`:

```python
import pytest

from saalr_brokers.alpaca import AlpacaAdapter
from saalr_brokers.credentials import (
    CredentialError,
    EnvCredentialResolver,
    build_alpaca_adapter,
)


def test_resolves_key_and_secret_from_prefix():
    env = {"ALPACA_PAPER_KEY": "ak", "ALPACA_PAPER_SECRET": "sk"}
    key, secret = EnvCredentialResolver(env).resolve("env:ALPACA_PAPER", is_paper=True)
    assert key == "ak" and secret == "sk"


def test_missing_env_prefix_raises():
    with pytest.raises(CredentialError):
        EnvCredentialResolver({}).resolve("paper:local", is_paper=True)


def test_missing_keys_raise():
    with pytest.raises(CredentialError):
        EnvCredentialResolver({"ALPACA_PAPER_KEY": "ak"}).resolve("env:ALPACA_PAPER", is_paper=True)


def test_build_alpaca_adapter_returns_adapter_without_importing_sdk():
    env = {"ALPACA_LIVE_KEY": "ak", "ALPACA_LIVE_SECRET": "sk"}
    adapter = build_alpaca_adapter("env:ALPACA_LIVE", False, EnvCredentialResolver(env))
    assert isinstance(adapter, AlpacaAdapter)
    assert adapter._is_paper is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/brokers/tests/test_credentials.py -q`
Expected: FAIL with `ModuleNotFoundError: saalr_brokers.credentials`.

- [ ] **Step 3: Write the implementation**

Create `packages/brokers/saalr_brokers/credentials.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from .alpaca import AlpacaAdapter


class CredentialError(Exception):
    """A broker credential could not be resolved. Never carries the secret values."""


@runtime_checkable
class CredentialResolver(Protocol):
    def resolve(self, credential_ref: str, is_paper: bool) -> tuple[str, str]:
        """Resolve a credential_ref to (api_key, api_secret)."""
        ...


class EnvCredentialResolver:
    """Resolves a credential_ref of the form 'env:PREFIX' to the env vars
    PREFIX_KEY and PREFIX_SECRET from an injected mapping (e.g. os.environ).

    The paper-vs-live distinction is encoded by convention in the ref
    ('env:ALPACA_PAPER' vs 'env:ALPACA_LIVE'); is_paper is passed through to the
    adapter and does not alter the lookup.
    """

    _PREFIX = "env:"

    def __init__(self, env: Mapping[str, str]) -> None:
        self._env = env

    def resolve(self, credential_ref: str, is_paper: bool) -> tuple[str, str]:
        if not credential_ref.startswith(self._PREFIX):
            raise CredentialError("credential_ref must start with 'env:'")
        prefix = credential_ref[len(self._PREFIX):]
        try:
            return self._env[f"{prefix}_KEY"], self._env[f"{prefix}_SECRET"]
        except KeyError as exc:
            raise CredentialError(f"missing env var for credential_ref {credential_ref!r}") from exc


def build_alpaca_adapter(
    credential_ref: str, is_paper: bool, resolver: CredentialResolver
) -> AlpacaAdapter:
    """Resolve credentials and construct an AlpacaAdapter (SDK-free until a method runs)."""
    key, secret = resolver.resolve(credential_ref, is_paper)
    return AlpacaAdapter(key, secret, is_paper=is_paper)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/brokers/tests/test_credentials.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/brokers
git add packages/brokers/saalr_brokers/credentials.py packages/brokers/tests/test_credentials.py
git commit -m "feat(brokers): env-prefix CredentialResolver + build_alpaca_adapter"
```

---

### Task 2: Move shared OMS row-CRUD into `saalr_core/oms/repo.py`

Move the generic row-CRUD that reconciliation will reuse into core, and re-export it from the API repo so existing call sites are unchanged. This is a **behaviour-neutral move** — the existing OMS integration suite is the regression test.

**Files:**
- Create: `packages/core/saalr_core/oms/repo.py`
- Modify: `apps/api/saalr_api/oms/repo.py` (remove the moved functions; re-export from core)
- Test (regression): `tests/integration/test_oms.py` (unchanged, must stay green)

- [ ] **Step 1: Create the core repo module**

Create `packages/core/saalr_core/oms/repo.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from saalr_core.db.models.audit import AuditLog
from saalr_core.db.models.trading import BrokerAccount, Execution, Order, Position
from saalr_core.ids import new_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_broker_account(session, broker_account_id) -> BrokerAccount | None:
    return await session.get(BrokerAccount, broker_account_id)


async def update_order(session, order: Order, **fields) -> Order:
    for k, v in fields.items():
        setattr(order, k, v)
    await session.flush()
    return order


async def insert_execution(session, *, tenant_id, order_id, broker_account_id, qty, price,
                           commission, broker_execution_id) -> None:
    session.add(Execution(
        execution_id=new_id(), tenant_id=tenant_id, order_id=order_id,
        broker_account_id=broker_account_id, qty=qty, price=price, commission=commission,
        broker_execution_id=broker_execution_id, executed_at=_utcnow(),
    ))
    await session.flush()


async def get_position(session, broker_account_id, symbol, option_type, strike, expiry) -> Position | None:
    stmt = select(Position).where(
        Position.broker_account_id == broker_account_id, Position.symbol == symbol,
        Position.option_type.is_(option_type) if option_type is None else Position.option_type == option_type,
    )
    stmt = stmt.where(Position.strike.is_(None) if strike is None else Position.strike == strike)
    stmt = stmt.where(Position.expiry.is_(None) if expiry is None else Position.expiry == expiry)
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_position(session, *, tenant_id, broker_account_id, symbol, option_type, strike,
                          expiry, new_qty: int, new_avg: Decimal) -> None:
    existing = await get_position(session, broker_account_id, symbol, option_type, strike, expiry)
    if new_qty == 0:
        if existing is not None:
            await session.delete(existing)
            await session.flush()
        return
    if existing is None:
        session.add(Position(
            position_id=new_id(), tenant_id=tenant_id, broker_account_id=broker_account_id,
            symbol=symbol, option_type=option_type, strike=strike, expiry=expiry,
            qty=new_qty, avg_entry_price=new_avg, opened_at=_utcnow(), last_updated_at=_utcnow(),
        ))
    else:
        existing.qty = new_qty
        existing.avg_entry_price = new_avg
        existing.last_updated_at = _utcnow()
    await session.flush()


async def write_audit(session, *, tenant_id, user_id, action, target_type, target_id,
                      before, after, request_id) -> None:
    session.add(AuditLog(
        audit_id=new_id(), tenant_id=tenant_id, user_id=user_id, action=action,
        target_type=target_type, target_id=target_id, before_state=before, after_state=after,
        request_id=request_id,
    ))
    await session.flush()


# --- reconciliation queries (new) ---
async def sum_executed_qty(session, order_id) -> int:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(Execution.qty), 0)).where(Execution.order_id == order_id)
        )
    ).scalar_one()
    return int(total)


async def list_open_orders_for_account(session, broker_account_id) -> list[Order]:
    return list((await session.execute(
        select(Order).where(
            Order.broker_account_id == broker_account_id,
            Order.status.in_(("submitted", "partial")),
        )
    )).scalars().all())


async def list_active_alpaca_accounts(session) -> list[BrokerAccount]:
    """All active alpaca broker accounts. Run on an ADMIN (RLS-bypassing) session for
    cross-tenant discovery; the per-account reconcile then runs inside a tenant_session."""
    return list((await session.execute(
        select(BrokerAccount).where(BrokerAccount.broker == "alpaca", BrokerAccount.status == "active")
    )).scalars().all())
```

- [ ] **Step 2: Re-export from the API repo and drop the moved bodies**

In `apps/api/saalr_api/oms/repo.py`:
- Remove the function bodies for `get_broker_account`, `update_order`, `insert_execution`, `get_position`, `upsert_position`, `write_audit`.
- Add this import near the top (after the existing imports):

```python
from saalr_core.oms.repo import (  # re-exported so existing call sites are unchanged
    get_broker_account,
    get_position,
    insert_execution,
    update_order,
    upsert_position,
    write_audit,
)
```
- Keep the API-only helpers in place: `create_broker_account`, `list_broker_accounts`, `find_order_by_idempotency`, `insert_order`, `account_balance`, `get_order`, `list_orders`, `list_positions`.
- Add `from saalr_core.oms import repo as _core_repo  # noqa` is NOT needed; the explicit re-export import above is enough. Add `__all__` only if ruff flags unused imports — instead, suppress with the inline `# re-exported` comment already shown and, if ruff still flags F401, add `# noqa: F401` to that import block.

- [ ] **Step 3: Run the regression suite**

Run: `uv run pytest tests/integration/test_oms.py -q`
Expected: PASS (7 passed) — identical behaviour, functions now sourced from core.

- [ ] **Step 4: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/oms apps/api/saalr_api/oms
git add packages/core/saalr_core/oms/repo.py apps/api/saalr_api/oms/repo.py
git commit -m "refactor(oms): move shared row-CRUD to saalr_core/oms/repo; api re-exports"
```

---

### Task 3: Allow Alpaca broker-account creation (API)

A broker_account must be able to have `broker='alpaca'` + a `credential_ref` for the rest of the slice to be reachable. Extend the create schema/repo/endpoint minimally.

**Files:**
- Modify: `apps/api/saalr_api/oms/schemas.py` (BrokerAccountCreate: `credential_ref`)
- Modify: `apps/api/saalr_api/oms/repo.py` (`create_broker_account` takes `credential_ref`)
- Modify: `apps/api/saalr_api/oms/router.py` (`create_account` allows alpaca)
- Test: `tests/integration/test_oms_alpaca.py` (new file; first test)

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_oms_alpaca.py`:

```python
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


async def test_create_alpaca_account_requires_credential_ref(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp2@x.com"}
            r = await c.post("/v1/broker-accounts",
                             json={"broker": "alpaca", "account_label": "x"}, headers=h)
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "VALIDATION_MISSING_CREDENTIAL_REF"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_oms_alpaca.py -q`
Expected: FAIL (400 "only paper accounts are supported" / missing field).

- [ ] **Step 3: Implement**

In `apps/api/saalr_api/oms/schemas.py`, replace `BrokerAccountCreate`:

```python
class BrokerAccountCreate(BaseModel):
    broker: str = "paper"
    account_label: str = Field(min_length=1)
    is_paper: bool = True
    credential_ref: str | None = None
```

In `apps/api/saalr_api/oms/repo.py`, change `create_broker_account` to take `credential_ref`:

```python
async def create_broker_account(session, tenant_id, user_id, broker, label, is_paper,
                                credential_ref="paper:local") -> BrokerAccount:
    row = BrokerAccount(
        broker_account_id=new_id(), tenant_id=tenant_id, user_id=user_id, broker=broker,
        account_label=label, credential_ref=credential_ref, is_paper=is_paper, status="active",
    )
    session.add(row)
    await session.flush()
    return row
```

In `apps/api/saalr_api/oms/router.py`, replace `create_account`:

```python
@router.post("/v1/broker-accounts")
async def create_account(body: BrokerAccountCreate,
                         ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    if body.broker not in ("paper", "alpaca"):
        raise HTTPException(400, {"error": {"code": "BROKER_NOT_SUPPORTED",
                                            "message": "broker not supported"}})
    if body.broker == "alpaca":
        if not body.credential_ref:
            raise HTTPException(422, {"error": {"code": "VALIDATION_MISSING_CREDENTIAL_REF",
                                                "message": "credential_ref is required for alpaca"}})
        a = await repo.create_broker_account(session, principal.tenant_id, principal.user_id,
                                             "alpaca", body.account_label, body.is_paper,
                                             body.credential_ref)
    else:
        a = await repo.create_broker_account(session, principal.tenant_id, principal.user_id,
                                             "paper", body.account_label, True)
    return _acct_out(a)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/integration/test_oms_alpaca.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/oms
git add apps/api/saalr_api/oms/schemas.py apps/api/saalr_api/oms/repo.py apps/api/saalr_api/oms/router.py tests/integration/test_oms_alpaca.py
git commit -m "feat(oms): allow alpaca broker-account creation with credential_ref"
```

---

### Task 4: Route `place_order` / `cancel_order` to Alpaca + injectable adapter factory

Wire the alpaca path: synchronous submit that rests `submitted` (no fill), BP from the broker, credential/broker errors → 502, broker reject → 422. Adapter construction is an injectable factory on `app.state` so tests inject a stub and the default gate never imports alpaca.

**Files:**
- Modify: `apps/api/saalr_api/oms/service.py` (alpaca branch + `_submit_alpaca` + cancel routing + logger + imports)
- Modify: `apps/api/saalr_api/oms/router.py` (thread `request.app.state.alpaca_adapter_factory`)
- Modify: `apps/api/saalr_api/main.py` (set `app.state.alpaca_adapter_factory`)
- Test: `tests/integration/test_oms_alpaca.py` (append tests with a stub factory)

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_oms_alpaca.py`:

```python
from decimal import Decimal

from saalr_brokers.alpaca import BrokerError
from saalr_brokers.credentials import CredentialError
from saalr_brokers.types import BrokerOrderResult


class _StubAlpaca:
    def __init__(self, *, balance=Decimal("100000"), result=None, raise_submit=None):
        self._balance = balance
        self._result = result or BrokerOrderResult("alp-1", "submitted")
        self._raise_submit = raise_submit
        self.cancelled = None

    async def get_account_balance(self):
        return self._balance

    async def submit_order(self, order, idempotency_key):
        if self._raise_submit:
            raise self._raise_submit
        return self._result

    async def cancel_order(self, broker_order_id):
        self.cancelled = broker_order_id
        return True


async def _alpaca_account(c, h, ref="env:ALPACA_PAPER"):
    r = await c.post("/v1/broker-accounts",
                     json={"broker": "alpaca", "account_label": "A", "credential_ref": ref,
                           "is_paper": True}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["broker_account_id"]


def _order(acct, **kw):
    base = {"broker_account_id": acct, "symbol": "AAPL", "side": "buy", "qty": 1, "order_type": "market"}
    base.update(kw)
    return base


async def test_alpaca_order_rests_submitted(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.alpaca_adapter_factory = lambda account: _StubAlpaca()
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp3@x.com"}
            acct = await _alpaca_account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "a1"})
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "submitted" and r.json()["broker_order_id"] == "alp-1"
            # no fill yet -> no position
            assert (await c.get("/v1/positions", headers=h)).json()["positions"] == []


async def test_alpaca_reject_maps_422(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.alpaca_adapter_factory = lambda account: _StubAlpaca(
            result=BrokerOrderResult("alp-2", "rejected", "insufficient buying power"))
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp4@x.com"}
            acct = await _alpaca_account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "a2"})
            assert r.status_code == 422
            assert r.json()["detail"]["error"]["code"] == "BROKER_REJECTED"


async def test_alpaca_bad_credentials_502(app_sessionmaker, admin_engine):
    def _factory(account):
        raise CredentialError("missing env var")

    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.alpaca_adapter_factory = _factory
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp5@x.com"}
            acct = await _alpaca_account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "a3"})
            assert r.status_code == 502
            assert r.json()["detail"]["error"]["code"] == "BROKER_CREDENTIALS_UNAVAILABLE"


async def test_alpaca_broker_error_leaves_pending(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.alpaca_adapter_factory = lambda account: _StubAlpaca(raise_submit=BrokerError("boom"))
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:alp6@x.com"}
            acct = await _alpaca_account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "a4"})
            assert r.status_code == 502
            assert r.json()["detail"]["error"]["code"] == "BROKER_UNAVAILABLE"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/integration/test_oms_alpaca.py -q`
Expected: FAIL (alpaca orders currently hit `400 BROKER_NOT_SUPPORTED`).

- [ ] **Step 3: Rewrite `place_order` + add `_submit_alpaca` + cancel routing**

In `apps/api/saalr_api/oms/service.py`:

Add imports near the top (after the existing imports):

```python
import logging

from saalr_brokers.alpaca import BrokerError
from saalr_brokers.credentials import CredentialError

_logger = logging.getLogger("saalr.oms")
```

Replace the whole `place_order` function (lines 58–158) with:

```python
async def place_order(session: AsyncSession, principal, body: OrderCreate, idempotency_key,
                      request_id, adapter_factory=None) -> dict:
    tenant_id, user_id = principal.tenant_id, principal.user_id
    settings = get_settings()

    existing = await repo.find_order_by_idempotency(session, tenant_id, idempotency_key)
    if existing is not None:
        return _out(existing)

    account = await repo.get_broker_account(session, UUID(body.broker_account_id))
    if account is None:
        raise _err("RESOURCE_NOT_FOUND", "broker account not found", 404)
    if account.status != "active":
        raise _err("BROKER_ACCOUNT_INACTIVE", "broker account is not active", 409)
    if account.broker not in ("paper", "alpaca"):
        raise _err("BROKER_NOT_SUPPORTED", f"broker {account.broker} not yet supported", 400)
    is_alpaca = account.broker == "alpaca"

    # Resolve the alpaca adapter up front so a credential failure happens before any row insert.
    adapter = None
    if is_alpaca:
        if adapter_factory is None:
            raise _err("BROKER_UNAVAILABLE", "no alpaca adapter configured", 502)
        try:
            adapter = adapter_factory(account)
        except CredentialError as exc:
            raise _err("BROKER_CREDENTIALS_UNAVAILABLE", "broker credentials unavailable", 502) from exc

    today = datetime.now(timezone.utc).date()
    try:
        mark = await model_mark(session, symbol=body.symbol.upper(), market="US",
                                option_type=body.option_type, strike=body.strike,
                                expiry=body.expiry, today=today)
    except NoMarketData as exc:
        if not is_alpaca:
            order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                            status="rejected", reject_reason_code="RISK_NO_MARKET_DATA",
                                            idempotency_key=idempotency_key)
            await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.rejected",
                                   target_type="order", target_id=order.order_id, before=None,
                                   after={"status": "rejected", "code": "RISK_NO_MARKET_DATA"},
                                   request_id=request_id)
            raise _err("RISK_NO_MARKET_DATA", str(exc)) from exc
        mark = None  # alpaca: the broker enforces; a missing model mark must not block submission

    req = _to_request(body)
    est_cost = estimate_cost(req, mark) if mark is not None else Decimal(0)
    if is_alpaca:
        try:
            balance = await adapter.get_account_balance()
        except BrokerError as exc:
            raise _err("BROKER_UNAVAILABLE", "broker unavailable", 502) from exc
    else:
        balance = await repo.account_balance(session, account.broker_account_id,
                                             Decimal(str(settings.paper_starting_cash)), tenant_id)

    strategy_state = None
    if body.strategy_id:
        strat = await strat_repo.get_strategy(session, UUID(body.strategy_id))
        strategy_state = strat.state if strat else "draft"  # missing -> not executable
    ctx = RiskContext(account_active=True, strategy_state=strategy_state, available_balance=balance,
                      estimated_cost=est_cost, recent_order_count=0, rate_limit=None)

    decision = run_gates(req, ctx)
    if not decision.ok:
        order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                        status="rejected", reject_reason_code=decision.code,
                                        idempotency_key=idempotency_key)
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.rejected",
                               target_type="order", target_id=order.order_id, before=None,
                               after={"status": "rejected", "code": decision.code}, request_id=request_id)
        raise _err(decision.code, decision.message or decision.code)

    try:
        order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                        status="pending", idempotency_key=idempotency_key)
    except IntegrityError as exc:  # a concurrent request with the same Idempotency-Key won the race
        raise _err("ORDER_DUPLICATE_IN_FLIGHT",
                   "a duplicate order is in flight; retry to read the result", 409) from exc

    now = datetime.now(timezone.utc)
    if is_alpaca:
        return await _submit_alpaca(session, order, body, adapter, idempotency_key,
                                    tenant_id, user_id, request_id, now)

    adapter = PaperBrokerAdapter(balance, lambda o: mark)
    result = await adapter.submit_order(_to_broker_order(body), idempotency_key or str(order.order_id))
    book = (await adapter.get_orders())[0]

    transition(OrderStatus(order.status), OrderStatus.SUBMITTED)
    await repo.update_order(session, order, status="submitted", broker_order_id=result.broker_order_id, submitted_at=now)
    await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.submitted",
                           target_type="order", target_id=order.order_id, before=None,
                           after={"status": "submitted"}, request_id=request_id)

    if book["status"] == "filled":
        fill_price = book["fill_price"]
        if fill_price is None:  # invariant: a filled order always has a fill price
            raise _err("INTERNAL", "adapter returned filled with no fill price", 500)
        await repo.insert_execution(session, tenant_id=tenant_id, order_id=order.order_id,
                                    broker_account_id=account.broker_account_id, qty=body.qty,
                                    price=fill_price, commission=Decimal(0),
                                    broker_execution_id=f"pe-{order.order_id}")
        signed = body.qty if body.side == "buy" else -body.qty
        current = await repo.get_position(session, account.broker_account_id, body.symbol.upper(),
                                          body.option_type, body.strike, body.expiry)
        new_qty, new_avg = net_position(current.qty if current else 0,
                                        current.avg_entry_price if current else Decimal(0),
                                        signed, fill_price)
        await repo.upsert_position(session, tenant_id=tenant_id, broker_account_id=account.broker_account_id,
                                   symbol=body.symbol.upper(), option_type=body.option_type,
                                   strike=body.strike, expiry=body.expiry, new_qty=new_qty, new_avg=new_avg)
        transition(OrderStatus.SUBMITTED, OrderStatus.FILLED)
        await repo.update_order(session, order, status="filled", filled_at=now)
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.filled",
                               target_type="order", target_id=order.order_id, before={"status": "submitted"},
                               after={"status": "filled", "price": str(fill_price)}, request_id=request_id)
    elif book["status"] == "cancelled":
        transition(OrderStatus.SUBMITTED, OrderStatus.CANCELLED)
        await repo.update_order(session, order, status="cancelled")
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.cancelled",
                               target_type="order", target_id=order.order_id, before={"status": "submitted"},
                               after={"status": "cancelled"}, request_id=request_id)
    # else: rests as "submitted"

    return _out(order)


async def _submit_alpaca(session, order, body, adapter, idempotency_key, tenant_id, user_id,
                         request_id, now) -> dict:
    """Alpaca submit: the order rests 'submitted' (async fills come via reconciliation)."""
    try:
        result = await adapter.submit_order(_to_broker_order(body), idempotency_key or str(order.order_id))
    except BrokerError as exc:
        raise _err("BROKER_UNAVAILABLE", "broker unavailable", 502) from exc

    if result.status == "rejected":
        transition(OrderStatus(order.status), OrderStatus.REJECTED)
        await repo.update_order(session, order, status="rejected", reject_reason_code="BROKER_REJECTED")
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.rejected",
                               target_type="order", target_id=order.order_id, before={"status": "pending"},
                               after={"status": "rejected", "code": "BROKER_REJECTED"}, request_id=request_id)
        raise _err("BROKER_REJECTED", result.rejected_reason or "broker rejected the order")

    transition(OrderStatus(order.status), OrderStatus.SUBMITTED)
    await repo.update_order(session, order, status="submitted",
                            broker_order_id=result.broker_order_id, submitted_at=now)
    await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.submitted",
                           target_type="order", target_id=order.order_id, before={"status": "pending"},
                           after={"status": "submitted"}, request_id=request_id)
    return _out(order)
```

> Note: the paper branch no longer references `account.broker_account_id` after the merge — it still does, via the existing lines. The rewrite above keeps those references; `account` remains in scope.

Then replace `cancel_order` (the function at the end of the file) with:

```python
async def cancel_order(session, principal, order_id, request_id, adapter_factory=None) -> dict:
    order = await repo.get_order(session, UUID(order_id))
    if order is None:
        raise _err("RESOURCE_NOT_FOUND", "order not found", 404)
    if order.status not in ("pending", "submitted"):
        raise _err("ORDER_NOT_CANCELLABLE", f"cannot cancel a {order.status} order", 409)

    account = await repo.get_broker_account(session, order.broker_account_id)
    if (account is not None and account.broker == "alpaca" and order.broker_order_id
            and adapter_factory is not None):
        try:
            await adapter_factory(account).cancel_order(order.broker_order_id)
        except (CredentialError, BrokerError) as exc:  # best-effort; reconciliation confirms terminal state
            _logger.warning("alpaca cancel failed for order %s: %s", order_id, exc)

    transition(OrderStatus(order.status), OrderStatus.CANCELLED)
    await repo.update_order(session, order, status="cancelled")
    await repo.write_audit(session, tenant_id=principal.tenant_id, user_id=principal.user_id,
                           action="order.cancelled", target_type="order", target_id=order.order_id,
                           before={"status": order.status}, after={"status": "cancelled"}, request_id=request_id)
    return _out(order)
```

- [ ] **Step 4: Thread the factory from the router**

In `apps/api/saalr_api/oms/router.py`, replace the `place` and `cancel` handlers:

```python
@router.post("/v1/orders")
async def place(body: OrderCreate, request: Request,
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    factory = getattr(request.app.state, "alpaca_adapter_factory", None)
    return await service.place_order(session, principal, body, idempotency_key,
                                     _request_id(request), factory)


@router.post("/v1/orders/{order_id}/cancel")
async def cancel(order_id: UUID, request: Request,
                 ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    factory = getattr(request.app.state, "alpaca_adapter_factory", None)
    return await service.cancel_order(session, principal, str(order_id), _request_id(request), factory)
```

- [ ] **Step 5: Set the default factory in `main.py`**

In `apps/api/saalr_api/main.py`, add an import:

```python
from saalr_brokers.credentials import EnvCredentialResolver, build_alpaca_adapter
```

Inside `lifespan`, after the `app.state.vol_forecast_ttl = ...` line, add:

```python
        import os
        app.state.alpaca_adapter_factory = lambda account: build_alpaca_adapter(
            account.credential_ref, account.is_paper, EnvCredentialResolver(os.environ)
        )
```

> Alpaca keys (`ALPACA_PAPER_KEY`/`_SECRET`, `ALPACA_LIVE_KEY`/`_SECRET`) are real process env vars, not pydantic-settings `.env` fields — consistent with the OMS-3a live smoke. Tests overwrite `app.state.alpaca_adapter_factory` with a stub after entering the lifespan, so this default never builds a real adapter under test.

- [ ] **Step 6: Run the alpaca tests + the paper regression**

Run: `uv run pytest tests/integration/test_oms_alpaca.py tests/integration/test_oms.py -q`
Expected: PASS (6 alpaca + 7 paper).

- [ ] **Step 7: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/oms apps/api/saalr_api/main.py
git add apps/api/saalr_api/oms/service.py apps/api/saalr_api/oms/router.py apps/api/saalr_api/main.py tests/integration/test_oms_alpaca.py
git commit -m "feat(oms): route place/cancel to Alpaca via injectable adapter factory"
```

---

### Task 5: `reconcile_account` core logic + reconcile queries

The poll-driven reconcile: match local-open orders to Alpaca's reported state, persist fill deltas as synthetic executions (idempotent), recompute positions, advance status, stamp `last_reconciled_at`. Pure logic in core; tested with a real DB session + a stub adapter, seeded through the API from Task 4.

**Files:**
- Create: `packages/core/saalr_core/oms/reconcile.py`
- Test: `tests/integration/test_oms_reconcile.py`

`sum_executed_qty` and `list_open_orders_for_account` already exist from Task 2.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_oms_reconcile.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from saalr_brokers.types import BrokerOrderResult
from saalr_core.db.session import tenant_session
from saalr_core.oms import repo as core_repo
from saalr_core.oms.reconcile import reconcile_account

NOW = datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc)


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class _StubAlpaca:
    """Submits as 'submitted'; get_orders returns whatever rows the test sets."""
    def __init__(self):
        self.rows = []

    async def get_account_balance(self):
        return Decimal("100000")

    async def submit_order(self, order, idempotency_key):
        return BrokerOrderResult("brk-1", "submitted")

    async def get_orders(self, since=None):
        return self.rows


def _row(status, filled_qty, avg, broker_order_id="brk-1"):
    return {"broker_order_id": broker_order_id, "status": status, "symbol": "AAPL",
            "qty": 10, "side": "buy", "filled_qty": filled_qty,
            "filled_avg_price": Decimal(str(avg)) if avg is not None else None,
            "client_order_id": None}


async def _seed_submitted_order(app, h):
    """Create an alpaca account + a resting 'submitted' order via the API; return (account_id, order_id, tenant_id)."""
    stub = _StubAlpaca()
    app.state.alpaca_adapter_factory = lambda account: stub
    async with _client(app) as c:
        acct = (await c.post("/v1/broker-accounts",
                json={"broker": "alpaca", "account_label": "A", "credential_ref": "env:ALPACA_PAPER",
                      "is_paper": True}, headers=h)).json()["broker_account_id"]
        r = await c.post("/v1/orders",
                         json={"broker_account_id": acct, "symbol": "AAPL", "side": "buy",
                               "qty": 10, "order_type": "market"}, headers={**h, "Idempotency-Key": "r1"})
        assert r.json()["status"] == "submitted"
        order_id = r.json()["order_id"]
        tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
    return acct, order_id, tid


async def test_reconcile_fills_and_builds_position(app_sessionmaker, admin_engine):
    from saalr_api.main import create_app
    app = create_app()
    async with app.router.lifespan_context(app):
        h = {"Authorization": "Bearer dev:rec1@x.com"}
        acct, order_id, tid = await _seed_submitted_order(app, h)
        stub = _StubAlpaca()
        stub.rows = [_row("filled", 10, "50.00")]
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, __import__("uuid").UUID(acct))
            summary = await reconcile_account(s, stub, account, now=NOW)
        assert summary["filled"] == 1
        async with _client(app) as c:
            o = (await c.get(f"/v1/orders/{order_id}", headers=h)).json()
            assert o["status"] == "filled"
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert len(pos) == 1 and pos[0]["qty"] == 10 and Decimal(pos[0]["avg_entry_price"]) == Decimal("50")


async def test_reconcile_is_idempotent_on_repoll(app_sessionmaker, admin_engine):
    from saalr_api.main import create_app
    app = create_app()
    async with app.router.lifespan_context(app):
        h = {"Authorization": "Bearer dev:rec2@x.com"}
        acct, order_id, tid = await _seed_submitted_order(app, h)
        stub = _StubAlpaca()
        stub.rows = [_row("filled", 10, "50.00")]
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, __import__("uuid").UUID(acct))
            await reconcile_account(s, stub, account, now=NOW)
        # second pass: order is now terminal/local-closed -> no new executions, position unchanged
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, __import__("uuid").UUID(acct))
            summary2 = await reconcile_account(s, stub, account, now=NOW)
        assert summary2["matched"] == 0  # no open orders left
        async with _client(app) as c:
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert pos[0]["qty"] == 10  # still 10, not 20


async def test_reconcile_partial_then_full(app_sessionmaker, admin_engine):
    from saalr_api.main import create_app
    app = create_app()
    async with app.router.lifespan_context(app):
        h = {"Authorization": "Bearer dev:rec3@x.com"}
        acct, order_id, tid = await _seed_submitted_order(app, h)
        stub = _StubAlpaca()
        stub.rows = [_row("partial", 4, "50.00")]
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, __import__("uuid").UUID(acct))
            s1 = await reconcile_account(s, stub, account, now=NOW)
        assert s1["partial"] == 1
        stub.rows = [_row("filled", 10, "50.00")]
        async with tenant_session(app.state.sessionmaker, tid) as s:
            account = await core_repo.get_broker_account(s, __import__("uuid").UUID(acct))
            s2 = await reconcile_account(s, stub, account, now=NOW)
        assert s2["filled"] == 1
        async with _client(app) as c:
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert pos[0]["qty"] == 10  # 4 + 6
            assert (await c.get(f"/v1/orders/{order_id}", headers=h)).json()["status"] == "filled"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/integration/test_oms_reconcile.py -q`
Expected: FAIL (`ModuleNotFoundError: saalr_core.oms.reconcile`).

- [ ] **Step 3: Implement `reconcile_account`**

Create `packages/core/saalr_core/oms/reconcile.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from saalr_core.oms.fsm import IllegalOrderTransition, OrderStatus, transition
from saalr_core.oms.positions import net_position

from . import repo


async def reconcile_account(session, adapter, account, *, lookback_buffer_seconds: int = 300,
                            now: datetime) -> dict:
    """Poll Alpaca for the account's open orders, persist fill deltas + positions, advance status.

    Drives off LOCAL open orders (status submitted/partial) + a covering lookback window, matched
    by broker_order_id, so Alpaca's after-filters-by-submit-time never hides a late fill. Stamps
    account.last_reconciled_at. Returns a per-status summary for logging/tests.
    """
    summary = {"matched": 0, "filled": 0, "partial": 0, "cancelled": 0, "rejected": 0}

    open_orders = await repo.list_open_orders_for_account(session, account.broker_account_id)
    if not open_orders:
        account.last_reconciled_at = now
        await session.flush()
        return summary

    submitted_times = [o.submitted_at for o in open_orders if o.submitted_at]
    since = (min(submitted_times) - timedelta(seconds=lookback_buffer_seconds)) if submitted_times else None
    rows = await adapter.get_orders(since)
    by_id = {r["broker_order_id"]: r for r in rows}

    for o in open_orders:
        row = by_id.get(o.broker_order_id)
        if row is None:
            continue
        summary["matched"] += 1

        observed = int(row["filled_qty"])
        recorded = await repo.sum_executed_qty(session, o.order_id)
        delta = observed - recorded
        avg = row.get("filled_avg_price")
        if delta > 0 and avg is not None:
            await repo.insert_execution(
                session, tenant_id=o.tenant_id, order_id=o.order_id,
                broker_account_id=o.broker_account_id, qty=delta, price=avg, commission=Decimal(0),
                broker_execution_id=f"recon:{o.order_id}:{observed}",
            )
            signed = delta if o.side == "buy" else -delta
            current = await repo.get_position(session, o.broker_account_id, o.symbol,
                                              o.option_type, o.strike, o.expiry)
            new_qty, new_avg = net_position(
                current.qty if current else 0,
                current.avg_entry_price if current else Decimal(0), signed, avg,
            )
            await repo.upsert_position(
                session, tenant_id=o.tenant_id, broker_account_id=o.broker_account_id,
                symbol=o.symbol, option_type=o.option_type, strike=o.strike, expiry=o.expiry,
                new_qty=new_qty, new_avg=new_avg,
            )

        new_status = row["status"]
        if new_status != o.status:
            try:
                transition(OrderStatus(o.status), OrderStatus(new_status))
            except IllegalOrderTransition:
                continue  # e.g. a status that doesn't advance our FSM; leave as-is
            fields = {"status": new_status}
            if new_status == "filled":
                fields["filled_at"] = now
            before = {"status": o.status}
            await repo.update_order(session, o, **fields)
            await repo.write_audit(
                session, tenant_id=o.tenant_id, user_id=account.user_id,
                action=f"order.{new_status}", target_type="order", target_id=o.order_id,
                before=before, after={"status": new_status},
                request_id=f"recon:{account.broker_account_id}",
            )
            if new_status in summary:
                summary[new_status] += 1

    account.last_reconciled_at = now
    await session.flush()
    return summary
```

> `IllegalOrderTransition` and `OrderStatus`/`transition` are defined in `saalr_core/oms/fsm.py` (OMS-1). If the exception name differs, import the actual one — verify with `grep -n "class .*Transition" packages/core/saalr_core/oms/fsm.py`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/integration/test_oms_reconcile.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/oms
git add packages/core/saalr_core/oms/reconcile.py tests/integration/test_oms_reconcile.py
git commit -m "feat(oms): reconcile_account — poll Alpaca, persist fills/positions, advance status"
```

---

### Task 6: `apps/oms-worker` reconciliation worker

The loop driver: discover active alpaca accounts on the **admin** engine (RLS bypass), then reconcile each inside a `tenant_session`, one transaction per account.

**Files:**
- Create: `apps/oms-worker/pyproject.toml`
- Create: `apps/oms-worker/oms_worker/__init__.py` (empty)
- Create: `apps/oms-worker/oms_worker/reconcile.py`
- Create: `apps/oms-worker/oms_worker/cli.py`
- Create: `apps/oms-worker/oms_worker/__main__.py`
- Create: `apps/oms-worker/tests/test_reconcile_worker.py`
- Create: `apps/oms-worker/tests/test_cli.py`

`list_active_alpaca_accounts` already exists in core repo (Task 2).

- [ ] **Step 1: Scaffold the package + register it in the workspace**

Create `apps/oms-worker/pyproject.toml`:

```toml
[project]
name = "saalr-oms-worker"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "saalr-core",
  "saalr-brokers[alpaca]",
  "sqlalchemy>=2.0",
  "asyncpg>=0.29",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["oms_worker"]

[tool.uv.sources]
saalr-core = { workspace = true }
saalr-brokers = { workspace = true }

[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]
```

Create `apps/oms-worker/oms_worker/__init__.py` (empty file).

Run `uv sync` so the workspace picks up the new member.
Run: `uv sync 2>&1 | tail -2` — Expected: resolves without error (this does NOT install the alpaca extra into the root env; the extra is only materialised when you target the package).

- [ ] **Step 2: Write the failing worker test**

Create `apps/oms-worker/tests/test_reconcile_worker.py`:

```python
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from saalr_api.main import create_app
from saalr_brokers.types import BrokerOrderResult
from oms_worker.reconcile import run_reconcile


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class _StubAlpaca:
    def __init__(self, rows=None):
        self.rows = rows or []

    async def get_account_balance(self):
        return Decimal("100000")

    async def submit_order(self, order, idempotency_key):
        return BrokerOrderResult("brk-w1", "submitted")

    async def get_orders(self, since=None):
        return self.rows


async def test_run_reconcile_once_fills_open_order(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        stub = _StubAlpaca()
        app.state.alpaca_adapter_factory = lambda account: stub
        h = {"Authorization": "Bearer dev:wrk1@x.com"}
        async with _client(app) as c:
            acct = (await c.post("/v1/broker-accounts",
                    json={"broker": "alpaca", "account_label": "A", "credential_ref": "env:ALPACA_PAPER",
                          "is_paper": True}, headers=h)).json()["broker_account_id"]
            r = await c.post("/v1/orders",
                             json={"broker_account_id": acct, "symbol": "AAPL", "side": "buy",
                                   "qty": 10, "order_type": "market"},
                             headers={**h, "Idempotency-Key": "w1"})
            assert r.json()["status"] == "submitted"
            order_id = r.json()["order_id"]

        # the worker fills it
        stub.rows = [{"broker_order_id": "brk-w1", "status": "filled", "symbol": "AAPL", "qty": 10,
                      "side": "buy", "filled_qty": 10, "filled_avg_price": Decimal("50.00"),
                      "client_order_id": None}]
        await run_reconcile(app.state.sessionmaker, admin_engine,
                            adapter_factory=lambda account: stub, once=True,
                            now=datetime(2026, 6, 1, 16, 0, tzinfo=timezone.utc))

        async with _client(app) as c:
            assert (await c.get(f"/v1/orders/{order_id}", headers=h)).json()["status"] == "filled"
```

> The worker test imports `saalr_api` for seeding only; that's fine because the test runs in the root env (where `saalr-api` is installed). The worker *package* itself never imports `saalr-api`.

- [ ] **Step 3: Run to verify it fails**

Run: `uv run --package saalr-oms-worker pytest apps/oms-worker/tests/test_reconcile_worker.py -q`
Expected: FAIL (`ModuleNotFoundError: oms_worker.reconcile`).

- [ ] **Step 4: Implement the loop driver**

Create `apps/oms-worker/oms_worker/reconcile.py`:

```python
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from saalr_brokers.credentials import EnvCredentialResolver, build_alpaca_adapter
from saalr_core.db.session import create_sessionmaker, tenant_session
from saalr_core.oms import repo as core_repo
from saalr_core.oms.reconcile import reconcile_account

_logger = logging.getLogger("saalr.oms.worker")


def _default_adapter_factory(account):
    return build_alpaca_adapter(account.credential_ref, account.is_paper,
                                EnvCredentialResolver(os.environ))


async def reconcile_once(app_sessionmaker, admin_engine, *, adapter_factory, now) -> int:
    """Discover active alpaca accounts (admin engine bypasses RLS), reconcile each in a tenant txn."""
    admin_sm = create_sessionmaker(admin_engine)
    async with admin_sm() as s:
        accounts = await core_repo.list_active_alpaca_accounts(s)

    reconciled = 0
    for acct in accounts:
        try:
            async with tenant_session(app_sessionmaker, acct.tenant_id) as s:
                account = await core_repo.get_broker_account(s, acct.broker_account_id)
                if account is None:
                    continue
                adapter = adapter_factory(account)
                await reconcile_account(s, adapter, account, now=now)
            reconciled += 1
        except Exception:  # crash isolation: one bad account never stops the loop
            _logger.exception("reconcile failed for account %s", acct.broker_account_id)
    return reconciled


async def run_reconcile(app_sessionmaker, admin_engine, *, adapter_factory=None, once: bool = False,
                        interval: float = 5.0, now: datetime | None = None) -> None:
    factory = adapter_factory or _default_adapter_factory
    while True:
        stamp = now or datetime.now(timezone.utc)
        n = await reconcile_once(app_sessionmaker, admin_engine, adapter_factory=factory, now=stamp)
        _logger.info("reconciled %d alpaca account(s)", n)
        if once:
            return
        await asyncio.sleep(interval)
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run --package saalr-oms-worker pytest apps/oms-worker/tests/test_reconcile_worker.py -q`
Expected: PASS (1 passed).

- [ ] **Step 6: Add the CLI + entrypoint + a parser test**

Create `apps/oms-worker/oms_worker/cli.py`:

```python
from __future__ import annotations

import argparse
import asyncio

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="oms_worker", description="Saalr OMS reconciliation worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reconcile", help="poll Alpaca and reconcile open orders")
    r.add_argument("--interval", type=float, default=5.0)
    r.add_argument("--once", action="store_true")
    return p


async def _cmd_reconcile(args) -> None:
    from .reconcile import run_reconcile  # lazy: keeps build_parser import-light

    settings = get_settings()
    app_engine = create_engine(settings.app_database_url)
    admin_engine = create_engine(settings.admin_database_url)
    app_sm = create_sessionmaker(app_engine)
    try:
        await run_reconcile(app_sm, admin_engine, once=args.once, interval=args.interval)
    finally:
        await app_engine.dispose()
        await admin_engine.dispose()


_DISPATCH = {"reconcile": _cmd_reconcile}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
```

Create `apps/oms-worker/oms_worker/__main__.py`:

```python
from .cli import main

if __name__ == "__main__":
    main()
```

Create `apps/oms-worker/tests/test_cli.py`:

```python
import pytest

from oms_worker.cli import build_parser


def test_parser_reconcile_defaults():
    args = build_parser().parse_args(["reconcile"])
    assert args.cmd == "reconcile" and args.once is False and args.interval == 5.0


def test_parser_once_flag():
    args = build_parser().parse_args(["reconcile", "--once"])
    assert args.once is True


def test_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
```

- [ ] **Step 7: Run the worker test suite**

Run: `uv run --package saalr-oms-worker pytest apps/oms-worker/tests -q`
Expected: PASS (1 worker + 3 cli = 4 passed).

- [ ] **Step 8: Confirm the default gate is still alpaca-free**

Run: `uv run python -c "import importlib.util as u; print('alpaca installed' if u.find_spec('alpaca') else 'alpaca absent')"`
Expected: `alpaca absent` (the worker's extra is not in the root env).
Run: `uv run pytest packages/brokers/tests/test_alpaca_adapter.py -q`
Expected: `1 skipped` (importorskip still skips) — proving Task 6 didn't leak alpaca into the default env.

- [ ] **Step 9: Lint + commit**

```bash
uvx ruff check apps/oms-worker
git add apps/oms-worker
git commit -m "feat(oms-worker): reconcile CLI + loop — discover alpaca accounts, reconcile per tenant"
```

> If `uv sync` modified `uv.lock` to register the new member, DO stage `uv.lock` in THIS commit (a real workspace change, unlike the `uv pip install alpaca-py` mutation which must never be committed). Verify the diff is only the new member, then `git add uv.lock`.

---

### Task 7: Runbook + `.env.example`

**Files:**
- Create: `docs/runbooks/oms-reconcile.md`
- Modify: `.env.example` (document the alpaca env vars)

- [ ] **Step 1: Write the runbook**

Create `docs/runbooks/oms-reconcile.md`:

```markdown
# OMS reconciliation worker

Polls Alpaca for open orders on every active `broker='alpaca'` account, persists fills as
executions + positions, advances order status, and stamps `broker_accounts.last_reconciled_at`.

## Credentials
Alpaca keys are **process env vars** (not `.env`/pydantic-settings fields). A broker_account's
`credential_ref` names the env prefix, e.g. `credential_ref = "env:ALPACA_PAPER"` resolves
`ALPACA_PAPER_KEY` + `ALPACA_PAPER_SECRET`. Paper vs live is encoded in the ref by convention
(`ALPACA_PAPER` / `ALPACA_LIVE`) and mirrored by the account's `is_paper`.

## Run
    uv run --package saalr-oms-worker python -m oms_worker reconcile --interval 5      # loop
    uv run --package saalr-oms-worker python -m oms_worker reconcile --once            # one pass (cron/test)

Needs `APP_DATABASE_URL` (per-tenant, RLS) and `ADMIN_DATABASE_URL` (cross-tenant account discovery,
RLS bypass). DB on 55432 locally.

## Notes
- Discovery uses the admin engine (RLS bypass) to enumerate alpaca accounts; each account is then
  reconciled inside a `tenant_session` so all reads/writes are tenant-scoped. A SECURITY DEFINER
  discovery function (to drop the admin dependency) is a later hardening.
- At-least-once safe: synthetic `broker_execution_id = recon:{order_id}:{cumulative_filled}` makes a
  re-poll of the same fill level a no-op.
- Live smoke (opt-in): set `ALPACA_PAPER_KEY`/`ALPACA_PAPER_SECRET`, submit a tiny paper order, run
  `--once`, confirm the order advances.
- Deferred: containerize + schedule (supercronic, like ingest-worker); real trade-update websocket.
```

- [ ] **Step 2: Document the env vars**

Append to `.env.example`:

```
# Alpaca brokerage (OMS-3b). Real process env vars, referenced by broker_accounts.credential_ref="env:ALPACA_PAPER".
ALPACA_PAPER_KEY=
ALPACA_PAPER_SECRET=
ALPACA_LIVE_KEY=
ALPACA_LIVE_SECRET=
```

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/oms-reconcile.md .env.example
git commit -m "docs(oms): reconciliation worker runbook + alpaca env vars in .env.example"
```

---

## Final verification (after all tasks)

- [ ] Default gate: `uv run pytest -q` — all green; alpaca-py NOT installed (the OMS-3a adapter tests still skip).
- [ ] Worker gate: `uv run --package saalr-oms-worker pytest apps/oms-worker/tests -q` — 4 passed.
- [ ] Lint: `uvx ruff check` — clean.
- [ ] Final code-review subagent over the whole diff.

## Self-review notes (deviations from spec, intentional)
- **Account creation added (Task 3):** the spec's file list omitted it, but `broker='alpaca'` accounts
  must be creatable for the slice to be reachable end-to-end; kept minimal (one schema field + endpoint
  branch).
- **`--market` dropped from the CLI:** the spec mentioned `reconcile --market US`, but `broker_accounts`
  has no market column (Alpaca is US-only); a market flag would filter nothing, so it's omitted to avoid a
  misleading no-op.
- **Worker discovery uses the admin engine** (RLS bypass) rather than "like ingest's instrument list"
  (instruments is non-RLS; `broker_accounts` is RLS) — the honest mechanism; a SECURITY DEFINER function
  is noted as later hardening in the runbook.
