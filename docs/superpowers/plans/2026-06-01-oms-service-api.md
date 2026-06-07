# OMS service + API (OMS-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make paper trading work end-to-end through the API: `POST /v1/orders` runs the OMS-1 risk gates, model-prices a mark, fills via the `PaperBrokerAdapter`, and persists the order/execution/position with an audit trail — plus broker-account create, cancel, list, and positions.

**Architecture:** A new `apps/api/saalr_api/oms/` feature (schemas/marks/repo/service/router) orchestrates the OMS-1 core against the existing `orders`/`executions`/`positions`/`broker_accounts`/`audit_log` tables under RLS. A shared pure `net_position` helper unifies the position math. One migration adds a `'paper'` broker value.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async (asyncpg), Alembic (sync psycopg2), the BSM pricing engine, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-06-01-oms-service-api-c2-design.md`

**Conventions / facts (verified):**
- `from __future__ import annotations` everywhere.
- The `broker_accounts.broker` CHECK is named **`broker_accounts_broker_check`** (verified in the live DB). Migrations in `infra/migrations/versions/`; latest is `0004`.
- Models (`saalr_core/db/models/trading.py`): `BrokerAccount`, `Order`, `Execution`, `Position` (all RLS tenant-scoped, in the conftest `TENANT_TABLES`); `AuditLog` (`saalr_core/db/models/audit.py`, also RLS). `Order` cols: order_id, tenant_id, strategy_id, broker_account_id, symbol, option_type, strike(Numeric), expiry(Date), side, qty, order_type, limit_price, stop_price, time_in_force, status, broker_order_id, idempotency_key, reject_reason_code, created_at, submitted_at, filled_at. `Execution` cols: execution_id, tenant_id, order_id, broker_account_id, qty, price, commission, broker_execution_id, executed_at. `Position` cols: position_id, tenant_id, broker_account_id, symbol, option_type, strike, expiry, qty, avg_entry_price, opened_at, last_updated_at.
- OMS-1 pieces: `saalr_brokers.types.BrokerOrder`, `saalr_brokers.paper.PaperBrokerAdapter`, `saalr_core.oms.types.{OrderStatus,OrderRequest,RiskContext,...,RISK_*}`, `saalr_core.oms.fsm.{transition,IllegalOrderTransition}`, `saalr_core.oms.risk.{run_gates,estimate_cost}`.
- Pricing: `saalr_core.pricing.greeks.price(OptionParams(spot, strike, t_years, rate, sigma, div_yield, kind))`, `OptionKind.CALL/PUT`.
- RLS: `get_principal` yields `(session, principal)`; `principal.tenant_id`, `.user_id`. `new_id()` → UUID. asyncpg binds `Decimal` (NUMERIC), `date` (DATE), `datetime` (TIMESTAMPTZ) — never str/float.
- Pagination + repo style: mirror `apps/api/saalr_api/strategies/repo.py` (cursor `(created_at, id)` desc; `session.get`; `flush`). Pro-upgrade + `/me` + tenant_id helper as in `test_strategies.py`.
- Integration env: Postgres 55432, Redis 6379 (export `ADMIN_DATABASE_URL`/`APP_DATABASE_URL` to 55432).

---

## Task 1: Migration `0005` — add the `'paper'` broker value

**Files:**
- Create: `infra/migrations/versions/0005_paper_broker.py`

- [ ] **Step 1: Write the migration**

```python
# infra/migrations/versions/0005_paper_broker.py
"""add 'paper' to the broker_accounts.broker CHECK

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-01
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE broker_accounts DROP CONSTRAINT IF EXISTS broker_accounts_broker_check;
        ALTER TABLE broker_accounts ADD CONSTRAINT broker_accounts_broker_check
          CHECK (broker IN ('paper', 'alpaca', 'ibkr', 'zerodha', 'angelone'));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE broker_accounts DROP CONSTRAINT IF EXISTS broker_accounts_broker_check;
        ALTER TABLE broker_accounts ADD CONSTRAINT broker_accounts_broker_check
          CHECK (broker IN ('alpaca', 'ibkr', 'zerodha', 'angelone'));
    """)
```

- [ ] **Step 2: Apply + verify**

Run (env exported):
```bash
uv run alembic upgrade head
uv run pytest tests/integration/test_migrations.py tests/integration/test_schema_matches_models.py -q
```
Expected: applies cleanly; schema test still green (no model change). Sanity: inserting a `broker='paper'` row no longer violates the CHECK (Task 4's tests prove it). `uvx ruff check infra/migrations/versions/0005_paper_broker.py`.

- [ ] **Step 3: Commit**

```bash
git add infra/migrations/versions/0005_paper_broker.py
git commit -m "feat(oms): migration 0005 — add 'paper' broker value"
```

---

## Task 2: Shared `net_position` + paper-adapter refactor

**Files:**
- Create: `packages/core/saalr_core/oms/positions.py`
- Test: `packages/core/tests/test_oms_positions.py`
- Modify: `packages/brokers/pyproject.toml` (+ `saalr-core` dep + source)
- Modify: `packages/brokers/saalr_brokers/paper.py` (use `net_position`)

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_oms_positions.py
from decimal import Decimal

from saalr_core.oms.positions import net_position


def test_open_and_add_weighted_average():
    assert net_position(0, Decimal(0), 10, Decimal("50")) == (10, Decimal("50"))
    assert net_position(10, Decimal("50"), 10, Decimal("60")) == (20, Decimal("55"))


def test_partial_close_keeps_average():
    assert net_position(10, Decimal("50"), -4, Decimal("60")) == (6, Decimal("50"))


def test_close_to_zero_is_flat():
    assert net_position(10, Decimal("50"), -10, Decimal("60")) == (0, Decimal(0))


def test_flip_through_zero_resets_basis_to_fill():
    assert net_position(5, Decimal("50"), -8, Decimal("60")) == (-3, Decimal("60"))


def test_short_then_add_short():
    assert net_position(-5, Decimal("50"), -5, Decimal("60")) == (-10, Decimal("55"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_oms_positions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.oms.positions'`.

- [ ] **Step 3: Write `net_position`**

```python
# packages/core/saalr_core/oms/positions.py
from __future__ import annotations

from decimal import Decimal


def net_position(
    old_qty: int, old_avg: Decimal, signed_qty: int, price: Decimal
) -> tuple[int, Decimal]:
    """Apply a signed fill (qty>0 buy, qty<0 sell) to a position. Returns (new_qty, new_avg).
    Weighted-average on opening/adding the same direction; average unchanged on a partial close;
    basis reset to the fill price when the position crosses through zero; (0, 0) when flat."""
    new = old_qty + signed_qty
    if new == 0:
        return 0, Decimal(0)
    if old_qty == 0 or (old_qty > 0) == (signed_qty > 0):
        total = old_avg * abs(old_qty) + price * abs(signed_qty)
        return new, total / abs(new)
    if (old_qty > 0) != (new > 0):  # crossed through zero
        return new, price
    return new, old_avg  # partial close, same direction
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_oms_positions.py -v`
Expected: PASS (5).

- [ ] **Step 5: Add the saalr-core dep to saalr-brokers + refactor the adapter**

In `packages/brokers/pyproject.toml`: set `dependencies = ["saalr-core"]` and add
`[tool.uv.sources] saalr-core = { workspace = true }`. Run `uv sync`.

In `packages/brokers/saalr_brokers/paper.py`, replace the body of `_add_position` to delegate to the
shared helper (import `from saalr_core.oms.positions import net_position` at the top):

```python
    def _add_position(self, order: BrokerOrder, signed_qty: int, price: Decimal) -> None:
        key = self._key(order)
        pos = self._positions.get(key, {"qty": 0, "avg_price": Decimal(0), "order": order})
        new_qty, new_avg = net_position(pos["qty"], pos["avg_price"], signed_qty, price)
        pos["qty"], pos["avg_price"] = new_qty, new_avg
        if new_qty == 0:
            self._positions.pop(key, None)
        else:
            self._positions[key] = pos
```

- [ ] **Step 6: Verify the adapter is behaviour-neutral**

Run: `uv run pytest packages/brokers/tests -q` → expect all 12 still pass (incl. the flip-through-zero test). `uvx ruff check packages/core/saalr_core/oms/positions.py packages/brokers/saalr_brokers/paper.py`.

- [ ] **Step 7: Commit**

```bash
git add packages/core/saalr_core/oms/positions.py packages/core/tests/test_oms_positions.py packages/brokers/pyproject.toml packages/brokers/saalr_brokers/paper.py uv.lock
git commit -m "refactor(oms): shared net_position helper (used by paper adapter + OMS service)"
```

---

## Task 3: Data layer — schemas, model-mark provider, repo

**Files:**
- Modify: `packages/core/saalr_core/config.py` (+ `paper_starting_cash`)
- Create: `apps/api/saalr_api/oms/__init__.py` (empty)
- Create: `apps/api/saalr_api/oms/schemas.py`
- Create: `apps/api/saalr_api/oms/marks.py`
- Create: `apps/api/saalr_api/oms/repo.py`
- Test: `tests/integration/test_oms_marks.py`

- [ ] **Step 1: Add the setting**

In `packages/core/saalr_core/config.py`, add to `Settings`: `paper_starting_cash: float = 100000.0`.

- [ ] **Step 2: Write the failing mark test**

```python
# tests/integration/test_oms_marks.py
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from saalr_api.oms.marks import NoMarketData, model_mark


async def _seed_bars(admin_engine, symbol, closes, start=datetime(2025, 1, 1, tzinfo=timezone.utc)):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol=:s"), {"s": symbol})
        for i, c in enumerate(closes):
            ts = start + timedelta(days=i)
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:s,'US','1d',:c,:c,:c,:c,1000)"""),
                {"ts": ts, "s": symbol, "c": Decimal(str(c))},
            )


async def test_equity_mark_is_latest_close(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", [100, 101, 102.5])
    async with app_sessionmaker() as s:
        m = await model_mark(s, symbol="AAPL", market="US", option_type=None,
                             strike=None, expiry=None, today=date(2025, 6, 1))
    assert m == Decimal("102.5")


async def test_option_mark_is_positive_bsm(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", [100 + (i % 3) for i in range(40)])
    async with app_sessionmaker() as s:
        m = await model_mark(s, symbol="AAPL", market="US", option_type="CALL",
                             strike=Decimal("100"), expiry=date(2025, 4, 1), today=date(2025, 3, 1))
    assert m > Decimal("0")


async def test_no_bars_raises(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol='ZZZZ'"))
    async with app_sessionmaker() as s:
        with pytest.raises(NoMarketData):
            await model_mark(s, symbol="ZZZZ", market="US", option_type=None,
                             strike=None, expiry=None, today=date(2025, 6, 1))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_oms_marks.py -v` → FAIL (ModuleNotFoundError on `saalr_api.oms.marks`).

- [ ] **Step 4: Write schemas, marks, repo**

```python
# apps/api/saalr_api/oms/schemas.py
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class BrokerAccountCreate(BaseModel):
    broker: str = "paper"
    account_label: str = Field(min_length=1)
    is_paper: bool = True


class OrderCreate(BaseModel):
    broker_account_id: str
    symbol: str = Field(min_length=1)
    side: str
    qty: int
    order_type: str
    strategy_id: str | None = None
    option_type: str | None = None
    strike: Decimal | None = None
    expiry: date | None = None
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "day"
```

```python
# apps/api/saalr_api/oms/marks.py
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.pricing.greeks import price as bsm_price
from saalr_core.pricing.types import OptionKind, OptionParams

_RATE = 0.04
_VOL_FLOOR = 0.05
_TRADING_DAYS = 252


class NoMarketData(Exception):
    """No stored bar to price the order against."""


async def _closes(session: AsyncSession, symbol: str, market: str, limit: int = 40) -> list[float]:
    rows = (
        await session.execute(
            text("""SELECT close FROM bars
                    WHERE symbol=:s AND market=:m AND interval='1d'
                    ORDER BY ts DESC LIMIT :n"""),
            {"s": symbol, "m": market, "n": limit},
        )
    ).all()
    return [float(r.close) for r in reversed(rows)]  # oldest -> newest


def _realized_vol(closes: list[float]) -> float:
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a > 0 and b > 0]
    window = rets[-21:]
    if len(window) < 2:
        return _VOL_FLOOR
    mu = sum(window) / len(window)
    var = sum((r - mu) ** 2 for r in window) / (len(window) - 1)
    return max(math.sqrt(var) * math.sqrt(_TRADING_DAYS), _VOL_FLOOR)


async def model_mark(
    session: AsyncSession, *, symbol: str, market: str, option_type: str | None,
    strike: Decimal | None, expiry: date | None, today: date,
) -> Decimal:
    closes = await _closes(session, symbol, market)
    if not closes:
        raise NoMarketData(f"no bars for {symbol}")
    spot = closes[-1]
    if option_type is None:
        return Decimal(str(spot))
    if expiry is None:
        raise NoMarketData("option order missing expiry")
    t = (expiry - today).days / 365.0
    if t <= 0:
        raise NoMarketData("option expiry not in the future")
    sigma = _realized_vol(closes)
    kind = OptionKind.CALL if option_type.upper() in ("CALL", "CE") else OptionKind.PUT
    px = bsm_price(OptionParams(spot=spot, strike=float(strike), t_years=t, rate=_RATE,
                                sigma=sigma, div_yield=0.0, kind=kind))
    return Decimal(str(round(px, 4)))
```

```python
# apps/api/saalr_api/oms/repo.py
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.audit import AuditLog
from saalr_core.db.models.trading import BrokerAccount, Execution, Order, Position
from saalr_core.ids import new_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- broker accounts ---
async def create_broker_account(session, tenant_id, user_id, broker, label, is_paper) -> BrokerAccount:
    row = BrokerAccount(
        broker_account_id=new_id(), tenant_id=tenant_id, user_id=user_id, broker=broker,
        account_label=label, credential_ref="paper:local", is_paper=is_paper, status="active",
    )
    session.add(row)
    await session.flush()
    return row


async def get_broker_account(session, broker_account_id) -> BrokerAccount | None:
    return await session.get(BrokerAccount, broker_account_id)


async def list_broker_accounts(session) -> list[BrokerAccount]:
    return list((await session.execute(select(BrokerAccount).order_by(BrokerAccount.created_at.desc()))).scalars().all())


# --- orders ---
async def find_order_by_idempotency(session, tenant_id, key) -> Order | None:
    if not key:
        return None
    return (
        await session.execute(
            select(Order).where(Order.tenant_id == tenant_id, Order.idempotency_key == key)
        )
    ).scalar_one_or_none()


async def insert_order(session, *, tenant_id, user_id, body, status, reject_reason_code=None,
                       idempotency_key=None) -> Order:
    row = Order(
        order_id=new_id(), tenant_id=tenant_id,
        strategy_id=UUID(body.strategy_id) if body.strategy_id else None,
        broker_account_id=UUID(body.broker_account_id), symbol=body.symbol.upper(),
        option_type=body.option_type, strike=body.strike, expiry=body.expiry,
        side=body.side, qty=body.qty, order_type=body.order_type,
        limit_price=body.limit_price, stop_price=body.stop_price, time_in_force=body.time_in_force,
        status=status, reject_reason_code=reject_reason_code, idempotency_key=idempotency_key,
    )
    session.add(row)
    await session.flush()
    return row


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


async def account_balance(session, broker_account_id, starting_cash: Decimal) -> Decimal:
    total = (
        await session.execute(
            text("""
                SELECT COALESCE(SUM(
                    (CASE WHEN o.side='buy' THEN -1 ELSE 1 END)
                    * e.price * e.qty * (CASE WHEN o.option_type IS NOT NULL THEN 100 ELSE 1 END)
                    - e.commission
                ), 0)
                FROM executions e JOIN orders o ON o.order_id = e.order_id
                WHERE e.broker_account_id = :acct
            """),
            {"acct": str(broker_account_id)},
        )
    ).scalar_one()
    return starting_cash + Decimal(str(total))


# --- positions ---
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


async def list_positions(session, broker_account_id=None) -> list[Position]:
    stmt = select(Position).order_by(Position.last_updated_at.desc())
    if broker_account_id is not None:
        stmt = stmt.where(Position.broker_account_id == broker_account_id)
    return list((await session.execute(stmt)).scalars().all())


async def get_order(session, order_id) -> Order | None:
    return await session.get(Order, order_id)


async def list_orders(session, limit, cursor) -> list[Order]:
    stmt = select(Order).order_by(Order.created_at.desc(), Order.order_id.desc())
    if cursor is not None:
        created_at, oid = cursor
        stmt = stmt.where(
            (Order.created_at < created_at) | ((Order.created_at == created_at) & (Order.order_id < oid))
        )
    return list((await session.execute(stmt.limit(limit))).scalars().all())


# --- audit ---
async def write_audit(session, *, tenant_id, user_id, action, target_type, target_id,
                      before, after, request_id) -> None:
    session.add(AuditLog(
        audit_id=new_id(), tenant_id=tenant_id, user_id=user_id, action=action,
        target_type=target_type, target_id=target_id, before_state=before, after_state=after,
        request_id=request_id,
    ))
    await session.flush()
```

- [ ] **Step 5: Run the mark test**

Run: `uv run pytest tests/integration/test_oms_marks.py -v` → expect 3 passed.

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/config.py apps/api/saalr_api/oms tests/integration/test_oms_marks.py
git add packages/core/saalr_core/config.py apps/api/saalr_api/oms/__init__.py apps/api/saalr_api/oms/schemas.py apps/api/saalr_api/oms/marks.py apps/api/saalr_api/oms/repo.py tests/integration/test_oms_marks.py
git commit -m "feat(oms): schemas + model-mark provider + DB repo"
```

---

## Task 4: Service + router + the end-to-end suite

**Files:**
- Create: `apps/api/saalr_api/oms/service.py`
- Create: `apps/api/saalr_api/oms/router.py`
- Modify: `apps/api/saalr_api/main.py` (register the router)
- Test: `tests/integration/test_oms.py`

- [ ] **Step 1: Write the failing end-to-end test**

```python
# tests/integration/test_oms.py
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, n=40, px=100.0):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol=:s"), {"s": symbol})
        for i in range(n):
            ts = start + timedelta(days=i)
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:s,'US','1d',:c,:c,:c,:c,1000)"""),
                {"ts": ts, "s": symbol, "c": Decimal(str(px))},
            )


async def _account(c, h):
    r = await c.post("/v1/broker-accounts", json={"account_label": "Paper"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["broker_account_id"]


def _order(acct, **kw):
    base = {"broker_account_id": acct, "symbol": "AAPL", "side": "buy", "qty": 10, "order_type": "market"}
    base.update(kw)
    return base


async def test_market_buy_fills_and_persists(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms1@x.com"}
            acct = await _account(c, h)
            r = await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "k1"})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "filled" and body["broker_order_id"]
            # a position appears
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert len(pos) == 1 and pos[0]["qty"] == 10 and Decimal(pos[0]["avg_entry_price"]) == Decimal("50")


async def test_idempotent_order(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms2@x.com"}
            acct = await _account(c, h)
            hk = {**h, "Idempotency-Key": "dup"}
            r1 = await c.post("/v1/orders", json=_order(acct), headers=hk)
            r2 = await c.post("/v1/orders", json=_order(acct), headers=hk)
            assert r1.json()["order_id"] == r2.json()["order_id"]
            pos = (await c.get("/v1/positions", headers=h)).json()["positions"]
            assert pos[0]["qty"] == 10  # not 20 — one fill


async def test_insufficient_buying_power_rejected(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms3@x.com"}
            acct = await _account(c, h)
            r = await c.post("/v1/orders", json=_order(acct, qty=100000),
                             headers={**h, "Idempotency-Key": "k"})
            assert r.status_code == 422
            assert r.json()["error"]["code"] == "RISK_INSUFFICIENT_BUYING_POWER"


async def test_no_market_data_rejected(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms4@x.com"}
            acct = await _account(c, h)
            async with admin_engine.begin() as conn:
                await conn.execute(text("DELETE FROM bars WHERE symbol='ZZZZ'"))
            r = await c.post("/v1/orders", json=_order(acct, symbol="ZZZZ"),
                             headers={**h, "Idempotency-Key": "k"})
            assert r.status_code == 422 and r.json()["error"]["code"] == "RISK_NO_MARKET_DATA"


async def test_non_marketable_limit_rests_and_cancels(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms5@x.com"}
            acct = await _account(c, h)
            r = await c.post("/v1/orders",
                             json=_order(acct, order_type="limit", limit_price="48"),
                             headers={**h, "Idempotency-Key": "k"})
            assert r.json()["status"] == "submitted"  # 50 > 48 buy limit -> rests
            oid = r.json()["order_id"]
            assert (await c.get("/v1/positions", headers=h)).json()["positions"] == []
            cancel = await c.post(f"/v1/orders/{oid}/cancel", headers=h)
            assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled"
            # cancelling again -> 409
            assert (await c.post(f"/v1/orders/{oid}/cancel", headers=h)).status_code == 409


async def test_rls_isolation(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            ha = {"Authorization": "Bearer dev:oms-a@x.com"}
            hb = {"Authorization": "Bearer dev:oms-b@x.com"}
            acct = await _account(c, ha)
            r = await c.post("/v1/orders", json=_order(acct), headers={**ha, "Idempotency-Key": "k"})
            oid = r.json()["order_id"]
            assert (await c.get(f"/v1/orders/{oid}", headers=hb)).status_code == 404
            assert (await c.get("/v1/positions", headers=hb)).json()["positions"] == []


async def test_audit_row_written(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oms6@x.com"}
            acct = await _account(c, h)
            await c.post("/v1/orders", json=_order(acct), headers={**h, "Idempotency-Key": "k"})
    async with admin_engine.begin() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM audit_log WHERE action='order.filled'"))).scalar_one()
    assert n >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_oms.py -v` → FAIL (404 / ModuleNotFoundError on `saalr_api.oms.service`).

- [ ] **Step 3: Write the service**

```python
# apps/api/saalr_api/oms/service.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_brokers.paper import PaperBrokerAdapter
from saalr_brokers.types import BrokerOrder
from saalr_core.config import get_settings
from saalr_core.oms.fsm import OrderStatus, transition
from saalr_core.oms.positions import net_position
from saalr_core.oms.risk import estimate_cost, run_gates
from saalr_core.oms.types import OrderRequest, RiskContext

from ..strategies import repo as strat_repo
from . import repo
from .marks import NoMarketData, model_mark
from .schemas import OrderCreate

_MULT = 100


def _err(code: str, msg: str, status: int = 422, details: dict | None = None) -> HTTPException:
    body = {"error": {"code": code, "message": msg}}
    if details:
        body["error"]["details"] = details
    return HTTPException(status, body)


def _to_request(body: OrderCreate) -> OrderRequest:
    return OrderRequest(
        side=body.side, qty=body.qty, order_type=body.order_type, symbol=body.symbol.upper(),
        limit_price=body.limit_price, stop_price=body.stop_price, time_in_force=body.time_in_force,
        option_type=body.option_type, strike=body.strike, expiry=body.expiry,
    )


def _to_broker_order(body: OrderCreate) -> BrokerOrder:
    return BrokerOrder(
        symbol=body.symbol.upper(), side=body.side, qty=body.qty, order_type=body.order_type,
        limit_price=body.limit_price, stop_price=body.stop_price, time_in_force=body.time_in_force,
        option_type=body.option_type, strike=body.strike, expiry=body.expiry,
    )


def _out(order) -> dict:
    return {
        "order_id": str(order.order_id), "broker_order_id": order.broker_order_id,
        "status": order.status,
        "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
    }


async def place_order(session: AsyncSession, principal, body: OrderCreate, idempotency_key, request_id) -> dict:
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

    today = datetime.now(timezone.utc).date()
    try:
        mark = await model_mark(session, symbol=body.symbol.upper(), market="US",
                                option_type=body.option_type, strike=body.strike,
                                expiry=body.expiry, today=today)
    except NoMarketData as exc:
        order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                        status="rejected", reject_reason_code="RISK_NO_MARKET_DATA",
                                        idempotency_key=idempotency_key)
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.rejected",
                               target_type="order", target_id=order.order_id, before=None,
                               after={"status": "rejected", "code": "RISK_NO_MARKET_DATA"},
                               request_id=request_id)
        raise _err("RISK_NO_MARKET_DATA", str(exc)) from exc

    req = _to_request(body)
    est_cost = estimate_cost(req, mark)
    balance = await repo.account_balance(session, account.broker_account_id, Decimal(str(settings.paper_starting_cash)))
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

    order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                    status="pending", idempotency_key=idempotency_key)

    if account.broker != "paper":
        raise _err("BROKER_NOT_SUPPORTED", f"broker {account.broker} not yet supported", 400)
    adapter = PaperBrokerAdapter(balance, lambda o: mark)
    result = await adapter.submit_order(_to_broker_order(body), idempotency_key or str(order.order_id))
    book = (await adapter.get_orders())[0]
    now = datetime.now(timezone.utc)

    transition(OrderStatus(order.status), OrderStatus.SUBMITTED)
    await repo.update_order(session, order, status="submitted", broker_order_id=result.broker_order_id, submitted_at=now)
    await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.submitted",
                           target_type="order", target_id=order.order_id, before=None,
                           after={"status": "submitted"}, request_id=request_id)

    if book["status"] == "filled":
        fill_price = book["fill_price"]
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


async def cancel_order(session, principal, order_id, request_id) -> dict:
    order = await repo.get_order(session, UUID(order_id))
    if order is None:
        raise _err("RESOURCE_NOT_FOUND", "order not found", 404)
    if order.status not in ("pending", "submitted"):
        raise _err("ORDER_NOT_CANCELLABLE", f"cannot cancel a {order.status} order", 409)
    transition(OrderStatus(order.status), OrderStatus.CANCELLED)
    await repo.update_order(session, order, status="cancelled")
    await repo.write_audit(session, tenant_id=principal.tenant_id, user_id=principal.user_id,
                           action="order.cancelled", target_type="order", target_id=order.order_id,
                           before={"status": order.status}, after={"status": "cancelled"}, request_id=request_id)
    return _out(order)
```

> Note: `place_order` runs inside the `get_principal` RLS transaction (committed when the handler returns). The `transition(...)` calls assert FSM legality (they raise on a bug, not on normal flow). The fresh `PaperBrokerAdapter` is seeded with the DB-derived `balance` + the precomputed `mark`; the DB is the source of truth for positions/cash.

- [ ] **Step 4: Write the router + register**

```python
# apps/api/saalr_api/oms/router.py
from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.ids import new_id

from ..auth import Principal, get_principal
from . import repo, service
from .schemas import BrokerAccountCreate, OrderCreate

router = APIRouter(tags=["oms"])


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or str(new_id())


def _acct_out(a) -> dict:
    return {"broker_account_id": str(a.broker_account_id), "broker": a.broker,
            "account_label": a.account_label, "is_paper": a.is_paper, "status": a.status}


def _pos_out(p) -> dict:
    return {"broker_account_id": str(p.broker_account_id), "symbol": p.symbol,
            "option_type": p.option_type, "strike": str(p.strike) if p.strike is not None else None,
            "expiry": p.expiry.isoformat() if p.expiry else None, "qty": p.qty,
            "avg_entry_price": str(p.avg_entry_price)}


def _order_out(o) -> dict:
    return {"order_id": str(o.order_id), "symbol": o.symbol, "side": o.side, "qty": o.qty,
            "order_type": o.order_type, "status": o.status, "broker_order_id": o.broker_order_id,
            "reject_reason_code": o.reject_reason_code, "created_at": o.created_at.isoformat()}


@router.post("/v1/broker-accounts")
async def create_account(body: BrokerAccountCreate,
                         ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    if body.broker != "paper":
        raise HTTPException(400, {"error": {"code": "BROKER_NOT_SUPPORTED", "message": "only paper accounts are supported"}})
    a = await repo.create_broker_account(session, principal.tenant_id, principal.user_id,
                                         "paper", body.account_label, True)
    return _acct_out(a)


@router.get("/v1/broker-accounts")
async def list_accounts(ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    return {"broker_accounts": [_acct_out(a) for a in await repo.list_broker_accounts(session)]}


@router.post("/v1/orders")
async def place(body: OrderCreate, request: Request,
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    return await service.place_order(session, principal, body, idempotency_key, _request_id(request))


@router.get("/v1/orders")
async def list_orders(limit: int = Query(20, le=100), cursor: str | None = None,
                      ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    decoded = None
    if cursor:
        try:
            ts, oid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            decoded = (datetime.fromisoformat(ts), UUID(oid))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": "bad cursor"}}) from exc
    rows = await repo.list_orders(session, limit, decoded)
    nxt = None
    if len(rows) == limit:
        last = rows[-1]
        nxt = base64.urlsafe_b64encode(f"{last.created_at.isoformat()}|{last.order_id}".encode()).decode()
    return {"orders": [_order_out(r) for r in rows], "next_cursor": nxt}


@router.get("/v1/orders/{order_id}")
async def get_one(order_id: UUID, ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    o = await repo.get_order(session, order_id)
    if o is None:
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "order not found"}})
    return _order_out(o)


@router.post("/v1/orders/{order_id}/cancel")
async def cancel(order_id: UUID, request: Request,
                 ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    return await service.cancel_order(session, principal, str(order_id), _request_id(request))


@router.get("/v1/positions")
async def list_positions(broker_account_id: UUID | None = Query(None),
                         ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    return {"positions": [_pos_out(p) for p in await repo.list_positions(session, broker_account_id)]}
```

In `apps/api/saalr_api/main.py`: `from .oms.router import router as oms_router` + `app.include_router(oms_router)`.

- [ ] **Step 5: Run the suite**

Run: `uv run pytest tests/integration/test_oms.py -v`
Expected: PASS (7). If the RLS test sees a cross-tenant 200 instead of 404, confirm `get_order`/`list_positions` run on the RLS session (they do — `get_principal` sets `app.current_tenant`, and these tables are FORCE-RLS).

- [ ] **Step 6: Lint + commit**

```bash
uvx ruff check apps/api/saalr_api/oms apps/api/saalr_api/main.py tests/integration/test_oms.py
git add apps/api/saalr_api/oms/service.py apps/api/saalr_api/oms/router.py apps/api/saalr_api/main.py tests/integration/test_oms.py
git commit -m "feat(oms): place_order service + endpoints (paper trading end-to-end)"
```

---

## Task 5: Full gate

**Files:** none (verification only). 55432 + Redis up.

- [ ] **Step 1: Pure suites**

Run: `uv run pytest packages/core/tests packages/brokers/tests -q` → green (incl. net_position + the refactored paper adapter).

- [ ] **Step 2: OMS + regression integration**

Run: `uv run pytest tests/integration/test_oms.py tests/integration/test_oms_marks.py tests/integration/test_strategies.py tests/integration/test_schema_matches_models.py -q` → green.

- [ ] **Step 3: Lint**

Run: `uvx ruff check apps/api/saalr_api/oms packages/core/saalr_core/oms packages/brokers/saalr_brokers` → clean.

- [ ] **Step 4: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "chore(oms): OMS-2 — suite + lint green"
```

---

## Self-review notes (addressed)

- **Spec coverage:** migration (T1), shared net_position + adapter refactor (T2), schemas/marks/repo (T3), place_order service + router + the end-to-end suite incl. idempotency/reject/RLS/audit/cancel (T4), gate (T5).
- **Account-mode-agnostic:** `place_order` routes by `account.broker`; only `"paper"` is wired (else 400). The buying-power gate uses the DB-derived balance; the DB is the source of truth for positions/cash (the fresh per-request adapter only decides the fill).
- **Honesty:** no bar → `RISK_NO_MARKET_DATA` (persisted rejected + audited), never a fabricated fill. Marks are model-priced (equity last close / option BSM) consistent with the backtest/forecast ethos.
- **Type/units consistency:** `Decimal` for prices/strike, `date` for expiry; option multiplier 100 in `estimate_cost`, `account_balance`, and (via the adapter) the fill — net_position handles averaging + flip. FSM transitions asserted (`pending→submitted→filled`/`cancelled`). Idempotency via the `orders(tenant_id, idempotency_key)` unique index + a pre-check.
- **net_position home:** `saalr_core/oms` (with the FSM + gates); `saalr-brokers` gains a one-way `saalr-core` dep (T2) — no cycle.
- **request_id:** generated per request (clean `new_id()` — the implementer removes the inline `__import__` shim).
