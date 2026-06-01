# Alpaca broker adapter (OMS-3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A real `AlpacaAdapter` (alpaca-py) satisfying the `BrokerAdapter` ABC — `BrokerOrder→alpaca` mapping (incl. OCC option symbols + `client_order_id` idempotency), an Alpaca→our status map, paper/live via `is_paper`, sync SDK wrapped in `asyncio.to_thread` — with alpaca-py as an optional, lazy-imported extra so the default install stays alpaca-free.

**Architecture:** One module in `saalr-brokers` (`alpaca.py`) + tests. Pure helpers (`occ_symbol`, `map_status`) always tested; the adapter's SDK mapping tested with an injected **stub** `TradingClient` under the `alpaca` extra (no network); an env-gated live smoke. No OMS-service/DB/reconciliation changes (OMS-3b).

**Tech Stack:** Python 3.12, alpaca-py (optional extra), pytest (`pytest-asyncio`), ruff.

**Spec:** `docs/superpowers/specs/2026-06-01-alpaca-adapter-oms3a-design.md`

**Conventions / facts (verified):**
- `from __future__ import annotations` at the top of every module.
- `saalr-brokers` is a pure root dependency (OMS-1/2). `saalr_brokers.types`: `BrokerOrder{symbol, side("buy"/"sell"), qty:int, order_type("market"/"limit"/"stop"/"stop_limit"), limit_price:Decimal|None, stop_price:Decimal|None, time_in_force("day"/"gtc"/"ioc"/"fok"), option_type:str|None, strike:Decimal|None, expiry:date|None}`, `BrokerOrderResult{broker_order_id, status, rejected_reason}`, `BrokerPosition{symbol, qty, avg_price, market_value, unrealized_pnl}`. `BrokerAdapter` (ABC) declares `async def stream_executions(self) -> AsyncIterator[BrokerFill]`.
- The existing env-gated live-smoke pattern (`tests/integration/test_market_smoke.py`): module/per-test `pytest.mark.skipif`. For an importorskip on an optional dep: `pytest.importorskip("alpaca")` at module top skips the whole file when the SDK isn't installed.
- alpaca-py API (verify exact attribute names/types against the installed version while implementing; adjust `Decimal(str(...))`/`int(...)` conversions if it differs — the stub + live smoke catch mismatches): `from alpaca.trading.client import TradingClient` (constructed `TradingClient(key, secret, paper=is_paper)`, **synchronous**); `from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest, StopLimitOrderRequest`; `from alpaca.trading.enums import OrderSide, TimeInForce` (value-constructible: `OrderSide("buy")`, `TimeInForce("day")`). `client.submit_order(req) -> Order(.id, .status, .qty, .filled_qty, .filled_avg_price, .side, .symbol, .client_order_id, .rejected_reason)`; `client.cancel_order_by_id(id)`; `client.get_orders() -> list[Order]`; `client.get_all_positions() -> list[Position(.symbol,.qty,.avg_entry_price,.market_value,.unrealized_pl)]`; `client.get_account() -> Account(.buying_power)`.

---

## Task 1: pure helpers — `occ_symbol` + `map_status` (+ module scaffold)

**Files:**
- Modify: `packages/brokers/pyproject.toml` (add the `alpaca` optional extra)
- Create: `packages/brokers/saalr_brokers/alpaca.py` (pure helpers + `BrokerError`; the adapter class lands in Task 2)
- Test: `packages/brokers/tests/test_alpaca_pure.py`

- [ ] **Step 1: Add the optional extra**

In `packages/brokers/pyproject.toml`, add (keep `dependencies = ["saalr-core"]`):
```toml
[project.optional-dependencies]
alpaca = ["alpaca-py>=0.20"]
```

- [ ] **Step 2: Write the failing pure tests**

```python
# packages/brokers/tests/test_alpaca_pure.py
from datetime import date

from saalr_brokers.alpaca import map_status, occ_symbol


def test_occ_symbol_call_and_put():
    assert occ_symbol("AAPL", date(2025, 6, 20), "CALL", 100.0) == "AAPL250620C00100000"
    assert occ_symbol("AAPL", date(2025, 6, 20), "PUT", 100.0) == "AAPL250620P00100000"


def test_occ_symbol_strike_milli_padding():
    assert occ_symbol("SPY", date(2026, 1, 16), "CALL", 5.5).endswith("C00005500")
    assert occ_symbol("SPY", date(2026, 1, 16), "PUT", 432.5).endswith("P00432500")
    assert occ_symbol("CE", date(2026, 1, 16), "CE", 10) == "CE260116C00010000"  # CE option_type -> call


def test_map_status_known_and_unknown():
    assert map_status("new") == "submitted"
    assert map_status("accepted") == "submitted"
    assert map_status("partially_filled") == "partial"
    assert map_status("filled") == "filled"
    assert map_status("canceled") == "cancelled"
    assert map_status("expired") == "cancelled"
    assert map_status("rejected") == "rejected"
    assert map_status("suspended") == "rejected"
    assert map_status("something_new") == "submitted"  # conservative default


def test_map_status_handles_enum_like():
    class _S:
        value = "FILLED"
    assert map_status(_S()) == "filled"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest packages/brokers/tests/test_alpaca_pure.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_brokers.alpaca'`.

- [ ] **Step 4: Write the pure module**

```python
# packages/brokers/saalr_brokers/alpaca.py
from __future__ import annotations

from datetime import date
from decimal import Decimal


class BrokerError(Exception):
    """Wraps an alpaca SDK/transport error so callers don't see raw alpaca exceptions."""


def occ_symbol(root: str, expiry: date, option_type: str, strike: float | Decimal) -> str:
    """OCC option symbol: ROOT + YYMMDD + C/P + strike*1000 zero-padded to 8 digits."""
    cp = "C" if option_type.upper() in ("CALL", "CE") else "P"
    strike_milli = int(round(float(strike) * 1000))
    return f"{root.upper()}{expiry:%y%m%d}{cp}{strike_milli:08d}"


_ALPACA_STATUS: dict[str, str] = {
    "new": "submitted", "accepted": "submitted", "pending_new": "submitted",
    "accepted_for_bidding": "submitted",
    "partially_filled": "partial",
    "filled": "filled",
    "canceled": "cancelled", "expired": "cancelled", "done_for_day": "cancelled",
    "pending_cancel": "cancelled",
    "rejected": "rejected", "suspended": "rejected", "stopped": "rejected",
}


def map_status(status) -> str:
    """Alpaca order status (str or enum) -> our OrderStatus value. Unknown -> 'submitted'."""
    s = str(getattr(status, "value", status)).lower()
    return _ALPACA_STATUS.get(s, "submitted")
```

- [ ] **Step 5: Run test + lint**

Run: `uv run pytest packages/brokers/tests/test_alpaca_pure.py -v` → PASS (4).
`uvx ruff check packages/brokers/saalr_brokers/alpaca.py packages/brokers/tests/test_alpaca_pure.py`.

- [ ] **Step 6: Commit**

```bash
git add packages/brokers/pyproject.toml packages/brokers/saalr_brokers/alpaca.py packages/brokers/tests/test_alpaca_pure.py
git commit -m "feat(brokers): alpaca optional extra + occ_symbol/map_status helpers"
```

---

## Task 2: `AlpacaAdapter` + stub-client tests + live smoke

**Files:**
- Modify: `packages/brokers/saalr_brokers/alpaca.py` (add `AlpacaAdapter`)
- Test: `packages/brokers/tests/test_alpaca_adapter.py`

- [ ] **Step 1: Write the failing stub-client test (requires the alpaca extra)**

```python
# packages/brokers/tests/test_alpaca_adapter.py
import os
from datetime import date
from decimal import Decimal

import pytest

pytest.importorskip("alpaca")  # the whole file is skipped unless the alpaca extra is installed

from alpaca.trading.requests import (  # noqa: E402
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)

from saalr_brokers.alpaca import AlpacaAdapter  # noqa: E402
from saalr_brokers.types import BrokerOrder  # noqa: E402


class _Order:
    def __init__(self, **kw):
        self.id = kw.get("id", "al-1")
        self.status = kw.get("status", "accepted")
        self.qty = kw.get("qty", "10")
        self.filled_qty = kw.get("filled_qty", "0")
        self.filled_avg_price = kw.get("filled_avg_price")
        self.side = kw.get("side", "buy")
        self.symbol = kw.get("symbol", "AAPL")
        self.client_order_id = kw.get("client_order_id")
        self.rejected_reason = kw.get("rejected_reason")


class _Position:
    symbol, qty, avg_entry_price, market_value, unrealized_pl = "AAPL", "10", "50", "500", "0"


class _Account:
    buying_power = "100000"


class _StubClient:
    def __init__(self, order=None, orders=None):
        self._order = order or _Order()
        self._orders = orders if orders is not None else [self._order]
        self.last_req = None
        self.cancelled = None

    def submit_order(self, req):
        self.last_req = req
        return self._order

    def cancel_order_by_id(self, oid):
        self.cancelled = oid

    def get_orders(self):
        return self._orders

    def get_all_positions(self):
        return [_Position()]

    def get_account(self):
        return _Account()


def _adapter(stub):
    return AlpacaAdapter("k", "s", is_paper=True, client=stub)


def _eq(**kw):
    base = dict(symbol="AAPL", side="buy", qty=10, order_type="market")
    base.update(kw)
    return BrokerOrder(**base)


async def test_submit_market_equity_maps_request_and_idempotency():
    stub = _StubClient(_Order(id="al-9", status="accepted"))
    res = await _adapter(stub).submit_order(_eq(), "idem-1")
    assert isinstance(stub.last_req, MarketOrderRequest)
    assert stub.last_req.symbol == "AAPL" and int(stub.last_req.qty) == 10
    assert stub.last_req.client_order_id == "idem-1"
    assert res.broker_order_id == "al-9" and res.status == "submitted"


async def test_submit_limit_stop_stoplimit_request_types():
    stub = _StubClient()
    a = _adapter(stub)
    await a.submit_order(_eq(order_type="limit", limit_price=Decimal("52")), "k")
    assert isinstance(stub.last_req, LimitOrderRequest) and float(stub.last_req.limit_price) == 52.0
    await a.submit_order(_eq(order_type="stop", stop_price=Decimal("49")), "k2")
    assert isinstance(stub.last_req, StopOrderRequest) and float(stub.last_req.stop_price) == 49.0
    await a.submit_order(_eq(order_type="stop_limit", limit_price=Decimal("52"), stop_price=Decimal("49")), "k3")
    assert isinstance(stub.last_req, StopLimitOrderRequest)


async def test_submit_option_uses_occ_symbol():
    stub = _StubClient()
    await _adapter(stub).submit_order(
        _eq(option_type="CALL", strike=Decimal("100"), expiry=date(2025, 6, 20)), "k"
    )
    assert stub.last_req.symbol == "AAPL250620C00100000"


async def test_rejected_status_maps_to_rejected():
    stub = _StubClient(_Order(status="rejected", rejected_reason="insufficient buying power"))
    res = await _adapter(stub).submit_order(_eq(), "k")
    assert res.status == "rejected" and res.rejected_reason == "insufficient buying power"


async def test_get_orders_normalizes_and_maps_status():
    stub = _StubClient(orders=[_Order(id="al-2", status="filled", filled_qty="10", filled_avg_price="50.25")])
    rows = await _adapter(stub).get_orders()
    assert rows[0]["broker_order_id"] == "al-2" and rows[0]["status"] == "filled"
    assert rows[0]["filled_avg_price"] == Decimal("50.25") and rows[0]["filled_qty"] == 10


async def test_get_positions_and_balance():
    a = _adapter(_StubClient())
    pos = await a.get_positions()
    assert pos[0].symbol == "AAPL" and pos[0].qty == 10 and pos[0].avg_price == Decimal("50")
    assert await a.get_account_balance() == Decimal("100000")


async def test_cancel_and_stream():
    stub = _StubClient()
    a = _adapter(stub)
    assert await a.cancel_order("al-1") is True and stub.cancelled == "al-1"
    with pytest.raises(NotImplementedError):
        async for _ in a.stream_executions():
            pass


@pytest.mark.skipif(
    not (os.environ.get("ALPACA_PAPER_KEY") and os.environ.get("ALPACA_PAPER_SECRET")),
    reason="set ALPACA_PAPER_KEY/ALPACA_PAPER_SECRET to run the live Alpaca paper smoke",
)
async def test_alpaca_paper_live_smoke():
    a = AlpacaAdapter(os.environ["ALPACA_PAPER_KEY"], os.environ["ALPACA_PAPER_SECRET"], is_paper=True)
    bal = await a.get_account_balance()
    assert isinstance(bal, Decimal) and bal >= 0
```

- [ ] **Step 2: Install the extra + run to verify it fails**

Run:
```bash
uv pip install alpaca-py
uv run pytest packages/brokers/tests/test_alpaca_adapter.py -v
```
Expected: FAIL — `ImportError: cannot import name 'AlpacaAdapter'` (the helpers exist; the class doesn't yet). If `uv pip install alpaca-py` is unavailable, `uv add --package saalr-brokers --optional alpaca alpaca-py` then `uv sync --extra alpaca` — report which worked. (Without the extra the file is skipped, which is NOT the failure we want — install it first.)

- [ ] **Step 3: Write the adapter (append to `alpaca.py`)**

```python
# append to packages/brokers/saalr_brokers/alpaca.py
import asyncio  # add to the imports at the top

from .base import BrokerAdapter
from .types import BrokerOrder, BrokerOrderResult, BrokerPosition


class AlpacaAdapter(BrokerAdapter):
    """BrokerAdapter backed by alpaca-py. alpaca is imported lazily (so importing this module
    needs no SDK); the synchronous TradingClient is called via asyncio.to_thread."""

    def __init__(self, api_key: str, api_secret: str, is_paper: bool = True, *, client=None) -> None:
        self._key = api_key
        self._secret = api_secret
        self._is_paper = is_paper
        self._client = client

    def _trading(self):
        if self._client is None:
            try:
                from alpaca.trading.client import TradingClient
            except ImportError as exc:  # pragma: no cover - exercised only without the extra
                raise BrokerError("alpaca-py not installed (pip install alpaca-py)") from exc
            self._client = TradingClient(self._key, self._secret, paper=self._is_paper)
        return self._client

    def _build_request(self, order: BrokerOrder, idempotency_key: str):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
            StopLimitOrderRequest,
            StopOrderRequest,
        )

        symbol = (
            occ_symbol(order.symbol, order.expiry, order.option_type, order.strike)
            if order.option_type
            else order.symbol
        )
        kw = dict(
            symbol=symbol, qty=order.qty, side=OrderSide(order.side),
            time_in_force=TimeInForce(order.time_in_force), client_order_id=idempotency_key,
        )
        t = order.order_type
        if t == "market":
            return MarketOrderRequest(**kw)
        if t == "limit":
            return LimitOrderRequest(limit_price=float(order.limit_price), **kw)
        if t == "stop":
            return StopOrderRequest(stop_price=float(order.stop_price), **kw)
        if t == "stop_limit":
            return StopLimitOrderRequest(
                limit_price=float(order.limit_price), stop_price=float(order.stop_price), **kw
            )
        raise BrokerError(f"unsupported order_type {t!r}")

    async def submit_order(self, order: BrokerOrder, idempotency_key: str) -> BrokerOrderResult:
        req = self._build_request(order, idempotency_key)
        try:
            o = await asyncio.to_thread(self._trading().submit_order, req)
        except BrokerError:
            raise
        except Exception as exc:
            raise BrokerError(str(exc)) from exc
        if map_status(o.status) == "rejected":
            return BrokerOrderResult(str(o.id), "rejected",
                                     getattr(o, "rejected_reason", None) or str(o.status))
        return BrokerOrderResult(str(o.id), "submitted")

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await asyncio.to_thread(self._trading().cancel_order_by_id, broker_order_id)
            return True
        except Exception:
            return False

    async def get_orders(self, since=None) -> list[dict]:
        try:
            orders = await asyncio.to_thread(self._trading().get_orders)
        except Exception as exc:
            raise BrokerError(str(exc)) from exc
        out: list[dict] = []
        for o in orders:
            fap = getattr(o, "filled_avg_price", None)
            out.append({
                "broker_order_id": str(o.id),
                "status": map_status(o.status),
                "symbol": o.symbol,
                "qty": int(o.qty),
                "side": str(getattr(o.side, "value", o.side)),
                "filled_qty": int(o.filled_qty or 0),
                "filled_avg_price": Decimal(str(fap)) if fap else None,
                "client_order_id": getattr(o, "client_order_id", None),
            })
        return out

    async def get_positions(self) -> list[BrokerPosition]:
        try:
            ps = await asyncio.to_thread(self._trading().get_all_positions)
        except Exception as exc:
            raise BrokerError(str(exc)) from exc
        return [
            BrokerPosition(
                symbol=p.symbol, qty=int(p.qty), avg_price=Decimal(str(p.avg_entry_price)),
                market_value=Decimal(str(p.market_value)), unrealized_pnl=Decimal(str(p.unrealized_pl)),
            )
            for p in ps
        ]

    async def get_account_balance(self) -> Decimal:
        try:
            acct = await asyncio.to_thread(self._trading().get_account)
        except Exception as exc:
            raise BrokerError(str(exc)) from exc
        return Decimal(str(acct.buying_power))

    async def stream_executions(self):
        raise NotImplementedError("reconcile via get_orders polling (OMS-3b)")
        yield  # unreachable; makes this an async generator so it satisfies the ABC contract
```

- [ ] **Step 4: Run the stub tests to verify they pass**

Run: `uv run pytest packages/brokers/tests/test_alpaca_adapter.py -v` (with the alpaca extra installed)
Expected: PASS — 7 stub tests; the live smoke SKIPS (no keys). If an attribute mismatch surfaces (e.g. `o.qty` shape, `OrderSide("buy")` casing) against the installed alpaca-py, adjust the conversion in the adapter to match the real SDK and report it — do NOT weaken a test assertion.

- [ ] **Step 5: Lint + commit**

```bash
uvx ruff check packages/brokers/saalr_brokers/alpaca.py packages/brokers/tests/test_alpaca_adapter.py
git add packages/brokers/saalr_brokers/alpaca.py packages/brokers/tests/test_alpaca_adapter.py
git commit -m "feat(brokers): AlpacaAdapter (BrokerOrder->alpaca, status map, asyncio.to_thread)"
```

---

## Task 3: Gate

**Files:** none (verification only).

- [ ] **Step 1: Default gate is alpaca-free**

Run: `uv run pytest packages/brokers/tests packages/core/tests -q`
Expected: green; `test_alpaca_adapter.py` shows as **skipped** if the alpaca extra isn't in the current env (importorskip), and the pure `test_alpaca_pure.py` runs. (If the extra IS installed from Task 2, the stub tests run too — also fine.)

- [ ] **Step 2: Lint**

Run: `uvx ruff check packages/brokers/saalr_brokers`
Expected: clean (the unreachable `yield` after `raise` in `stream_executions` is intentional — if ruff flags it, add a `# noqa` for that line and report the code).

- [ ] **Step 3: Confirm import-without-extra**

Run: `uv run python -c "import saalr_brokers.alpaca; print('import ok without instantiating')"`
Expected: `import ok` — the module imports with no alpaca-py installed (all `alpaca.*` imports are inside methods).

- [ ] **Step 4: Final commit (if anything was adjusted)**

```bash
git add -A
git commit -m "chore(brokers): Alpaca adapter OMS-3a — suite + lint green"
```

---

## Self-review notes (addressed)

- **Spec coverage:** optional extra + pure helpers (T1), the adapter mapping incl. OCC symbols + `client_order_id` + status map + sync-in-async + deferred stream (T2), gate incl. import-without-extra (T3).
- **Isolation:** all `alpaca.*` imports are inside methods → `import saalr_brokers.alpaca` works without the SDK; the default gate skips the stub tests via `importorskip`. Only Task 2 installs the extra to prove the mapping.
- **Sync SDK:** every `TradingClient` call is wrapped in `await asyncio.to_thread(...)`; the stub client is plain-synchronous so it works the same way.
- **Type/units consistency:** `Decimal(str(x))` at the boundary; `qty`/`filled_qty` → `int`; `OrderSide`/`TimeInForce` value-constructed from our lowercase strings; option `symbol` via `occ_symbol`; `client_order_id == idempotency_key`. `stream_executions` is an async generator that raises (matches the ABC, tested).
- **No service changes:** OMS-3a adds nothing to `place_order`/the API/DB (the service still 400s non-paper — that wiring is OMS-3b).
