# Market-Data Ingestion (daily bars) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI worker that ingests daily OHLCV bars from Massive aggregates into the `bars` TimescaleDB hypertable for a DB-managed `instruments` universe — backfill + idempotent incremental.

**Architecture:** Pure Massive aggregates adapter in `saalr_core/marketdata/aggregates.py` (reused HTTP/retry pattern); a new non-RLS `instruments` table (migration `0003`); orchestration + CLI in the `ingest-worker` app, writing as the `saalr_app` role. Idempotent upserts make re-runs safe.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async (asyncpg), Alembic, httpx, argparse, pytest.

**Spec:** `docs/superpowers/specs/2026-05-30-market-data-ingestion-design.md`

**Integration tests need Docker Postgres on host 55432** (native PG shadows 5432/5433). Run them with:
`ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest <path> -q`

## File structure

```
packages/core/saalr_core/db/models/market_data.py   # ADD Instrument
packages/core/saalr_core/config.py                  # ADD bars_backfill_default_days
infra/migrations/versions/0003_instruments.py       # NEW
packages/core/saalr_core/marketdata/aggregates.py   # NEW: parse_aggregates + MassiveAggregatesProvider
packages/core/tests/test_aggregates.py              # NEW
packages/core/tests/fixtures/massive_aggs.json      # NEW
apps/ingest-worker/pyproject.toml                   # MODIFY: deps + wheel target
apps/ingest-worker/ingest_worker/__init__.py        # NEW (empty)
apps/ingest-worker/ingest_worker/__main__.py        # NEW
apps/ingest-worker/ingest_worker/repo.py            # NEW
apps/ingest-worker/ingest_worker/service.py         # NEW
apps/ingest-worker/ingest_worker/cli.py             # NEW
tests/integration/test_ingest.py                    # NEW
tests/integration/test_market_smoke.py              # MODIFY: add a bars live smoke
```

---

## Task 1: Instrument model + migration + config

**Files:**
- Modify: `packages/core/saalr_core/db/models/market_data.py`
- Modify: `packages/core/saalr_core/config.py`
- Create: `infra/migrations/versions/0003_instruments.py`
- Test: `tests/integration/test_ingest.py` (first test only)

- [ ] **Step 1: Add the Instrument model**

In `packages/core/saalr_core/db/models/market_data.py`, update the sqlalchemy import line to add `Boolean`, `func`, `text`, then append the model. The current import line is:
`from sqlalchemy import CHAR, BigInteger, Date, Numeric, Text` → change to
`from sqlalchemy import CHAR, BigInteger, Boolean, Date, Numeric, Text, func, text`.
Append at the end of the file:

```python
class Instrument(Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    market: Mapped[str] = mapped_column(CHAR(2), primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Add the config setting**

In `packages/core/saalr_core/config.py`, add to `Settings` (after `vol_surface_cache_ttl_seconds`):

```python
    # Market-data ingestion
    bars_backfill_default_days: int = 1825  # ~5y, used when a symbol has no stored bars
```

- [ ] **Step 3: Create the migration**

Create `infra/migrations/versions/0003_instruments.py`:

```python
"""instruments table for market-data ingestion

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-30
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE instruments (
          symbol      TEXT NOT NULL,
          market      CHAR(2) NOT NULL,
          name        TEXT,
          is_active   BOOLEAN NOT NULL DEFAULT true,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (symbol, market)
        );

        -- The ingest worker connects as the non-superuser saalr_app role.
        GRANT SELECT, INSERT, UPDATE ON instruments TO saalr_app;
        -- Defensive (idempotent): ensure the worker can write bars too.
        GRANT SELECT, INSERT, UPDATE ON bars TO saalr_app;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS instruments;")
```

- [ ] **Step 4: Write a migration/schema test**

Create `tests/integration/test_ingest.py` with this first test (self-contained — later tasks
prepend the `datetime`/`repo`/`service`/`BarRow` imports they need):

```python
from sqlalchemy import text


async def test_instruments_table_exists_and_writable(app_sessionmaker):
    async with app_sessionmaker() as s:
        async with s.begin():
            await s.execute(text("TRUNCATE instruments"))
            await s.execute(
                text("INSERT INTO instruments (symbol, market, name) VALUES ('AAPL','US','Apple')")
            )
        async with s.begin():
            n = (await s.execute(text("SELECT count(*) FROM instruments WHERE symbol='AAPL'"))).scalar_one()
    assert n == 1
```

- [ ] **Step 5: Apply migration + run the test**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_ingest.py::test_instruments_table_exists_and_writable tests/integration/test_schema_matches_models.py -q`
Expected: passes (the autouse `_migrate` fixture applies `0003`; `test_all_model_columns_match_db` confirms the `Instrument` model matches the table).

> If `instruments` columns don't match the model, reconcile the migration DDL with the model (names/types/defaults) until `test_all_model_columns_match_db` passes.

- [ ] **Step 6: Commit**

```bash
git add packages/core/saalr_core/db/models/market_data.py packages/core/saalr_core/config.py infra/migrations/versions/0003_instruments.py
git commit -m "feat(ingest): instruments table + model + backfill-days config"
```

---

## Task 2: Massive aggregates adapter

**Files:**
- Create: `packages/core/saalr_core/marketdata/aggregates.py`
- Create: `packages/core/tests/fixtures/massive_aggs.json`
- Test: `packages/core/tests/test_aggregates.py`

- [ ] **Step 1: Create the fixture**

Create `packages/core/tests/fixtures/massive_aggs.json`:

```json
{
  "ticker": "AAPL",
  "results": [
    {"t": 1735603200000, "o": 250.0, "h": 255.5, "l": 249.2, "c": 254.1, "v": 41000000},
    {"t": 1735689600000, "o": 254.0, "h": 256.0, "l": 252.0, "c": 252.8, "v": 38500000}
  ],
  "next_url": null
}
```

- [ ] **Step 2: Write the failing test**

Create `packages/core/tests/test_aggregates.py`:

```python
import json
import pathlib
from datetime import datetime, timezone

from saalr_core.marketdata.aggregates import parse_aggregates

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_parse_aggregates_maps_bars():
    data = json.loads((FIX / "massive_aggs.json").read_text())
    rows = parse_aggregates(data["results"], "AAPL", "US")
    assert len(rows) == 2
    r = rows[0]
    assert r.symbol == "AAPL" and r.market == "US" and r.interval == "1d"
    assert r.ts == datetime(2024, 12, 31, 0, 0, tzinfo=timezone.utc)
    assert r.open == 250.0 and r.high == 255.5 and r.low == 249.2 and r.close == 254.1
    assert r.volume == 41000000


def test_parse_aggregates_empty():
    assert parse_aggregates([], "AAPL", "US") == []
```

- [ ] **Step 3: Run to verify fail**

Run: `cd packages/core && uv run pytest tests/test_aggregates.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 4: Implement aggregates.py**

Create `packages/core/saalr_core/marketdata/aggregates.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from .provider import ProviderError

_BASE = "https://api.massive.com"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class BarRow:
    ts: datetime
    symbol: str
    market: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: int


def parse_aggregates(results: list[dict], symbol: str, market: str) -> list[BarRow]:
    """Pure: map Massive daily-aggregate rows into BarRow (vendor JSON stops here)."""
    out: list[BarRow] = []
    for r in results:
        out.append(
            BarRow(
                ts=datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc),
                symbol=symbol,
                market=market,
                interval="1d",
                open=float(r["o"]),
                high=float(r["h"]),
                low=float(r["l"]),
                close=float(r["c"]),
                volume=int(r.get("v", 0)),
            )
        )
    return out


class MassiveAggregatesProvider:
    def __init__(self, api_key: str | None, *, base_url: str = _BASE) -> None:
        self._api_key = api_key
        self._base = base_url

    async def _get(self, client: httpx.AsyncClient, url: str, params: dict) -> dict:
        for attempt in range(3):
            try:
                r = await client.get(url, params=params)
                if r.status_code in _RETRYABLE:
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    raise ProviderError(f"massive returned {r.status_code} after retries")
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as exc:
                raise ProviderError(str(exc)) from exc
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ProviderError(str(exc)) from exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ProviderError("exhausted retries")

    async def get_daily_bars(self, symbol: str, start: date, end: date, market: str = "US") -> list[BarRow]:
        if not self._api_key:
            raise ProviderError("no massive api key configured")
        rows: list[BarRow] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self._base}/v2/aggs/ticker/{symbol}/range/1/day/{start.isoformat()}/{end.isoformat()}"
            params: dict = {"apiKey": self._api_key, "adjusted": "true", "limit": 50000}
            while url:
                data = await self._get(client, url, params)
                rows.extend(parse_aggregates(data.get("results", []) or [], symbol, market))
                url = data.get("next_url")
                params = {"apiKey": self._api_key}  # next_url carries the rest
        return rows
```

- [ ] **Step 5: Run to verify pass + lint**

Run: `cd packages/core && uv run pytest tests/test_aggregates.py -q`
Expected: 2 passed.
Run: `cd ../.. && uvx ruff check packages/core/saalr_core/marketdata/aggregates.py packages/core/tests/test_aggregates.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add packages/core/saalr_core/marketdata/aggregates.py packages/core/tests/test_aggregates.py packages/core/tests/fixtures/massive_aggs.json
git commit -m "feat(marketdata): Massive daily-aggregates adapter + pure parse"
```

---

## Task 3: ingest-worker package + repo

**Files:**
- Modify: `apps/ingest-worker/pyproject.toml`
- Create: `apps/ingest-worker/ingest_worker/__init__.py` (empty)
- Create: `apps/ingest-worker/ingest_worker/repo.py`

- [ ] **Step 1: Wire the package**

Replace `apps/ingest-worker/pyproject.toml` with:

```toml
[project]
name = "saalr-ingest-worker"
version = "0.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "saalr-core",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["ingest_worker"]

[tool.uv.sources]
saalr-core = { workspace = true }
```

Create empty `apps/ingest-worker/ingest_worker/__init__.py`:

```python
```

- [ ] **Step 2: Implement repo.py**

Create `apps/ingest-worker/ingest_worker/repo.py`:

```python
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.models.market_data import Bar, Instrument
from saalr_core.marketdata.aggregates import BarRow

_ADD_INSTRUMENT = text(
    """
    INSERT INTO instruments (symbol, market, name, is_active)
    VALUES (:symbol, :market, :name, true)
    ON CONFLICT (symbol, market) DO UPDATE SET name = EXCLUDED.name, is_active = true
    """
)

_UPSERT_BARS = text(
    """
    INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
    VALUES (:ts, :symbol, :market, :interval, :open, :high, :low, :close, :volume)
    ON CONFLICT (symbol, market, interval, ts) DO UPDATE SET
      open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
      close = EXCLUDED.close, volume = EXCLUDED.volume
    """
)


async def add_instrument(session: AsyncSession, symbol: str, market: str = "US", name: str | None = None) -> None:
    await session.execute(_ADD_INSTRUMENT, {"symbol": symbol, "market": market, "name": name})


async def list_active_instruments(session: AsyncSession, market: str | None = None) -> list[Instrument]:
    stmt = select(Instrument).where(Instrument.is_active.is_(True))
    if market is not None:
        stmt = stmt.where(Instrument.market == market)
    stmt = stmt.order_by(Instrument.symbol)
    return list((await session.execute(stmt)).scalars().all())


async def latest_bar_ts(session: AsyncSession, symbol: str, market: str, interval: str) -> datetime | None:
    return (
        await session.execute(
            select(func.max(Bar.ts)).where(
                Bar.symbol == symbol, Bar.market == market, Bar.interval == interval
            )
        )
    ).scalar_one_or_none()


async def upsert_bars(session: AsyncSession, rows: list[BarRow]) -> int:
    if not rows:
        return 0
    params = [
        {
            "ts": r.ts, "symbol": r.symbol, "market": r.market, "interval": r.interval,
            "open": Decimal(str(r.open)), "high": Decimal(str(r.high)),
            "low": Decimal(str(r.low)), "close": Decimal(str(r.close)), "volume": r.volume,
        }
        for r in rows
    ]
    await session.execute(_UPSERT_BARS, params)
    return len(rows)
```

- [ ] **Step 3: Sync + verify import**

Run: `uv sync`
Run: `uv run python -c "from ingest_worker.repo import add_instrument, upsert_bars, latest_bar_ts, list_active_instruments; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add apps/ingest-worker/pyproject.toml apps/ingest-worker/ingest_worker/__init__.py apps/ingest-worker/ingest_worker/repo.py uv.lock
git commit -m "feat(ingest): worker package + instruments/bars repository"
```

---

## Task 4: Ingest service

**Files:**
- Create: `apps/ingest-worker/ingest_worker/service.py`

- [ ] **Step 1: Implement service.py**

Create `apps/ingest-worker/ingest_worker/service.py`:

```python
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from .repo import latest_bar_ts, list_active_instruments, upsert_bars


async def backfill_symbol(session: AsyncSession, provider, symbol: str, market: str,
                          start: date, end: date) -> int:
    rows = await provider.get_daily_bars(symbol, start, end, market)
    return await upsert_bars(session, rows)


async def run_incremental(session: AsyncSession, provider, default_days: int,
                          today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    counts: dict[str, int] = {}
    for inst in await list_active_instruments(session):
        last = await latest_bar_ts(session, inst.symbol, inst.market, "1d")
        start = (last.date() + timedelta(days=1)) if last else (today - timedelta(days=default_days))
        if start > today:
            counts[inst.symbol] = 0
            continue
        rows = await provider.get_daily_bars(inst.symbol, start, today, inst.market)
        counts[inst.symbol] = await upsert_bars(session, rows)
    return counts
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from ingest_worker.service import backfill_symbol, run_incremental; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps/ingest-worker/ingest_worker/service.py
git commit -m "feat(ingest): backfill + idempotent incremental service"
```

---

## Task 5: Integration tests

**Files:**
- Modify: `tests/integration/test_ingest.py` (add the rest)

- [ ] **Step 1: Append the integration tests**

First, add these imports at the TOP of `tests/integration/test_ingest.py` (above the existing
`from sqlalchemy import text`):

```python
from datetime import date, datetime, timedelta, timezone

from ingest_worker import repo, service
from saalr_core.marketdata.aggregates import BarRow
```

Then append the tests below (note: `text`, `repo`, `service`, `BarRow`, `datetime`, `timezone`,
`date`, `timedelta` are now all imported at the top — do not re-import inside):

```python


def _bar(ts, symbol="AAPL", market="US", close=100.0):
    return BarRow(ts=ts, symbol=symbol, market=market, interval="1d",
                  open=close - 1, high=close + 1, low=close - 2, close=close, volume=1000)


class StubAggs:
    """Returns one daily bar per calendar day in [start, end]."""
    def __init__(self):
        self.calls = []

    async def get_daily_bars(self, symbol, start, end, market="US"):
        self.calls.append((symbol, start, end))
        out, d = [], start
        while d <= end:
            ts = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            out.append(_bar(ts, symbol, market, close=100.0 + d.day))
            d += timedelta(days=1)
        return out


async def test_add_instrument_idempotent(app_sessionmaker):
    async with app_sessionmaker() as s:
        async with s.begin():
            await s.execute(text("TRUNCATE instruments"))
            await repo.add_instrument(s, "MSFT", "US", "Microsoft")
            await repo.add_instrument(s, "MSFT", "US", "Microsoft Corp")  # second add = update
        async with s.begin():
            active = await repo.list_active_instruments(s)
    assert [(i.symbol, i.name) for i in active] == [("MSFT", "Microsoft Corp")]


async def test_bars_upsert_is_idempotent(app_sessionmaker):
    ts = datetime(2025, 1, 2, tzinfo=timezone.utc)
    async with app_sessionmaker() as s:
        async with s.begin():
            await s.execute(text("TRUNCATE bars"))
            await repo.upsert_bars(s, [_bar(ts, close=101.0)])
            await repo.upsert_bars(s, [_bar(ts, close=102.0)])  # same PK -> update
        async with s.begin():
            n = (await s.execute(text("SELECT count(*) FROM bars WHERE symbol='AAPL'"))).scalar_one()
            c = (await s.execute(text("SELECT close FROM bars WHERE symbol='AAPL'"))).scalar_one()
    assert n == 1 and float(c) == 102.0


async def test_backfill_then_incremental_appends(app_sessionmaker):
    stub = StubAggs()
    async with app_sessionmaker() as s:
        async with s.begin():
            await s.execute(text("TRUNCATE bars"))
            await s.execute(text("TRUNCATE instruments"))
            await repo.add_instrument(s, "AAPL", "US", "Apple")
            await service.backfill_symbol(s, stub, "AAPL", "US", date(2025, 1, 1), date(2025, 1, 3))
        async with s.begin():
            n1 = (await s.execute(text("SELECT count(*) FROM bars WHERE symbol='AAPL'"))).scalar_one()
        # incremental from the latest stored ts (2025-01-03) up to a fixed "today"
        async with s.begin():
            counts = await service.run_incremental(s, stub, default_days=30, today=date(2025, 1, 6))
        async with s.begin():
            n2 = (await s.execute(text("SELECT count(*) FROM bars WHERE symbol='AAPL'"))).scalar_one()
    assert n1 == 3                 # 2025-01-01..03
    assert counts["AAPL"] == 3     # 2025-01-04..06 (start = last+1day)
    assert n2 == 6                 # no duplication
```

- [ ] **Step 2: Run the integration tests**

Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_ingest.py -q`
Expected: 4 passed (the Task-1 test + these 3).

> Note: ensure the top-of-file imports in `test_ingest.py` are present: `from datetime import datetime, timezone`, `from sqlalchemy import text`, `from ingest_worker import repo, service`, `from saalr_core.marketdata.aggregates import BarRow`, plus the `from datetime import date, timedelta` added here. Consolidate duplicate datetime imports.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_ingest.py
git commit -m "test(ingest): instruments CRUD, bars upsert idempotency, backfill+incremental"
```

---

## Task 6: CLI

**Files:**
- Create: `apps/ingest-worker/ingest_worker/cli.py`
- Create: `apps/ingest-worker/ingest_worker/__main__.py`

- [ ] **Step 1: Implement cli.py**

Create `apps/ingest-worker/ingest_worker/cli.py`:

```python
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker
from saalr_core.marketdata.aggregates import MassiveAggregatesProvider
from saalr_core.marketdata.provider import ProviderError

from . import repo, service


async def _with_session(fn: Callable[[AsyncSession, object], Awaitable[None]]) -> None:
    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    try:
        sm = create_sessionmaker(engine)
        async with sm() as session:
            async with session.begin():
                await fn(session, settings)
    finally:
        await engine.dispose()


def _provider(settings) -> MassiveAggregatesProvider:
    return MassiveAggregatesProvider(settings.massive_api_key)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ingest_worker", description="Saalr market-data ingestion")
    sub = p.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add-instrument", help="add or re-activate a symbol")
    add.add_argument("symbol")
    add.add_argument("--market", default="US")
    add.add_argument("--name", default=None)

    lst = sub.add_parser("list-instruments", help="list active instruments")
    lst.add_argument("--market", default=None)

    bf = sub.add_parser("backfill", help="backfill daily bars for a date range")
    bf.add_argument("--start", required=True)
    bf.add_argument("--end", required=True)
    bf.add_argument("--symbol", default=None)
    bf.add_argument("--market", default="US")

    sub.add_parser("run", help="incremental: append new daily bars for all active instruments")
    return p


async def _cmd_add(args, session, settings) -> None:
    await repo.add_instrument(session, args.symbol.upper(), args.market, args.name)
    print(f"added {args.symbol.upper()} ({args.market})")


async def _cmd_list(args, session, settings) -> None:
    rows = await repo.list_active_instruments(session, args.market)
    for i in rows:
        print(f"{i.symbol}\t{i.market}\t{i.name or ''}")
    print(f"{len(rows)} active")


async def _cmd_backfill(args, session, settings) -> None:
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    provider = _provider(settings)
    symbols = (
        [(args.symbol.upper(), args.market)]
        if args.symbol
        else [(i.symbol, i.market) for i in await repo.list_active_instruments(session)]
    )
    for sym, mkt in symbols:
        try:
            n = await service.backfill_symbol(session, provider, sym, mkt, start, end)
            print(f"{sym}: {n} bars")
        except ProviderError as exc:
            print(f"{sym}: FAILED {exc}")


async def _cmd_run(args, session, settings) -> None:
    provider = _provider(settings)
    counts = await service.run_incremental(session, provider, settings.bars_backfill_default_days)
    for sym, n in counts.items():
        print(f"{sym}: +{n} bars")


_DISPATCH = {
    "add-instrument": _cmd_add,
    "list-instruments": _cmd_list,
    "backfill": _cmd_backfill,
    "run": _cmd_run,
}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handler = _DISPATCH[args.cmd]
    asyncio.run(_with_session(lambda session, settings: handler(args, session, settings)))
```

Create `apps/ingest-worker/ingest_worker/__main__.py`:

```python
from .cli import main

main()
```

- [ ] **Step 2: Verify the parser (no DB needed)**

Run: `uv run python -c "from ingest_worker.cli import build_parser; build_parser().parse_args(['backfill','--start','2025-01-01','--end','2025-01-31','--symbol','AAPL']); build_parser().parse_args(['run']); print('ok')"`
Expected: `ok`
Run: `uv run python -m ingest_worker --help`
Expected: prints usage with the four subcommands (exit 0).

- [ ] **Step 3: Lint**

Run: `uvx ruff check apps/ingest-worker/ingest_worker`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/ingest-worker/ingest_worker/cli.py apps/ingest-worker/ingest_worker/__main__.py
git commit -m "feat(ingest): CLI (add-instrument/list-instruments/backfill/run)"
```

---

## Task 7: Live smoke + full gate

**Files:**
- Modify: `tests/integration/test_market_smoke.py`

- [ ] **Step 1: Add a bars live smoke test**

Append to `tests/integration/test_market_smoke.py`:

```python
from datetime import date, timedelta

from saalr_core.marketdata.aggregates import MassiveAggregatesProvider


@pytest.mark.skipif(not _settings.massive_api_key, reason="no MASSIVE_API_KEY")
async def test_massive_live_daily_bars():
    end = date.today()
    start = end - timedelta(days=7)
    bars = await MassiveAggregatesProvider(_settings.massive_api_key).get_daily_bars("AAPL", start, end)
    assert len(bars) >= 1
    assert bars[0].close > 0 and bars[0].volume > 0
```

(The file already imports `os`, `pytest`, `_settings = get_settings()`, and has the module-level
`pytestmark = pytest.mark.skipif(not os.environ.get("RUN_LIVE_SMOKE"), ...)`. Reuse them — only add
the import lines and the test above.)

- [ ] **Step 2: Confirm it skips without the flag**

Run: `uv run pytest tests/integration/test_market_smoke.py -q`
Expected: skipped (3 skipped now).

- [ ] **Step 3: (Manual, local) live run**

Run (PowerShell): `$env:RUN_LIVE_SMOKE=1; uv run pytest tests/integration/test_market_smoke.py::test_massive_live_daily_bars -q`
Expected: 1 passed (real AAPL daily bars; requires `MASSIVE_API_KEY` with stocks-aggregates access).

- [ ] **Step 4: Full gate**

Run: `cd packages/core && uv run pytest -q && cd ../..`
Expected: core suite green (incl. `test_aggregates`).
Run: `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest -q`
Expected: all green (live smoke skipped).
Run: `uvx ruff check packages/core/saalr_core apps/ingest-worker/ingest_worker tests`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_market_smoke.py
git commit -m "test(ingest): env-gated live daily-bars smoke + full gate green"
```

---

## Self-review checklist (completed)

- **Spec coverage:** Instrument table + migration + grants (T1), config default-days (T1), aggregates adapter parse+fetch (T2), repo instruments/bars/latest_ts/upsert (T3), backfill + incremental service (T4), integration: instruments CRUD + bars idempotency + backfill/incremental (T5 + T1 writable test), CLI 4 subcommands (T6), live smoke (T7), gate (T7). All spec sections covered.
- **Placeholder scan:** none — every step has complete code. The one cross-task note (test_ingest.py imports needed before Task 5) is explicit, not a placeholder.
- **Type consistency:** `BarRow` (ts/symbol/market/interval/open/high/low/close/volume), `Instrument`, `MassiveAggregatesProvider.get_daily_bars(symbol, start, end, market='US')`, `parse_aggregates(results, symbol, market)`, `repo.{add_instrument,list_active_instruments,latest_bar_ts,upsert_bars}`, `service.{backfill_symbol,run_incremental}` are used consistently across tasks. The stub provider in T5 matches the real provider's `get_daily_bars` signature.

## Known risks / notes

- **`bars`/`instruments` are non-RLS shared tables;** the worker writes as `saalr_app` (granted in `0003`). No tenant GUC. The integration tests use `app_sessionmaker` (the `saalr_app` role) and `TRUNCATE` these tables themselves (they're not in the conftest tenant-truncate list).
- **asyncpg strictness:** `upsert_bars` binds `Decimal` for NUMERIC and `datetime` for the TIMESTAMPTZ `ts` (the lesson from the Greeks-slice persistence bug). Don't pass float/str.
- **`run_incremental` accepts an injectable `today`** so the integration test is deterministic; production passes none (uses `date.today()`).
- **Stocks-aggregates entitlement:** offline tests never hit the network; the live smoke `skipif`s on the key and `RUN_LIVE_SMOKE`. A 403 (no stocks access) surfaces as `ProviderError` in the CLI, per-symbol, without aborting the batch.
```
