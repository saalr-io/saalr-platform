# Market-data ingestion (daily bars) — design

**Date:** 2026-05-30
**Slice:** LLD §13 step 5 — "Market data ingestion (Massive for US) → Postgres. End-to-end data pipeline runs." First cut: **daily underlying bars (OHLCV)** for a DB-managed instrument universe.
**Status:** Approved design, pre-plan.
**Builds on:** the Massive adapter + HTTP pattern from the Greeks/vol-surface slice; the `bars` TimescaleDB hypertable; the (currently empty) `ingest-worker` app.

## Purpose

Build the scheduled batch pipeline that accumulates **historical and ongoing daily price
history** for a universe of US underlyings into the `bars` hypertable. This is the foundation
the backtest engine (§13.8) and other quantitative features need. (Option-chain history already
accrues via the Greeks slice's on-demand persistence; scheduled chain snapshots are a later slice.)

## Decisions (locked during brainstorming)

1. **Daily bars (OHLCV) first.** Intraday bars and scheduled option-chain snapshots are deferred.
2. **CLI worker + a DB `instruments` table.** The universe is rows in a new `instruments` table
   (add/enable at runtime), not static config. The worker is a standalone CLI; real scheduling
   (cron/ECS) is external/later.
3. **Real Massive aggregates** (stocks access confirmed). Adapter built against the documented
   `/v2/aggs` endpoint; offline tests use recorded fixtures; a live smoke test (env-gated) pulls
   real bars.
4. **Structure:** adapter in `saalr_core/marketdata/` (shared); orchestration/CLI in `ingest-worker`.

## Architecture

```
packages/core/saalr_core/
  marketdata/aggregates.py          # parse_aggregates (pure) + MassiveAggregatesProvider
  db/models/market_data.py          # ADD Instrument model (Bar exists)
infra/migrations/versions/0003_instruments.py   # NEW: instruments table + saalr_app grants
apps/ingest-worker/
  pyproject.toml                    # ADD dep: saalr-core (workspace)
  ingest_worker/
    __init__.py  __main__.py
    repo.py                         # instruments CRUD + idempotent bars upsert + latest_bar_ts
    service.py                      # backfill_symbol() + run_incremental()
    cli.py                          # argparse: add-instrument / list-instruments / backfill / run
  tests/                            # (integration lives under repo-root tests/integration)
packages/core/tests/test_aggregates.py
tests/integration/test_ingest.py
tests/integration/test_market_smoke.py            # ADD a bars live-smoke test
```

### Data model: `instruments` (shared market data, NO RLS — like `bars`)
| column | type | notes |
|---|---|---|
| symbol | TEXT | PK part |
| market | CHAR(2) | PK part; 'US' |
| name | TEXT NULL | display name |
| is_active | BOOLEAN NOT NULL DEFAULT true | only active symbols are ingested by `run` |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |

PK `(symbol, market)`. Migration `0003_instruments` creates the table and `GRANT SELECT, INSERT,
UPDATE ON instruments TO saalr_app`, since the worker connects as the non-superuser `saalr_app`
role. The migration also issues `GRANT SELECT, INSERT, UPDATE ON bars TO saalr_app` defensively
(idempotent — the Greeks slice already writes `options_chain_snapshots` as `saalr_app`, so `bars`
from the same baseline grant block is almost certainly already granted; the redundant GRANT just
guarantees the worker can write). The migration's first action is a quick check/assert via a
plain `GRANT` (no-op if already held). `instruments` is NOT tenant-scoped (no RLS policy).

### Worker DB access
The worker is a standalone process using `saalr_core.config.Settings` and the core async session
factory (`create_engine`/`create_sessionmaker`), connecting as `saalr_app` to the non-RLS
market-data tables (`bars`, `instruments`). No `app.current_tenant` GUC is set — these are global
shared data. Config additions: none required beyond the existing `app_database_url` +
`massive_api_key` (a `bars_backfill_default_days` setting with a sensible default is added for the
empty-history incremental case).

## Components

### `saalr_core/marketdata/aggregates.py`
- **`BarRow`** (frozen dataclass): `ts: datetime, symbol: str, market: str, interval: str, open,
  high, low, close: float, volume: int`.
- **`parse_aggregates(results: list[dict], symbol: str, market: str) -> list[BarRow]`** — PURE.
  Maps Massive daily-aggregate rows (`t` = ms-epoch bar start, `o/h/l/c`, `v`) to `BarRow`s with
  `interval='1d'` and `ts = datetime.fromtimestamp(t/1000, tz=UTC)`. Vendor JSON stops here.
- **`MassiveAggregatesProvider.get_daily_bars(symbol, start: date, end: date) -> list[BarRow]`** —
  `GET {base}/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}?adjusted=true&limit=50000`,
  paginated via `next_url`, reusing the throttle + retry + `ProviderError` pattern from
  `massive.py` (`_RETRYABLE`, fail-fast on non-retryable 4xx). Auth via `massive_api_key`.

### `apps/ingest-worker/ingest_worker/repo.py`
- `add_instrument(session, symbol, market, name=None)` — `INSERT … ON CONFLICT (symbol, market)
  DO UPDATE SET name=…, is_active=true`.
- `list_active_instruments(session, market=None) -> list[Instrument]`.
- `latest_bar_ts(session, symbol, market, interval) -> datetime | None` — `max(ts)`.
- `upsert_bars(session, rows: list[BarRow])` — bulk `INSERT … ON CONFLICT (symbol, market,
  interval, ts) DO UPDATE SET open/high/low/close/volume`. Binds `Decimal(str(x))` for the NUMERIC
  columns and the `datetime` `ts` directly (asyncpg is strict — never pass float/str).

### `apps/ingest-worker/ingest_worker/service.py`
- `backfill_symbol(session, provider, symbol, market, start, end) -> int` — fetch → parse →
  `upsert_bars`; returns the row count.
- `run_incremental(session, provider, default_days) -> dict[str,int]` — for each active
  instrument: `start = (latest_bar_ts + 1 day)` or `today - default_days` when empty; `end =
  today`; fetch + upsert; returns a per-symbol count map. Idempotent (overlap re-upserts).

### `apps/ingest-worker/ingest_worker/cli.py` + `__main__.py`
`argparse` subcommands (each opens a session from `Settings`, builds
`MassiveAggregatesProvider(settings.massive_api_key)`, runs the async op via `asyncio.run`, prints
a one-line summary):
- `add-instrument SYMBOL [--market US] [--name NAME]`
- `list-instruments [--market US]`
- `backfill --start YYYY-MM-DD --end YYYY-MM-DD [--symbol SYMBOL]` (all active if no `--symbol`)
- `run` (incremental for all active instruments)

## Data flow
1. Operator: `python -m ingest_worker add-instrument AAPL --name Apple` → row in `instruments`.
2. `backfill --start 2020-01-01 --end 2025-12-31` → daily bars for the range upserted into `bars`.
3. Scheduled (external) `run` → appends new daily bars since each symbol's latest stored `ts`.
4. Backtest (§13.8) and other features read `bars`.

## Error handling
- Massive unreachable after retries → `ProviderError`; the CLI catches it, logs the symbol, and
  continues to the next instrument (one bad symbol doesn't abort a batch); exit code reflects
  whether any symbol failed.
- A symbol Massive doesn't recognise → empty results → 0 bars upserted, logged; not fatal.
- Idempotent upsert means a re-run after a partial failure is safe.
- 403/entitlement on live calls (if stocks access lapses) → `ProviderError`, surfaced clearly.

## Testing
- **Pure** (`packages/core/tests/test_aggregates.py`): `parse_aggregates` against a recorded
  Massive aggregates fixture — ms-epoch → tz-aware UTC `ts`, OHLCV mapped, `interval='1d'`;
  handles an empty `results` list.
- **Integration** (`tests/integration/test_ingest.py`, Postgres 55432, truncates
  `bars`/`instruments` itself): `add_instrument` idempotency + `list_active_instruments`;
  **bars upsert idempotency** (upsert the same rows twice → no PK duplication, values updated);
  `backfill_symbol` and `run_incremental` via a **stub aggregates provider** (bars land;
  incremental starts from `latest_bar_ts` and appends without duplication).
- **Migration**: assert the `instruments` table exists and `saalr_app` can insert/select it
  (the new migration applied by the existing alembic session fixture). Schema-vs-models test picks
  up the `Instrument` model.
- **Live smoke** (env-gated, in `tests/integration/test_market_smoke.py`): real
  `MassiveAggregatesProvider.get_daily_bars("AAPL", <recent 5-day range>)` returns ≥1 bar with
  positive OHLCV; `skipif` on missing key / `RUN_LIVE_SMOKE`.
- **Gate**: `uv run pytest` (core + integration on the 55432 DB env) + `uvx ruff check`.

## Out of scope
- Intraday bars (1m/5m/1h), scheduled option-chain snapshots, India/Bhavcopy ingestion.
- Real scheduling/orchestration (cron/ECS task definitions) — the worker is a CLI; wiring a
  schedule is an infra task. (The user's PowerShell build-orchestrator is for dev builds, not the
  data scheduler.)
- Corporate-action/split reconciliation beyond Massive's `adjusted=true` (the endpoint returns
  split/dividend-adjusted daily bars).
- Data-freshness alerting, `data_usage` license attribution, continuous aggregates/downsampling.
- A management UI for instruments (CLI only this slice).
