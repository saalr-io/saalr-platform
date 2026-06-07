# OMS order core (OMS-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the account-mode-agnostic order core — a `saalr-brokers` package (BrokerAdapter ABC + dataclasses + a deterministic mark-price `PaperBrokerAdapter`) and pure `saalr_core/oms` (order-status FSM + core pre-trade risk gates).

**Architecture:** Two standalone homes. `saalr-brokers` (new package, no SDK yet, root dependency) holds the broker layer; `saalr_core/oms` holds the pure FSM + gates. No DB/API (that's OMS-2). All tests are fast + deterministic.

**Tech Stack:** Python 3.12 (stdlib + `decimal`), pytest (`pytest-asyncio`), ruff, uv workspace.

**Spec:** `docs/superpowers/specs/2026-06-01-oms-order-core-design.md`

**Conventions / facts (verified):**
- `from __future__ import annotations` at the top of every module.
- `packages/brokers` exists as a stub (`saalr-brokers`, deps `[]`, no wheel target). It is NOT yet a root dependency. Root `pyproject.toml` deps = `["saalr-core","saalr-api","saalr-ml"]` + matching `[tool.uv.sources]`.
- `orders`/`executions`/`positions`/`broker_accounts` tables + models already exist (slice 1); OMS-1 adds NO tables/models. Order CHECK values: status ∈ `pending/submitted/partial/filled/cancelled/rejected`; side ∈ `buy/sell`; order_type ∈ `market/limit/stop/stop_limit`; tif ∈ `day/gtc/ioc/fok`.
- FSM pattern to mirror: `saalr_core/strategies/state.py` (`VALID_TRANSITIONS` dict + `transition()` raising a custom exception).
- `OPTION_MULTIPLIER = 100` (the option contract multiplier used elsewhere).
- Prices are `Decimal`. pytest-asyncio is in `auto` mode (async tests need no decorator).

---

## Task 1: `saalr-brokers` package — types + ABC + root wiring

**Files:**
- Modify: `packages/brokers/pyproject.toml` (wheel target)
- Modify: `pyproject.toml` (root: add `saalr-brokers` dep + source)
- Create: `packages/brokers/saalr_brokers/__init__.py` (empty)
- Create: `packages/brokers/saalr_brokers/types.py`
- Create: `packages/brokers/saalr_brokers/base.py`
- Test: `packages/brokers/tests/test_broker_types.py`

- [ ] **Step 1: Wire the package**

In `packages/brokers/pyproject.toml`, add (keep `dependencies = []`):
```toml
[tool.hatch.build.targets.wheel]
packages = ["saalr_brokers"]
```
In the root `pyproject.toml`: add `"saalr-brokers"` to `[project].dependencies` and `saalr-brokers = { workspace = true }` to `[tool.uv.sources]`. Then `uv sync`.

- [ ] **Step 2: Write the failing test**

```python
# packages/brokers/tests/test_broker_types.py
from decimal import Decimal

import pytest

from saalr_brokers.base import BrokerAdapter
from saalr_brokers.types import BrokerFill, BrokerOrder, BrokerOrderResult, BrokerPosition


def test_dataclasses_construct():
    o = BrokerOrder(symbol="AAPL", side="buy", qty=1, order_type="market")
    assert o.time_in_force == "day" and o.limit_price is None
    r = BrokerOrderResult(broker_order_id="x", status="submitted")
    assert r.rejected_reason is None
    f = BrokerFill(broker_order_id="x", broker_execution_id="e", qty=1, price=Decimal("1.5"))
    assert f.commission == Decimal(0)
    p = BrokerPosition("AAPL", 1, Decimal("1"), Decimal("1"), Decimal("0"))
    assert p.qty == 1


def test_broker_adapter_is_abstract():
    with pytest.raises(TypeError):
        BrokerAdapter()  # cannot instantiate an ABC with abstract methods
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest packages/brokers/tests/test_broker_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_brokers'` (run `uv sync` if the member isn't installed).

- [ ] **Step 4: Write types + base**

```python
# packages/brokers/saalr_brokers/types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class BrokerOrder:
    symbol: str
    side: str               # "buy" | "sell"
    qty: int
    order_type: str         # "market" | "limit" | "stop" | "stop_limit"
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "day"   # "day" | "gtc" | "ioc" | "fok"
    option_type: str | None = None
    strike: Decimal | None = None
    expiry: date | None = None


@dataclass(frozen=True)
class BrokerOrderResult:
    broker_order_id: str
    status: str             # "submitted" | "rejected"
    rejected_reason: str | None = None


@dataclass(frozen=True)
class BrokerFill:
    broker_order_id: str
    broker_execution_id: str
    qty: int
    price: Decimal
    commission: Decimal = Decimal(0)


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    qty: int
    avg_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
```

```python
# packages/brokers/saalr_brokers/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal

from .types import BrokerFill, BrokerOrder, BrokerOrderResult, BrokerPosition


class BrokerAdapter(ABC):
    """The contract every broker adapter implements (LLD §6). Paper and live alike."""

    @abstractmethod
    async def submit_order(self, order: BrokerOrder, idempotency_key: str) -> BrokerOrderResult: ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool: ...

    @abstractmethod
    async def get_orders(self, since: datetime | None = None) -> list[dict]: ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    async def get_account_balance(self) -> Decimal: ...

    @abstractmethod
    def stream_executions(self) -> AsyncIterator[BrokerFill]: ...
```

- [ ] **Step 5: Run test + lint**

Run: `uv run pytest packages/brokers/tests/test_broker_types.py -v` → PASS (2).
Then `uvx ruff check packages/brokers/saalr_brokers packages/brokers/tests`.

- [ ] **Step 6: Commit**

```bash
git add packages/brokers/pyproject.toml pyproject.toml uv.lock packages/brokers/saalr_brokers/__init__.py packages/brokers/saalr_brokers/types.py packages/brokers/saalr_brokers/base.py packages/brokers/tests/test_broker_types.py
git commit -m "feat(brokers): saalr-brokers package — BrokerAdapter ABC + dataclasses"
```

---

## Task 2: `PaperBrokerAdapter`

**Files:**
- Create: `packages/brokers/saalr_brokers/paper.py`
- Test: `packages/brokers/tests/test_paper_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/brokers/tests/test_paper_adapter.py
from decimal import Decimal

from saalr_brokers.paper import PaperBrokerAdapter
from saalr_brokers.types import BrokerOrder


def _mark(price):
    return lambda order: Decimal(str(price))


def _eq(symbol="AAPL", side="buy", qty=10, order_type="market", **kw):
    return BrokerOrder(symbol=symbol, side=side, qty=qty, order_type=order_type, **kw)


async def test_market_buy_fills_at_mark_and_moves_cash_and_position():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    res = await a.submit_order(_eq(qty=10), "k1")
    assert res.status == "submitted"
    assert await a.get_account_balance() == Decimal("100000") - Decimal("50") * 10  # equity mult 1
    pos = await a.get_positions()
    assert len(pos) == 1 and pos[0].qty == 10 and pos[0].avg_price == Decimal("50")
    orders = await a.get_orders()
    assert orders[0]["status"] == "filled" and orders[0]["fill_price"] == Decimal("50")


async def test_option_fill_uses_100_multiplier():
    a = PaperBrokerAdapter(Decimal("100000"), _mark("2.50"))
    await a.submit_order(_eq(symbol="AAPL", qty=1, option_type="CALL", strike=Decimal("100")), "k1")
    assert await a.get_account_balance() == Decimal("100000") - Decimal("2.50") * 1 * 100


async def test_marketable_limit_fills_at_limit_not_mark():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    await a.submit_order(_eq(order_type="limit", side="buy", limit_price=Decimal("52")), "k1")  # mark 50 <= 52
    orders = await a.get_orders()
    assert orders[0]["status"] == "filled" and orders[0]["fill_price"] == Decimal("52")


async def test_non_marketable_limit_day_rests_open():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    res = await a.submit_order(_eq(order_type="limit", side="buy", limit_price=Decimal("48")), "k1")  # 50 > 48
    assert res.status == "submitted"
    orders = await a.get_orders()
    assert orders[0]["status"] == "open"
    assert await a.get_positions() == []


async def test_non_marketable_ioc_is_cancelled():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    await a.submit_order(_eq(order_type="limit", side="buy", limit_price=Decimal("48"), time_in_force="ioc"), "k1")
    assert (await a.get_orders())[0]["status"] == "cancelled"


async def test_stop_buy_triggers_when_mark_crosses():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    await a.submit_order(_eq(order_type="stop", side="buy", stop_price=Decimal("49")), "k1")  # 50 >= 49 -> trigger
    assert (await a.get_orders())[0]["status"] == "filled"


async def test_cancel_open_then_filled():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    r = await a.submit_order(_eq(order_type="limit", side="buy", limit_price=Decimal("48")), "k1")  # open
    assert await a.cancel_order(r.broker_order_id) is True
    assert (await a.get_orders())[0]["status"] == "cancelled"
    r2 = await a.submit_order(_eq(qty=1), "k2")  # filled
    assert await a.cancel_order(r2.broker_order_id) is False


async def test_idempotent_submit_does_not_double_fill():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    r1 = await a.submit_order(_eq(qty=10), "same")
    r2 = await a.submit_order(_eq(qty=10), "same")
    assert r1 == r2
    assert await a.get_account_balance() == Decimal("100000") - Decimal("500")  # only one fill
    assert (await a.get_positions())[0].qty == 10


async def test_buy_then_partial_sell_nets_position_and_cash():
    a = PaperBrokerAdapter(Decimal("100000"), _mark(50))
    await a.submit_order(_eq(side="buy", qty=10), "k1")
    await a.submit_order(_eq(side="sell", qty=4), "k2")
    pos = await a.get_positions()
    assert pos[0].qty == 6 and pos[0].avg_price == Decimal("50")
    assert await a.get_account_balance() == Decimal("100000") - Decimal("500") + Decimal("200")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/brokers/tests/test_paper_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_brokers.paper'`.

- [ ] **Step 3: Write the adapter**

```python
# packages/brokers/saalr_brokers/paper.py
from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .base import BrokerAdapter
from .types import BrokerFill, BrokerOrder, BrokerOrderResult, BrokerPosition

_OPTION_MULT = 100


@dataclass
class _BookOrder:
    broker_order_id: str
    order: BrokerOrder
    status: str  # "open" | "filled" | "cancelled"
    fill_price: Decimal | None = None


class PaperBrokerAdapter(BrokerAdapter):
    """Deterministic mark-price paper fills. Synchronous; no RNG, no wall-clock in fills."""

    def __init__(self, starting_cash: Decimal, mark_provider: Callable[[BrokerOrder], Decimal]) -> None:
        self._cash = Decimal(starting_cash)
        self._mark = mark_provider
        self._orders: dict[str, _BookOrder] = {}
        self._idem: dict[str, BrokerOrderResult] = {}
        self._positions: dict[tuple, dict] = {}
        self._fills: list[BrokerFill] = []
        self._seq = 0

    def _next(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq}"

    @staticmethod
    def _mult(order: BrokerOrder) -> int:
        return _OPTION_MULT if order.option_type else 1

    @staticmethod
    def _key(order: BrokerOrder) -> tuple:
        return (order.symbol, order.option_type, str(order.strike), str(order.expiry))

    def _marketable(self, order: BrokerOrder, mark: Decimal) -> tuple[bool, Decimal | None]:
        t = order.order_type
        if t == "market":
            return True, mark
        if t == "limit":
            if order.side == "buy" and mark <= order.limit_price:
                return True, order.limit_price
            if order.side == "sell" and mark >= order.limit_price:
                return True, order.limit_price
            return False, None
        if t in ("stop", "stop_limit"):
            triggered = (order.side == "buy" and mark >= order.stop_price) or (
                order.side == "sell" and mark <= order.stop_price
            )
            if not triggered:
                return False, None
            if t == "stop":
                return True, mark
            # stop_limit: now behave as a limit
            if order.side == "buy" and mark <= order.limit_price:
                return True, order.limit_price
            if order.side == "sell" and mark >= order.limit_price:
                return True, order.limit_price
            return False, None
        return False, None

    def _apply_fill(self, boid: str, order: BrokerOrder, price: Decimal) -> None:
        notional = price * order.qty * self._mult(order)
        signed = order.qty if order.side == "buy" else -order.qty
        self._cash += -notional if order.side == "buy" else notional
        self._add_position(order, signed, price)
        self._fills.append(
            BrokerFill(broker_order_id=boid, broker_execution_id=self._next("pe"),
                       qty=order.qty, price=price, commission=Decimal(0))
        )

    def _add_position(self, order: BrokerOrder, signed_qty: int, price: Decimal) -> None:
        key = self._key(order)
        pos = self._positions.get(key, {"qty": 0, "avg_price": Decimal(0), "order": order})
        old = pos["qty"]
        new = old + signed_qty
        if old == 0 or (old > 0) == (signed_qty > 0):  # opening/adding same direction
            total = pos["avg_price"] * abs(old) + price * abs(signed_qty)
            pos["avg_price"] = total / abs(new) if new != 0 else Decimal(0)
        pos["qty"] = new
        if new == 0:
            self._positions.pop(key, None)
        else:
            self._positions[key] = pos

    async def submit_order(self, order: BrokerOrder, idempotency_key: str) -> BrokerOrderResult:
        if idempotency_key in self._idem:
            return self._idem[idempotency_key]
        boid = self._next("po")
        marketable, fill_price = self._marketable(order, self._mark(order))
        if marketable:
            self._apply_fill(boid, order, fill_price)
            self._orders[boid] = _BookOrder(boid, order, "filled", fill_price)
        elif order.time_in_force in ("ioc", "fok"):
            self._orders[boid] = _BookOrder(boid, order, "cancelled")
        else:
            self._orders[boid] = _BookOrder(boid, order, "open")
        result = BrokerOrderResult(broker_order_id=boid, status="submitted")
        self._idem[idempotency_key] = result
        return result

    async def cancel_order(self, broker_order_id: str) -> bool:
        bo = self._orders.get(broker_order_id)
        if bo is None or bo.status != "open":
            return False
        bo.status = "cancelled"
        return True

    async def get_orders(self, since: datetime | None = None) -> list[dict]:
        return [
            {"broker_order_id": b.broker_order_id, "status": b.status, "symbol": b.order.symbol,
             "qty": b.order.qty, "side": b.order.side, "fill_price": b.fill_price}
            for b in self._orders.values()
        ]

    async def get_positions(self) -> list[BrokerPosition]:
        out: list[BrokerPosition] = []
        for pos in self._positions.values():
            order = pos["order"]
            qty, avg, mult = pos["qty"], pos["avg_price"], self._mult(order)
            mark = self._mark(order)
            out.append(
                BrokerPosition(
                    symbol=order.symbol, qty=qty, avg_price=avg,
                    market_value=mark * qty * mult, unrealized_pnl=(mark - avg) * qty * mult,
                )
            )
        return out

    async def get_account_balance(self) -> Decimal:
        return self._cash

    async def stream_executions(self) -> AsyncIterator[BrokerFill]:
        while self._fills:
            yield self._fills.pop(0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/brokers/tests/test_paper_adapter.py -v`
Expected: PASS (9).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/brokers/saalr_brokers/paper.py packages/brokers/tests/test_paper_adapter.py
git add packages/brokers/saalr_brokers/paper.py packages/brokers/tests/test_paper_adapter.py
git commit -m "feat(brokers): PaperBrokerAdapter — deterministic mark-price fills"
```

---

## Task 3: OMS order-status FSM

**Files:**
- Create: `packages/core/saalr_core/oms/__init__.py` (empty)
- Create: `packages/core/saalr_core/oms/types.py`
- Create: `packages/core/saalr_core/oms/fsm.py`
- Test: `packages/core/tests/test_oms_fsm.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_oms_fsm.py
import pytest

from saalr_core.oms.fsm import IllegalOrderTransition, transition
from saalr_core.oms.types import OrderStatus as S


def test_legal_transitions():
    assert transition(S.PENDING, S.SUBMITTED) == S.SUBMITTED
    assert transition(S.SUBMITTED, S.PARTIAL) == S.PARTIAL
    assert transition(S.SUBMITTED, S.FILLED) == S.FILLED
    assert transition(S.PARTIAL, S.FILLED) == S.FILLED
    assert transition(S.PENDING, S.REJECTED) == S.REJECTED
    assert transition(S.SUBMITTED, S.CANCELLED) == S.CANCELLED


@pytest.mark.parametrize("a,b", [
    (S.PENDING, S.FILLED),       # must go through submitted
    (S.FILLED, S.SUBMITTED),     # terminal
    (S.CANCELLED, S.SUBMITTED),  # terminal
    (S.REJECTED, S.FILLED),      # terminal
    (S.PARTIAL, S.SUBMITTED),    # cannot go back
])
def test_illegal_transitions_raise(a, b):
    with pytest.raises(IllegalOrderTransition):
        transition(a, b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_oms_fsm.py -v`
Expected: FAIL — `ModuleNotFoundError` for `saalr_core.oms.*`.

- [ ] **Step 3: Write types (status + value types) + fsm**

```python
# packages/core/saalr_core/oms/types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# risk reason codes
RISK_INVALID_QUANTITY = "RISK_INVALID_QUANTITY"
RISK_INVALID_ORDER_TYPE = "RISK_INVALID_ORDER_TYPE"
RISK_INVALID_SIDE = "RISK_INVALID_SIDE"
RISK_INVALID_TIF = "RISK_INVALID_TIF"
RISK_MISSING_LIMIT_PRICE = "RISK_MISSING_LIMIT_PRICE"
RISK_MISSING_STOP_PRICE = "RISK_MISSING_STOP_PRICE"
RISK_ACCOUNT_INACTIVE = "RISK_ACCOUNT_INACTIVE"
RISK_STRATEGY_NOT_EXECUTABLE = "RISK_STRATEGY_NOT_EXECUTABLE"
RISK_INSUFFICIENT_BUYING_POWER = "RISK_INSUFFICIENT_BUYING_POWER"
RISK_RATE_LIMIT_EXCEEDED = "RISK_RATE_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class OrderRequest:
    side: str
    qty: int
    order_type: str
    symbol: str
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "day"
    option_type: str | None = None
    strike: Decimal | None = None
    expiry: date | None = None


@dataclass(frozen=True)
class RiskContext:
    account_active: bool
    strategy_state: str | None
    available_balance: Decimal
    estimated_cost: Decimal
    recent_order_count: int = 0
    rate_limit: int | None = None


@dataclass(frozen=True)
class RiskDecision:
    ok: bool
    code: str | None = None
    message: str | None = None
```

```python
# packages/core/saalr_core/oms/fsm.py
from __future__ import annotations

from .types import OrderStatus

VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.SUBMITTED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    OrderStatus.SUBMITTED: {OrderStatus.PARTIAL, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED},
    OrderStatus.PARTIAL: {OrderStatus.FILLED, OrderStatus.CANCELLED},
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
}


class IllegalOrderTransition(Exception):
    """Raised when an order status transition is not permitted by the FSM."""


def transition(current: OrderStatus, target: OrderStatus) -> OrderStatus:
    if target not in VALID_TRANSITIONS[current]:
        raise IllegalOrderTransition(f"{current.value} -> {target.value} is not allowed")
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_oms_fsm.py -v`
Expected: PASS (legal + 5 parametrized illegal).

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/oms/types.py packages/core/saalr_core/oms/fsm.py packages/core/tests/test_oms_fsm.py
git add packages/core/saalr_core/oms/__init__.py packages/core/saalr_core/oms/types.py packages/core/saalr_core/oms/fsm.py packages/core/tests/test_oms_fsm.py
git commit -m "feat(oms): order-status FSM + value types"
```

---

## Task 4: OMS pre-trade risk gates

**Files:**
- Create: `packages/core/saalr_core/oms/risk.py`
- Test: `packages/core/tests/test_oms_risk.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/core/tests/test_oms_risk.py
from decimal import Decimal

from saalr_core.oms.risk import estimate_cost, run_gates
from saalr_core.oms.types import OrderRequest, RiskContext


def _o(**kw):
    base = dict(side="buy", qty=10, order_type="market", symbol="AAPL")
    base.update(kw)
    return OrderRequest(**base)


def _ctx(**kw):
    base = dict(account_active=True, strategy_state="paper",
               available_balance=Decimal("100000"), estimated_cost=Decimal("500"),
               recent_order_count=0, rate_limit=None)
    base.update(kw)
    return RiskContext(**base)


def test_clean_order_passes():
    assert run_gates(_o(), _ctx()).ok is True


def test_invalid_quantity():
    d = run_gates(_o(qty=0), _ctx())
    assert d.ok is False and d.code == "RISK_INVALID_QUANTITY"


def test_limit_without_price():
    d = run_gates(_o(order_type="limit"), _ctx())
    assert d.code == "RISK_MISSING_LIMIT_PRICE"


def test_stop_without_price():
    d = run_gates(_o(order_type="stop"), _ctx())
    assert d.code == "RISK_MISSING_STOP_PRICE"


def test_inactive_account():
    assert run_gates(_o(), _ctx(account_active=False)).code == "RISK_ACCOUNT_INACTIVE"


def test_strategy_not_executable():
    assert run_gates(_o(), _ctx(strategy_state="draft")).code == "RISK_STRATEGY_NOT_EXECUTABLE"
    # no attached strategy is fine
    assert run_gates(_o(), _ctx(strategy_state=None)).ok is True


def test_insufficient_buying_power():
    d = run_gates(_o(), _ctx(estimated_cost=Decimal("200000")))
    assert d.code == "RISK_INSUFFICIENT_BUYING_POWER"
    # a sell does not consume cash
    assert run_gates(_o(side="sell"), _ctx(estimated_cost=Decimal("200000"))).ok is True


def test_rate_limit():
    assert run_gates(_o(), _ctx(recent_order_count=10, rate_limit=10)).code == "RISK_RATE_LIMIT_EXCEEDED"
    assert run_gates(_o(), _ctx(recent_order_count=9, rate_limit=10)).ok is True


def test_first_failure_wins_structural_before_buying_power():
    # qty=0 AND cost>balance -> structural reported first
    d = run_gates(_o(qty=0), _ctx(estimated_cost=Decimal("999999")))
    assert d.code == "RISK_INVALID_QUANTITY"


def test_estimate_cost_option_vs_equity():
    assert estimate_cost(_o(option_type="CALL", qty=1), Decimal("2.5")) == Decimal("250.0")
    assert estimate_cost(_o(qty=10), Decimal("50")) == Decimal("500")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest packages/core/tests/test_oms_risk.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_core.oms.risk'`.

- [ ] **Step 3: Write the gates**

```python
# packages/core/saalr_core/oms/risk.py
from __future__ import annotations

from decimal import Decimal

from .types import (
    RISK_ACCOUNT_INACTIVE,
    RISK_INSUFFICIENT_BUYING_POWER,
    RISK_INVALID_ORDER_TYPE,
    RISK_INVALID_QUANTITY,
    RISK_INVALID_SIDE,
    RISK_INVALID_TIF,
    RISK_MISSING_LIMIT_PRICE,
    RISK_MISSING_STOP_PRICE,
    RISK_RATE_LIMIT_EXCEEDED,
    RISK_STRATEGY_NOT_EXECUTABLE,
    OrderRequest,
    RiskContext,
    RiskDecision,
)

_OPTION_MULT = 100
_ORDER_TYPES = {"market", "limit", "stop", "stop_limit"}
_SIDES = {"buy", "sell"}
_TIFS = {"day", "gtc", "ioc", "fok"}
_EXECUTABLE_STATES = {"paper", "live"}


def _structural(o: OrderRequest, ctx: RiskContext) -> str | None:
    if o.qty <= 0:
        return RISK_INVALID_QUANTITY
    if o.side not in _SIDES:
        return RISK_INVALID_SIDE
    if o.order_type not in _ORDER_TYPES:
        return RISK_INVALID_ORDER_TYPE
    if o.time_in_force not in _TIFS:
        return RISK_INVALID_TIF
    if o.order_type in ("limit", "stop_limit") and (o.limit_price is None or o.limit_price <= 0):
        return RISK_MISSING_LIMIT_PRICE
    if o.order_type in ("stop", "stop_limit") and (o.stop_price is None or o.stop_price <= 0):
        return RISK_MISSING_STOP_PRICE
    return None


def _executable_state(o: OrderRequest, ctx: RiskContext) -> str | None:
    if not ctx.account_active:
        return RISK_ACCOUNT_INACTIVE
    if ctx.strategy_state is not None and ctx.strategy_state not in _EXECUTABLE_STATES:
        return RISK_STRATEGY_NOT_EXECUTABLE
    return None


def _buying_power(o: OrderRequest, ctx: RiskContext) -> str | None:
    if o.side == "buy" and ctx.estimated_cost > ctx.available_balance:
        return RISK_INSUFFICIENT_BUYING_POWER
    return None


def _rate_cap(o: OrderRequest, ctx: RiskContext) -> str | None:
    if ctx.rate_limit is not None and ctx.recent_order_count >= ctx.rate_limit:
        return RISK_RATE_LIMIT_EXCEEDED
    return None


_GATES = (_structural, _executable_state, _buying_power, _rate_cap)


def run_gates(order: OrderRequest, ctx: RiskContext) -> RiskDecision:
    """Run the pre-trade gates in order; return the FIRST failure, else ok."""
    for gate in _GATES:
        code = gate(order, ctx)
        if code is not None:
            return RiskDecision(ok=False, code=code, message=code.removeprefix("RISK_").replace("_", " ").lower())
    return RiskDecision(ok=True)


def estimate_cost(order: OrderRequest, mark: Decimal) -> Decimal:
    mult = _OPTION_MULT if order.option_type else 1
    return mark * order.qty * mult
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest packages/core/tests/test_oms_risk.py -v`
Expected: PASS (all). Note `estimate_cost` returns `Decimal("250.0")` for the option case (`2.5 * 1 * 100`) — the test compares with `Decimal("250.0")` to match the scale.

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/core/saalr_core/oms/risk.py packages/core/tests/test_oms_risk.py
git add packages/core/saalr_core/oms/risk.py packages/core/tests/test_oms_risk.py
git commit -m "feat(oms): pure pre-trade risk gates + estimate_cost"
```

---

## Task 5: Full gate

**Files:** none (verification only).

- [ ] **Step 1: Core + brokers suites**

Run: `uv run pytest packages/core/tests packages/brokers/tests -q`
Expected: all green.

- [ ] **Step 2: Lint**

Run: `uvx ruff check packages/brokers/saalr_brokers packages/core/saalr_core/oms`
Expected: clean.

- [ ] **Step 3: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "chore(oms): OMS-1 order core — suite + lint green"
```

---

## Self-review notes (addressed)

- **Spec coverage:** broker types + ABC (T1), deterministic mark-price PaperBrokerAdapter incl. idempotency + cash/position math (T2), order FSM (T3), the four pure risk gates + estimate_cost + first-failure ordering (T4), gate (T5).
- **Account-mode-agnostic:** `PaperBrokerAdapter` subclasses `BrokerAdapter`; `get_account_balance` feeds the buying-power gate; nothing branches on paper-vs-live.
- **Determinism:** no RNG / wall-clock in fills; `mark_provider` injected; `_seq` counter for ids. Tests assert exact `Decimal`s.
- **Type/units consistency:** `BrokerOrder`/`OrderRequest` use `buy/sell`, `market/limit/stop/stop_limit`, `day/gtc/ioc/fok` (matching the `orders` CHECK); option multiplier 100 in both `estimate_cost` and the adapter; `OrderStatus` values match the `orders` status CHECK. `run_gates` returns the first failure (structural before buying-power, asserted).
- **No new tables:** OMS-1 adds none; the `orders`/`executions`/`positions` persistence is OMS-2.
- **Packaging:** `saalr-brokers` becomes a root dep (pure now); `alpaca-py` will be an optional extra in OMS-3.
