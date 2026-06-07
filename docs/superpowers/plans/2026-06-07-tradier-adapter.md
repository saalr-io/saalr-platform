# Tradier Broker Adapter (sandbox) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `TradierAdapter` (raw httpx, options-native) against the Tradier sandbox and generalize the OMS from hardcoded paper/alpaca to a broker→factory registry, so orders route to Tradier the same way they route to Alpaca.

**Architecture:** A new `BrokerAdapter` implementation talks to the Tradier REST sandbox over httpx; pure mapping helpers are unit-tested and the HTTP methods are tested via `httpx.MockTransport`. A shared `BrokerError` (moved to `base.py`) and a shared `occ.py` are reused by both adapters. The OMS gains `app.state.adapter_factories` and selects the adapter by `account.broker`; the router merges the legacy `alpaca_adapter_factory` into the registry so existing tests keep passing untouched.

**Tech Stack:** Python, httpx (async, no SDK), SQLAlchemy async, FastAPI, pytest.

**Spec:** [docs/superpowers/specs/2026-06-07-tradier-adapter-design.md](../specs/2026-06-07-tradier-adapter-design.md)

---

## File Structure

- Create `packages/brokers/saalr_brokers/occ.py` — `occ_symbol` (moved out of `alpaca.py`).
- Modify `packages/brokers/saalr_brokers/base.py` — add shared `BrokerError`.
- Modify `packages/brokers/saalr_brokers/alpaca.py` — re-export `occ_symbol` + `BrokerError`.
- Create `packages/brokers/saalr_brokers/tradier.py` — `TradierAdapter` + pure helpers + `TradierError`.
- Modify `packages/brokers/saalr_brokers/credentials.py` — `build_tradier_adapter`.
- Create `packages/brokers/tests/test_tradier_pure.py`, `packages/brokers/tests/test_tradier_adapter.py`.
- Modify `apps/api/saalr_api/oms/service.py` — broker-agnostic routing.
- Modify `apps/api/saalr_api/oms/router.py` — registry + accept `tradier`.
- Modify `apps/api/saalr_api/main.py` — wire `adapter_factories`.
- Create `tests/integration/test_oms_tradier.py`.

---

## Task 1: Extract shared `occ_symbol` + `BrokerError`

**Files:**
- Create: `packages/brokers/saalr_brokers/occ.py`
- Modify: `packages/brokers/saalr_brokers/base.py`, `packages/brokers/saalr_brokers/alpaca.py`

- [ ] **Step 1: Create `occ.py`**

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal


def occ_symbol(root: str, expiry: date, option_type: str, strike: float | Decimal) -> str:
    """OCC option symbol: ROOT + YYMMDD + C/P + strike*1000 zero-padded to 8 digits."""
    cp = "C" if option_type.upper() in ("CALL", "CE") else "P"
    strike_milli = int((Decimal(str(strike)) * 1000).to_integral_value())  # Decimal-native: no float drift
    return f"{root.upper()}{expiry:%y%m%d}{cp}{strike_milli:08d}"
```

- [ ] **Step 2: Add shared `BrokerError` to `base.py`**

At the top of `packages/brokers/saalr_brokers/base.py` (after the imports, before `class BrokerAdapter`), add:

```python
class BrokerError(Exception):
    """Base error for broker adapters (transport/SDK/HTTP failures). Never carries secrets."""
```

- [ ] **Step 3: Re-export from `alpaca.py` (delete its local definitions)**

In `packages/brokers/saalr_brokers/alpaca.py`, replace the local `class BrokerError(...)` (lines 12-13) and the local `def occ_symbol(...)` (lines 16-20) with re-exports. Change the import block + remove both definitions so the top of the file reads:

```python
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date, datetime
from decimal import Decimal

from .base import BrokerAdapter, BrokerError
from .occ import occ_symbol
from .types import BrokerFill, BrokerOrder, BrokerOrderResult, BrokerPosition
```

(`BrokerError` and `occ_symbol` remain importable as `from saalr_brokers.alpaca import BrokerError, occ_symbol` for existing callers/tests.)

- [ ] **Step 4: Run the existing broker + OMS tests to verify nothing broke**

Run: `uv run python -m pytest packages/brokers/tests/test_alpaca_pure.py packages/brokers/tests/test_alpaca_adapter.py -q`
Expected: PASS (occ_symbol/BrokerError still resolve via the re-export).

- [ ] **Step 5: Commit**

```bash
git add packages/brokers/saalr_brokers/occ.py packages/brokers/saalr_brokers/base.py packages/brokers/saalr_brokers/alpaca.py
git commit -m "refactor(brokers): share occ_symbol + BrokerError across adapters"
```

---

## Task 2: Tradier pure mapping helpers

**Files:**
- Create: `packages/brokers/saalr_brokers/tradier.py` (helpers only this task)
- Test: `packages/brokers/tests/test_tradier_pure.py`

- [ ] **Step 1: Write the failing test**

Create `packages/brokers/tests/test_tradier_pure.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

from saalr_brokers.tradier import (
    build_order_form, map_status, parse_balance, parse_orders, parse_positions,
)
from saalr_brokers.types import BrokerOrder


def test_build_order_form_equity_limit():
    o = BrokerOrder(symbol="AAPL", side="buy", qty=3, order_type="limit",
                    limit_price=Decimal("100.50"), time_in_force="day")
    f = build_order_form(o, "idem-1")
    assert f == {
        "class": "equity", "symbol": "AAPL", "side": "buy", "quantity": "3",
        "type": "limit", "duration": "day", "price": "100.50", "tag": "idem-1",
    }


def test_build_order_form_option_open_side_and_occ():
    o = BrokerOrder(symbol="AAPL", side="sell", qty=1, order_type="market",
                    option_type="CALL", strike=Decimal("180"), expiry=date(2026, 9, 18),
                    time_in_force="day")
    f = build_order_form(o, "idem-2")
    assert f["class"] == "option"
    assert f["symbol"] == "AAPL"
    assert f["option_symbol"] == "AAPL260918C00180000"
    assert f["side"] == "sell_to_open"          # sell -> sell_to_open (open-only)
    assert f["type"] == "market" and f["duration"] == "day"
    assert "price" not in f                       # market has no price


def test_map_status():
    assert map_status("filled") == "filled"
    assert map_status("partially_filled") == "partial"
    assert map_status("canceled") == "cancelled"
    assert map_status("rejected") == "rejected"
    assert map_status("open") == "submitted"
    assert map_status("ok") == "submitted"
    assert map_status("something-new") == "submitted"


def test_parse_orders_single_object_and_tag():
    # Tradier returns a single object (not a list) for one order
    body = {"orders": {"order": {
        "id": 123, "status": "filled", "symbol": "AAPL", "quantity": 3, "side": "buy",
        "exec_quantity": 3, "avg_fill_price": 100.5, "tag": "idem-1"}}}
    rows = parse_orders(body)
    assert rows == [{
        "broker_order_id": "123", "status": "filled", "symbol": "AAPL", "qty": 3,
        "side": "buy", "filled_qty": 3, "filled_avg_price": Decimal("100.5"),
        "client_order_id": "idem-1",
    }]


def test_parse_orders_empty():
    assert parse_orders({"orders": "null"}) == []


def test_parse_positions():
    body = {"positions": {"position": {"symbol": "AAPL", "quantity": 2, "cost_basis": 200.0}}}
    ps = parse_positions(body)
    assert ps[0].symbol == "AAPL" and ps[0].qty == 2
    assert ps[0].avg_price == Decimal("100")
    assert ps[0].market_value == Decimal("200.0") and ps[0].unrealized_pnl == Decimal(0)


def test_parse_balance_prefers_option_buying_power():
    assert parse_balance({"balances": {"option_buying_power": 5000.0, "total_cash": 1000.0}}) == Decimal("5000.0")
    assert parse_balance({"balances": {"total_cash": 1000.0}}) == Decimal("1000.0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest packages/brokers/tests/test_tradier_pure.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_brokers.tradier'`.

- [ ] **Step 3: Write `tradier.py` (helpers only)**

Create `packages/brokers/saalr_brokers/tradier.py`:

```python
from __future__ import annotations

from decimal import Decimal

from .base import BrokerError
from .occ import occ_symbol
from .types import BrokerPosition


class TradierError(BrokerError):
    """Wraps a Tradier transport/HTTP error so callers don't see raw httpx exceptions."""


_OPTION_SIDE = {"buy": "buy_to_open", "sell": "sell_to_open"}  # open-only (see spec limitations)
_DURATION = {"day": "day", "gtc": "gtc"}                       # ioc/fok -> day

_STATUS = {
    "filled": "filled",
    "partially_filled": "partial", "partial": "partial",
    "canceled": "cancelled", "cancelled": "cancelled", "expired": "cancelled",
    "rejected": "rejected", "error": "rejected",
}


def map_status(status: str) -> str:
    """Tradier order status -> our OrderStatus value. Unknown/open/ok -> 'submitted'."""
    return _STATUS.get(str(status).lower(), "submitted")


def build_order_form(order, tag: str) -> dict[str, str]:
    """Pure: BrokerOrder -> Tradier order form params (equity or single option leg)."""
    duration = _DURATION.get(order.time_in_force, "day")
    form: dict[str, str] = {
        "side": "", "quantity": str(order.qty), "type": order.order_type, "duration": duration,
        "tag": tag[:40],
    }
    if order.option_type:
        form["class"] = "option"
        form["symbol"] = order.symbol.upper()
        form["option_symbol"] = occ_symbol(order.symbol, order.expiry, order.option_type, order.strike)
        form["side"] = _OPTION_SIDE[order.side]
    else:
        form["class"] = "equity"
        form["symbol"] = order.symbol.upper()
        form["side"] = order.side
    if order.limit_price is not None and order.order_type in ("limit", "stop_limit"):
        form["price"] = str(order.limit_price)
    if order.stop_price is not None and order.order_type in ("stop", "stop_limit"):
        form["stop"] = str(order.stop_price)
    return form


def _as_list(node) -> list:
    """Tradier returns 'null', a single object, or a list. Normalize to a list."""
    if node in (None, "null", ""):
        return []
    return node if isinstance(node, list) else [node]


def parse_orders(body: dict) -> list[dict]:
    orders = _as_list((body.get("orders") or {}).get("order") if isinstance(body.get("orders"), dict)
                      else body.get("orders"))
    out: list[dict] = []
    for o in orders:
        fap = o.get("avg_fill_price")
        out.append({
            "broker_order_id": str(o.get("id")),
            "status": map_status(o.get("status", "")),
            "symbol": o.get("symbol"),
            "qty": int(o.get("quantity") or 0),
            "side": o.get("side"),
            "filled_qty": int(o.get("exec_quantity") or 0),
            "filled_avg_price": Decimal(str(fap)) if fap else None,
            "client_order_id": o.get("tag"),
        })
    return out


def parse_positions(body: dict) -> list[BrokerPosition]:
    node = body.get("positions")
    positions = _as_list(node.get("position") if isinstance(node, dict) else node)
    out: list[BrokerPosition] = []
    for p in positions:
        qty = int(p.get("quantity") or 0)
        cost = Decimal(str(p.get("cost_basis") or 0))
        avg = (cost / qty) if qty else Decimal(0)
        out.append(BrokerPosition(symbol=p.get("symbol"), qty=qty, avg_price=avg,
                                  market_value=cost, unrealized_pnl=Decimal(0)))
    return out


def parse_balance(body: dict) -> Decimal:
    b = body.get("balances") or {}
    for k in ("option_buying_power", "stock_buying_power", "total_cash", "total_equity"):
        if b.get(k) is not None:
            return Decimal(str(b[k]))
    return Decimal(0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest packages/brokers/tests/test_tradier_pure.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add packages/brokers/saalr_brokers/tradier.py packages/brokers/tests/test_tradier_pure.py
git commit -m "feat(brokers): Tradier pure mappers (order form, status, parsers)"
```

---

## Task 3: TradierAdapter HTTP methods

**Files:**
- Modify: `packages/brokers/saalr_brokers/tradier.py` (add the adapter class)
- Test: `packages/brokers/tests/test_tradier_adapter.py`

- [ ] **Step 1: Write the failing test**

Create `packages/brokers/tests/test_tradier_adapter.py`:

```python
from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from saalr_brokers.tradier import TradierAdapter
from saalr_brokers.types import BrokerOrder


def _adapter(handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                               base_url="https://sandbox.tradier.com/v1")
    return TradierAdapter("tok", "VA123", is_paper=True, client=client)


@pytest.mark.asyncio
async def test_submit_order_success():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"order": {"id": 42, "status": "ok"}})

    res = await _adapter(handler).submit_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=1, order_type="market"), "idem-9")
    assert res.broker_order_id == "42" and res.status == "submitted"
    assert "/accounts/VA123/orders" in seen["url"]
    assert "class=equity" in seen["body"] and "tag=idem-9" in seen["body"]


@pytest.mark.asyncio
async def test_submit_order_rejected():
    def handler(req):
        return httpx.Response(400, json={"errors": {"error": ["insufficient buying power"]}})

    res = await _adapter(handler).submit_order(
        BrokerOrder(symbol="AAPL", side="buy", qty=1, order_type="market"), "idem-10")
    assert res.status == "rejected"
    assert "insufficient" in (res.rejected_reason or "")


@pytest.mark.asyncio
async def test_cancel_order():
    def handler(req):
        assert req.method == "DELETE"
        return httpx.Response(200, json={"order": {"id": 42, "status": "ok"}})

    assert await _adapter(handler).cancel_order("42") is True


@pytest.mark.asyncio
async def test_get_orders_and_balance():
    def handler(req):
        if req.url.path.endswith("/orders"):
            return httpx.Response(200, json={"orders": {"order": {
                "id": 1, "status": "filled", "symbol": "AAPL", "quantity": 1, "side": "buy",
                "exec_quantity": 1, "avg_fill_price": 10.0, "tag": "t1"}}})
        return httpx.Response(200, json={"balances": {"total_cash": 1000.0}})

    a = _adapter(handler)
    orders = await a.get_orders()
    assert orders[0]["broker_order_id"] == "1" and orders[0]["status"] == "filled"
    assert await a.get_account_balance() == Decimal("1000.0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest packages/brokers/tests/test_tradier_adapter.py -q`
Expected: FAIL — `ImportError: cannot import name 'TradierAdapter'`.

- [ ] **Step 3: Add the adapter class to `tradier.py`**

Append to `packages/brokers/saalr_brokers/tradier.py`:

```python
import asyncio  # noqa: E402  (kept with the other stdlib import grouping intent)
from collections.abc import AsyncIterator  # noqa: E402
from datetime import datetime  # noqa: E402

import httpx  # noqa: E402

from .base import BrokerAdapter  # noqa: E402
from .types import BrokerFill, BrokerOrder, BrokerOrderResult  # noqa: E402

_SANDBOX = "https://sandbox.tradier.com/v1"
_LIVE = "https://api.tradier.com/v1"


class TradierAdapter(BrokerAdapter):
    """BrokerAdapter over the Tradier REST API (sandbox when is_paper)."""

    def __init__(self, access_token: str, account_id: str, is_paper: bool = True, *, client=None) -> None:
        self._token = access_token
        self._account_id = account_id
        self._base = _SANDBOX if is_paper else _LIVE
        self._client = client

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base, timeout=20.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    async def _request(self, method: str, path: str, *, data=None, params=None) -> dict:
        try:
            r = await self._http().request(method, path, headers=self._headers(),
                                           data=data, params=params)
            if r.status_code >= 400:
                # Tradier error payloads carry {"errors": {"error": [...]}}; surface the text.
                try:
                    errs = r.json().get("errors", {}).get("error")
                except Exception:
                    errs = None
                raise TradierError(
                    "; ".join(errs) if isinstance(errs, list) else (str(errs) or f"http {r.status_code}"))
            return r.json()
        except TradierError:
            raise
        except httpx.HTTPError as exc:
            raise TradierError(str(exc)) from exc

    async def submit_order(self, order: BrokerOrder, idempotency_key: str) -> BrokerOrderResult:
        try:
            body = await self._request(
                "POST", f"/accounts/{self._account_id}/orders",
                data=build_order_form(order, idempotency_key))
        except TradierError as exc:
            return BrokerOrderResult("", "rejected", str(exc))
        o = body.get("order", {})
        if map_status(o.get("status", "")) == "rejected":
            return BrokerOrderResult(str(o.get("id", "")), "rejected", str(o.get("status")))
        return BrokerOrderResult(str(o.get("id", "")), "submitted")

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await self._request("DELETE", f"/accounts/{self._account_id}/orders/{broker_order_id}")
            return True
        except TradierError:
            return False

    async def get_orders(self, since: datetime | None = None) -> list[dict]:
        body = await self._request("GET", f"/accounts/{self._account_id}/orders")
        rows = parse_orders(body)
        return rows  # since-filtering is best-effort; Tradier lacks a clean 'after' param

    async def get_positions(self):
        body = await self._request("GET", f"/accounts/{self._account_id}/positions")
        return parse_positions(body)

    async def get_account_balance(self):
        body = await self._request("GET", f"/accounts/{self._account_id}/balances")
        return parse_balance(body)

    async def stream_executions(self) -> AsyncIterator[BrokerFill]:
        raise NotImplementedError("reconcile via get_orders polling")
        yield  # unreachable; makes this an async generator so it satisfies the ABC contract
```

Note: `asyncio`/`BrokerFill` imports are present for ABC/async-generator parity even though the
sandbox path doesn't use a thread pool.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest packages/brokers/tests/test_tradier_adapter.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint (import ordering)**

Run: `uv run ruff check packages/brokers/saalr_brokers/tradier.py`
Expected: no errors. If ruff flags the mid-file imports, move them to the top of the file (above the helpers) and delete the `# noqa: E402` markers, then re-run Steps 4-5.

- [ ] **Step 6: Commit**

```bash
git add packages/brokers/saalr_brokers/tradier.py packages/brokers/tests/test_tradier_adapter.py
git commit -m "feat(brokers): TradierAdapter HTTP methods over httpx"
```

---

## Task 4: `build_tradier_adapter` builder

**Files:**
- Modify: `packages/brokers/saalr_brokers/credentials.py`
- Test: `packages/brokers/tests/test_credentials.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `packages/brokers/tests/test_credentials.py`:

```python
def test_build_tradier_adapter_maps_token_and_account_id():
    from saalr_brokers.credentials import EnvCredentialResolver, build_tradier_adapter
    from saalr_brokers.tradier import TradierAdapter

    resolver = EnvCredentialResolver({"TRADIER_SANDBOX_KEY": "tok", "TRADIER_SANDBOX_SECRET": "VA123"})
    adapter = build_tradier_adapter("env:TRADIER_SANDBOX", True, resolver)
    assert isinstance(adapter, TradierAdapter)
    assert adapter._token == "tok" and adapter._account_id == "VA123"
    assert adapter._base.startswith("https://sandbox.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest packages/brokers/tests/test_credentials.py::test_build_tradier_adapter_maps_token_and_account_id -q`
Expected: FAIL — `cannot import name 'build_tradier_adapter'`.

- [ ] **Step 3: Add the builder**

In `packages/brokers/saalr_brokers/credentials.py`, add an import near the top (after `from .alpaca import AlpacaAdapter`):

```python
from .tradier import TradierAdapter
```

And add the builder after `build_alpaca_adapter`:

```python
def build_tradier_adapter(
    credential_ref: str, is_paper: bool, resolver: CredentialResolver
) -> TradierAdapter:
    """Resolve (access_token, account_id) from the (key, secret) slots and construct a TradierAdapter."""
    token, account_id = resolver.resolve(credential_ref, is_paper)
    return TradierAdapter(token, account_id, is_paper=is_paper)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest packages/brokers/tests/test_credentials.py -q`
Expected: PASS (existing credential tests + the new one).

- [ ] **Step 5: Commit**

```bash
git add packages/brokers/saalr_brokers/credentials.py packages/brokers/tests/test_credentials.py
git commit -m "feat(brokers): build_tradier_adapter (token+account_id from resolver)"
```

---

## Task 5: OMS broker→factory registry + Tradier accounts

**Files:**
- Modify: `apps/api/saalr_api/oms/service.py`, `apps/api/saalr_api/oms/router.py`, `apps/api/saalr_api/main.py`
- Test: `tests/integration/test_oms_tradier.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_oms_tradier.py`:

```python
import httpx
from decimal import Decimal

from saalr_api.main import create_app
from saalr_brokers.types import BrokerOrderResult


class StubTradier:
    async def get_account_balance(self):
        return Decimal("100000")

    async def submit_order(self, order, idempotency_key):
        return BrokerOrderResult("T-1", "submitted")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_create_tradier_account_and_place_routes_to_tradier(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.adapter_factories = {"tradier": lambda account: StubTradier()}
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:tradier@x.com"}
            acct = (await c.post("/v1/broker-accounts",
                                 json={"broker": "tradier", "account_label": "T"}, headers=h)).json()
            assert acct["broker"] == "tradier"
            r = await c.post("/v1/orders", json={
                "broker_account_id": acct["broker_account_id"], "symbol": "AAPL",
                "side": "buy", "qty": 1, "order_type": "market"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "submitted"
    assert body["broker_order_id"] == "T-1"


async def test_unknown_broker_rejected_at_create(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:tradier2@x.com"}
            r = await c.post("/v1/broker-accounts",
                             json={"broker": "webull", "account_label": "W"}, headers=h)
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "BROKER_NOT_SUPPORTED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest tests/integration/test_oms_tradier.py -q`
Expected: FAIL — creating a `tradier` account returns 400 `BROKER_NOT_SUPPORTED` (router rejects it today).

- [ ] **Step 3: Generalize `service.py`**

In `apps/api/saalr_api/oms/service.py`:

(a) Change the error import (line 12) from alpaca to base:

```python
from saalr_brokers.base import BrokerError
```

(b) `place_order` signature (line 62-63): rename the last param:

```python
async def place_order(session: AsyncSession, principal, body: OrderCreate, idempotency_key,
                      request_id, adapter_factories=None) -> dict:
```

(c) Replace the broker gate + adapter resolution (lines 76-88) with:

```python
    supported = {"paper"} | set(adapter_factories or {})
    if account.broker not in supported:
        raise _err("BROKER_NOT_SUPPORTED", f"broker {account.broker} not yet supported", 400)
    is_live = account.broker != "paper"

    # Resolve the live adapter up front so a credential failure happens before any row insert.
    adapter = None
    if is_live:
        factory = (adapter_factories or {}).get(account.broker)
        if factory is None:
            raise _err("BROKER_UNAVAILABLE", f"no {account.broker} adapter configured", 502)
        try:
            adapter = factory(account)
        except CredentialError as exc:
            raise _err("BROKER_CREDENTIALS_UNAVAILABLE", "broker credentials unavailable", 502) from exc
```

(d) Replace every remaining `is_alpaca` with `is_live` (the `model_mark`/`NoMarketData` branch ~line 96, the balance branch ~line 109, and the submit branch ~line 143).

(e) The live submit call (line 144-145) — rename the helper:

```python
        return await _submit_live(session, order, body, adapter, idempotency_key,
                                  tenant_id, user_id, request_id, now)
```

(f) Rename the helper definition (line 226) and its docstring:

```python
async def _submit_live(session, order, body, adapter, idempotency_key, tenant_id, user_id,
                       request_id, now) -> dict:
    """Live broker submit: the order rests 'submitted' (async fills come via reconciliation)."""
```

(g) `place_strategy` signature (line 190-191) + its inner call (line 213):

```python
async def place_strategy(session: AsyncSession, principal, body, idem, request_id,
                         adapter_factories=None) -> dict:
```
```python
            res = await place_order(session, principal, order, f"{idem}:{i}", request_id, adapter_factories)
```

(h) `cancel_order` signature (line 251) + body (lines 259-264):

```python
async def cancel_order(session, principal, order_id, request_id, adapter_factories=None) -> dict:
```
```python
    account = await repo.get_broker_account(session, order.broker_account_id)
    if (account is not None and account.broker != "paper" and order.broker_order_id
            and adapter_factories is not None):
        factory = adapter_factories.get(account.broker)
        if factory is not None:
            try:
                await factory(account).cancel_order(order.broker_order_id)
            except (CredentialError, BrokerError) as exc:  # best-effort; reconciliation confirms terminal state
                _logger.warning("%s cancel failed for order %s: %s", account.broker, order_id, exc)
```

- [ ] **Step 4: Generalize `router.py`**

In `apps/api/saalr_api/oms/router.py`:

(a) Add a registry helper after `_request_id` (line 20):

```python
def _adapter_factories(request: Request):
    """Merge the per-broker registry with the legacy alpaca factory (back-compat)."""
    s = request.app.state
    reg = dict(getattr(s, "adapter_factories", {}) or {})
    legacy = getattr(s, "alpaca_adapter_factory", None)
    if legacy is not None and "alpaca" not in reg:
        reg["alpaca"] = legacy
    return reg or None
```

(b) Accept `tradier` in `create_account` (replace lines 45-57):

```python
    if body.broker not in ("paper", "alpaca", "tradier"):
        raise HTTPException(400, {"error": {"code": "BROKER_NOT_SUPPORTED",
                                            "message": "broker not supported"}})
    if body.broker == "alpaca":
        if not body.credential_ref:
            raise HTTPException(422, {"error": {"code": "VALIDATION_MISSING_CREDENTIAL_REF",
                                                "message": "credential_ref is required for alpaca"}})
        a = await repo.create_broker_account(session, principal.tenant_id, principal.user_id,
                                             "alpaca", body.account_label, body.is_paper,
                                             body.credential_ref)
    elif body.broker == "tradier":
        a = await repo.create_broker_account(session, principal.tenant_id, principal.user_id,
                                             "tradier", body.account_label, True, "env:TRADIER_SANDBOX")
    else:
        a = await repo.create_broker_account(session, principal.tenant_id, principal.user_id,
                                             "paper", body.account_label, True)
```

(c) In the three handlers that read the factory (`place` line 72, `place_strategy` line 82, `cancel` line 119), replace:

```python
    factory = getattr(request.app.state, "alpaca_adapter_factory", None)
```
with:
```python
    factories = _adapter_factories(request)
```
and pass `factories` instead of `factory` to the `service.*` call on the following line.

- [ ] **Step 5: Wire the registry in `main.py`**

In `apps/api/saalr_api/main.py`, add the import near the broker imports:

```python
from saalr_brokers.credentials import build_alpaca_adapter, build_tradier_adapter, make_credential_resolver
```

(If `build_alpaca_adapter`/`make_credential_resolver` are already imported elsewhere, just add `build_tradier_adapter` to that import.) Then, immediately after the existing `app.state.alpaca_adapter_factory = ...` assignment (line ~83-85), add:

```python
        app.state.adapter_factories = {
            "alpaca": app.state.alpaca_adapter_factory,
            "tradier": lambda account: build_tradier_adapter(
                account.credential_ref, account.is_paper, resolver),
        }
```

- [ ] **Step 6: Run the Tradier integration test + the full OMS suite**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest tests/integration/test_oms_tradier.py tests/integration/test_oms.py tests/integration/test_oms_alpaca.py tests/integration/test_oms_reconcile.py tests/integration/test_paper_strategy.py -q`
Expected: all PASS (existing OMS tests untouched still pass because `_adapter_factories` merges the legacy `alpaca_adapter_factory` they set).

- [ ] **Step 7: Commit**

```bash
git add apps/api/saalr_api/oms/service.py apps/api/saalr_api/oms/router.py apps/api/saalr_api/main.py tests/integration/test_oms_tradier.py
git commit -m "feat(oms): broker->factory registry + Tradier sandbox accounts"
```

---

## Final verification

- [ ] **Brokers + OMS suites:**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest packages/brokers/tests tests/integration/test_oms_tradier.py tests/integration/test_oms.py tests/integration/test_oms_alpaca.py tests/integration/test_oms_reconcile.py -q`
Expected: all PASS.

- [ ] **Lint:** `uv run ruff check packages/brokers/saalr_brokers apps/api/saalr_api/oms`
Expected: no errors.

- [ ] **Reconcile-worker note:** the reconcile worker still keys on Alpaca; Tradier sandbox orders rest `submitted` and won't auto-fill via reconciliation yet (documented follow-up, out of scope for this slice).
