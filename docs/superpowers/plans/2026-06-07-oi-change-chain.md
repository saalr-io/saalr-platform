# Change in OI (ΔOI) Chain Column Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-strike **Chg OI** column to the option chain with a Day/1h/3h/4h window toggle and a DTE label, computing ΔOI against the nearest earlier `options_chain_snapshots` row and labelling the real elapsed time.

**Architecture:** The chain endpoint already returns the current chain (with absolute OI) and persists each fetch as a timestamped snapshot. We add a pure baseline-picker (`oi_change.py`), a small repo query that loads OI history for an underlying, and enrich `MarketService.chain(...)` so each contract carries `oi_change: {day,1h,3h,4h}` and the response carries `oi_baselines`. The frontend `ChainTable` gains a local window toggle + a colored Chg OI column + a baseline note; `Markets.tsx` shows the DTE.

**Tech Stack:** FastAPI, SQLAlchemy async (raw `text()` over the shared `options_chain_snapshots`), React + react-router, Vitest, pytest.

**Spec:** [docs/superpowers/specs/2026-06-07-oi-change-chain-design.md](../specs/2026-06-07-oi-change-chain-design.md)

---

## File Structure

**Backend**
- Create `apps/api/saalr_api/market/oi_change.py` — pure: `WINDOWS`, `pick_baseline_ts`, `elapsed_label`.
- Create `packages/core/tests/test_oi_change.py` — pure unit tests (no DB; imports from `saalr_api`).
- Create `apps/api/saalr_api/market/oi_repo.py` — `load_oi_history(session, underlying, market)`.
- Modify `apps/api/saalr_api/market/service.py` — enrich `chain(...)` with `oi_change` + `oi_baselines`.
- Create `tests/integration/test_market_oi_change.py` — seed an earlier snapshot, assert ΔOI + baselines.

**Frontend**
- Modify `apps/web/src/lib/market.ts` — `OiWindow` type, `Contract.oi_change`, `Chain.oi_baselines`.
- Modify `apps/web/src/features/markets/ChainTable.tsx` — window toggle, Chg OI column, baseline note, accept `oiBaselines` prop.
- Modify `apps/web/src/features/markets/ChainTable.test.tsx` — new assertions.
- Modify `apps/web/src/pages/Markets.tsx` — pass `oiBaselines`, show DTE next to expiry.

---

## Task 1: Baseline picker (pure logic)

**Files:**
- Create: `apps/api/saalr_api/market/oi_change.py`
- Test: `packages/core/tests/test_oi_change.py`

- [ ] **Step 1: Write the failing test**

Create `packages/core/tests/test_oi_change.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from saalr_api.market.oi_change import WINDOWS, elapsed_label, pick_baseline_ts


def _ts(h, m=0):
    return datetime(2026, 5, 30, h, m, tzinfo=timezone.utc)


def test_windows_order():
    assert WINDOWS == ["day", "1h", "3h", "4h"]


def test_no_earlier_snapshot_returns_none():
    as_of = _ts(14, 30)
    assert pick_baseline_ts([as_of], as_of, "1h") is None
    assert pick_baseline_ts([], as_of, "day") is None


def test_1h_picks_nearest_earlier_to_target():
    as_of = _ts(14, 30)               # target for 1h == 13:30
    snaps = [_ts(10), _ts(13, 25), _ts(14, 30)]
    assert pick_baseline_ts(snaps, as_of, "1h") == _ts(13, 25)


def test_3h_picks_nearest_earlier_to_target():
    as_of = _ts(14, 30)               # target for 3h == 11:30
    snaps = [_ts(10), _ts(12), _ts(14, 30)]
    # 12:00 is 30m from target; 10:00 is 90m — pick 12:00
    assert pick_baseline_ts(snaps, as_of, "3h") == _ts(12)


def test_day_picks_earliest_same_day_before_as_of():
    as_of = _ts(14, 30)
    snaps = [_ts(9, 30), _ts(11), _ts(14, 30)]
    assert pick_baseline_ts(snaps, as_of, "day") == _ts(9, 30)


def test_day_ignores_prior_calendar_day():
    as_of = _ts(14, 30)
    prior_day = datetime(2026, 5, 29, 15, tzinfo=timezone.utc)
    assert pick_baseline_ts([prior_day, as_of], as_of, "day") is None


def test_elapsed_label_formats():
    as_of = _ts(14, 30)
    assert elapsed_label(as_of, _ts(11, 23)) == "~3h7m"
    assert elapsed_label(as_of, _ts(13, 30)) == "~1h"
    assert elapsed_label(as_of, _ts(13, 33)) == "~57m"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest packages/core/tests/test_oi_change.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'saalr_api.market.oi_change'`.

- [ ] **Step 3: Write the implementation**

Create `apps/api/saalr_api/market/oi_change.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta

# Display + computation order. "day" is special-cased (since-start-of-day);
# the rest are fixed look-back deltas.
WINDOWS: list[str] = ["day", "1h", "3h", "4h"]
_DELTAS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "3h": timedelta(hours=3),
    "4h": timedelta(hours=4),
}


def pick_baseline_ts(
    snapshot_ts: list[datetime], as_of: datetime, window: str
) -> datetime | None:
    """Pick the baseline snapshot timestamp for a window, or None if unavailable.

    Only snapshots strictly earlier than `as_of` are eligible. For "day" the
    baseline is the earliest snapshot on the same calendar day as `as_of`; for
    the look-back windows it is the snapshot closest to (as_of - delta)."""
    earlier = [t for t in snapshot_ts if t < as_of]
    if not earlier:
        return None
    if window == "day":
        sod = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        same_day = [t for t in earlier if t >= sod]
        return min(same_day) if same_day else None
    target = as_of - _DELTAS[window]
    return min(earlier, key=lambda t: abs((t - target).total_seconds()))


def elapsed_label(as_of: datetime, baseline_ts: datetime) -> str:
    """Compact human label for how long ago the baseline was, e.g. '~3h7m'."""
    secs = max(0, int((as_of - baseline_ts).total_seconds()))
    minutes = secs // 60
    h, m = divmod(minutes, 60)
    if h and m:
        return f"~{h}h{m}m"
    if h:
        return f"~{h}h"
    return f"~{m}m"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest packages/core/tests/test_oi_change.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/api/saalr_api/market/oi_change.py packages/core/tests/test_oi_change.py
git commit -m "feat(api): ΔOI baseline picker (pick_baseline_ts + elapsed_label)"
```

---

## Task 2: OI history repo + chain enrichment

**Files:**
- Create: `apps/api/saalr_api/market/oi_repo.py`
- Modify: `apps/api/saalr_api/market/service.py` (the `chain` method, ~lines 107-120)
- Test: `tests/integration/test_market_oi_change.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_market_oi_change.py`:

```python
import httpx
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import text

from saalr_api.main import create_app
from saalr_core.marketdata.types import RawChain, RawContract, YieldCurve
from saalr_core.pricing.types import OptionKind


class StubProvider:
    async def get_option_chain(self, ticker, market):
        return RawChain(
            underlying=ticker.upper(), market=market, as_of="2026-05-30T14:30:00+00:00",
            spot=185.0, div_yield=0.005,
            contracts=[
                RawContract("2026-09-19", 180.0, OptionKind.CALL, 9.0, 9.2, 9.1, 100, 500,
                            0.26, 0.58, 0.02, -0.05, 0.11),
            ],
        )


class StubRates:
    source_name = "fred"

    async def get_curve(self):
        return YieldCurve("2026-05-29", [(1 / 12, 0.05), (2.0, 0.045)])


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _make_pro(admin_engine, tenant_id):
    async with admin_engine.begin() as conn:
        await conn.execute(text("UPDATE subscriptions SET tier='pro' WHERE tenant_id=:t"),
                           {"t": tenant_id})


async def _seed_earlier_snapshot(admin_engine, oi: int):
    """Insert one earlier snapshot for OICHG @180 CALL with the given OI."""
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM options_chain_snapshots WHERE underlying='OICHG'"))
        await conn.execute(
            text("INSERT INTO options_chain_snapshots "
                 "(ts, underlying, market, expiry, strike, option_type, open_interest) "
                 "VALUES (:ts,'OICHG','US','2026-09-19',:strike,'CALL',:oi)"),
            {"ts": datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
             "strike": Decimal("180"), "oi": oi},
        )


async def test_chain_reports_oi_change_vs_earlier_snapshot(app_sessionmaker, admin_engine):
    await _seed_earlier_snapshot(admin_engine, oi=450)
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        await app.state.redis.delete("mdq:chain:v1:US:OICHG")
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oichg@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            r = await c.get("/v1/market/chain?ticker=OICHG&expiry=2026-09-19", headers=h)
    assert r.status_code == 200
    body = r.json()
    # current OI 500 - earlier 450 = +50 for every window (only one earlier snapshot)
    contract = body["contracts"][0]
    assert contract["oi_change"]["day"] == 50
    assert contract["oi_change"]["1h"] == 50
    assert body["oi_baselines"]["day"]["ts"].startswith("2026-05-30T10:00")
    assert body["oi_baselines"]["day"]["elapsed_label"].startswith("~")


async def test_chain_oi_change_null_when_no_earlier_snapshot(app_sessionmaker, admin_engine):
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM options_chain_snapshots WHERE underlying='OICHG'"))
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.market_provider = StubProvider()
        app.state.rate_provider = StubRates()
        await app.state.redis.delete("mdq:chain:v1:US:OICHG")
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:oichg2@x.com"}
            tid = (await c.get("/me", headers=h)).json()["tenant"]["id"]
            await _make_pro(admin_engine, tid)
            r = await c.get("/v1/market/chain?ticker=OICHG&expiry=2026-09-19", headers=h)
    body = r.json()
    assert body["contracts"][0]["oi_change"]["day"] is None
    assert body["oi_baselines"]["day"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest tests/integration/test_market_oi_change.py -q`
Expected: FAIL — `KeyError: 'oi_change'` (the chain response has no such field yet).

- [ ] **Step 3: Write the repo query**

Create `apps/api/saalr_api/market/oi_repo.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# (expiry_iso, strike_rounded, option_type) -> open_interest
OiKey = tuple[str, float, str]


async def load_oi_history(
    session: AsyncSession, underlying: str, market: str
) -> dict[datetime, dict[OiKey, int]]:
    """Load every stored snapshot's per-contract open interest for an underlying,
    keyed by snapshot timestamp. The table is small + shared (non-tenant)."""
    rows = (await session.execute(
        text("SELECT ts, expiry, strike, option_type, open_interest "
             "FROM options_chain_snapshots WHERE underlying = :u AND market = :m"),
        {"u": underlying, "m": market},
    )).all()
    hist: dict[datetime, dict[OiKey, int]] = {}
    for r in rows:
        if r.open_interest is None:
            continue
        key: OiKey = (r.expiry.isoformat(), round(float(r.strike), 4), r.option_type)
        hist.setdefault(r.ts, {})[key] = int(r.open_interest)
    return hist
```

- [ ] **Step 4: Enrich `MarketService.chain`**

In `apps/api/saalr_api/market/service.py`, add imports near the top (after `from .snapshots import persist_chain`):

```python
from . import oi_repo
from .oi_change import WINDOWS, elapsed_label, pick_baseline_ts
```

Replace the `chain` method (currently lines 107-120) with:

```python
    async def chain(self, session, ticker, market, expiry: str | None) -> dict:
        payload = await self._computed_chain(session, ticker, market)
        rows = payload["contracts"]
        if expiry:
            rows = [r for r in rows if r["expiry"] == expiry]

        hist = await oi_repo.load_oi_history(session, payload["ticker"], market)
        as_of = datetime.fromisoformat(payload["as_of"])
        ts_list = sorted(hist.keys())
        baseline_ts = {w: pick_baseline_ts(ts_list, as_of, w) for w in WINDOWS}
        oi_baselines = {
            w: ({"ts": bts.isoformat(), "elapsed_label": elapsed_label(as_of, bts)} if bts else None)
            for w, bts in baseline_ts.items()
        }
        for r in rows:
            key = (r["expiry"], round(float(r["strike"]), 4), r["type"])
            cur = r.get("open_interest")
            change: dict[str, int | None] = {}
            for w in WINDOWS:
                bts = baseline_ts[w]
                base = hist.get(bts, {}).get(key) if bts is not None else None
                change[w] = (cur - base) if (base is not None and cur is not None) else None
            r["oi_change"] = change

        return {
            "ticker": payload["ticker"],
            "market": payload["market"],
            "as_of": payload["as_of"],
            "spot": payload["spot"],
            "model": "bsm",
            "risk_free_source": payload["risk_free_source"],
            "contracts": rows,
            "oi_baselines": oi_baselines,
        }
```

- [ ] **Step 5: Run the integration test to verify it passes**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest tests/integration/test_market_oi_change.py tests/integration/test_market.py -q`
Expected: PASS (test_market.py still green — `chain()` keeps the same shape plus new fields).

- [ ] **Step 6: Commit**

```bash
git add apps/api/saalr_api/market/oi_repo.py apps/api/saalr_api/market/service.py tests/integration/test_market_oi_change.py
git commit -m "feat(api): enrich chain with per-strike oi_change + oi_baselines"
```

---

## Task 3: Frontend types + ChainTable Chg OI column

**Files:**
- Modify: `apps/web/src/lib/market.ts`
- Modify: `apps/web/src/features/markets/ChainTable.tsx`
- Test: `apps/web/src/features/markets/ChainTable.test.tsx`

- [ ] **Step 1: Add the types**

In `apps/web/src/lib/market.ts`, add the window type and extend `Contract` + `Chain`:

```typescript
export type OiWindow = 'day' | '1h' | '3h' | '4h'

export interface OiBaseline {
  ts: string
  elapsed_label: string
}
```

Add to the `Contract` interface (after `open_interest: number`):

```typescript
  oi_change?: Record<OiWindow, number | null>
```

Add to the `Chain` interface (after `contracts: Contract[]`):

```typescript
  oi_baselines?: Record<OiWindow, OiBaseline | null>
```

- [ ] **Step 2: Write the failing ChainTable assertions**

In `apps/web/src/features/markets/ChainTable.test.tsx`, add this block inside the existing top-level `describe(...)` (reuse the file's existing imports — `render`, `screen`, `fireEvent` from `@testing-library/react`, and the `Contract` type / a contract factory if present; otherwise inline the contract below):

```tsx
import type { Contract } from '../../lib/market'

function contractWithChange(): Contract {
  return {
    expiry: '2026-09-19', strike: 180, type: 'CALL', bid: 9, ask: 9.2, last: 9.1,
    volume: 100, open_interest: 500,
    oi_change: { day: 12400, '1h': -2100, '3h': 0, '4h': 500 },
    ours: { price: 9, delta: 0.5, gamma: 0.02, theta: -0.05, vega: 0.11, rho: 0.01, iv: 0.26 },
    vendor: { iv: 0.26, delta: 0.58, gamma: 0.02, theta: -0.05, vega: 0.11 },
  }
}

it('shows the Chg OI column and switches values by window', () => {
  render(<ChainTable contracts={[contractWithChange()]} spot={185}
    oiBaselines={{ day: { ts: '2026-05-30T10:00:00+00:00', elapsed_label: '~4h30m' },
      '1h': null, '3h': null, '4h': null }} />)
  // default window = day → +12.4k, green
  const cell = screen.getByTestId('chg-call-180')
  expect(cell.textContent).toContain('+12.4k')
  expect(cell.className).toContain('text-pos')
  // baseline note reflects the day baseline
  expect(screen.getByTestId('oi-baseline-note').textContent).toContain('~4h30m')
  // switch to 1h → -2.1k, red
  fireEvent.click(screen.getByTestId('oi-window-1h'))
  expect(screen.getByTestId('chg-call-180').textContent).toContain('-2.1k')
  expect(screen.getByTestId('chg-call-180').className).toContain('text-neg')
})

it('renders an em-dash and a no-baseline note when oi_change is missing', () => {
  const c = contractWithChange()
  c.oi_change = undefined
  render(<ChainTable contracts={[c]} spot={185}
    oiBaselines={{ day: null, '1h': null, '3h': null, '4h': null }} />)
  expect(screen.getByTestId('chg-call-180').textContent).toContain('—')
  expect(screen.getByTestId('oi-baseline-note').textContent.toLowerCase()).toContain('no earlier snapshot')
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd apps/web && npx vitest run src/features/markets/ChainTable.test.tsx`
Expected: FAIL — `oi-window-1h` / `chg-call-180` / `oi-baseline-note` test IDs don't exist; `oiBaselines` prop unknown.

- [ ] **Step 4: Implement the column + toggle + note**

In `apps/web/src/features/markets/ChainTable.tsx`:

(a) Update imports + the `ColDef` interface to allow a per-cell class, and import the window type:

```tsx
import type { Contract, OiWindow, OiBaseline } from '../../lib/market'
```

```tsx
interface ColDef { key: string; label: string; val: (c: Contract) => string; bar?: boolean; cls?: (c: Contract) => string }
```

(b) Add formatter + class helpers near the other formatters (after `const kfmt = ...`):

```tsx
const dfmt = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—'
  const sign = v > 0 ? '+' : v < 0 ? '-' : ''
  const a = Math.abs(v)
  return `${sign}${a >= 1000 ? `${(a / 1000).toFixed(1)}k` : a}`
}
const dcls = (v: number | null | undefined): string =>
  v == null ? 'text-txtFaint' : v > 0 ? 'text-pos' : v < 0 ? 'text-neg' : 'text-txtDim'
```

(c) In `SideCells`, give the Chg cell a stable testid **and** the color class on the inner value span — leave the `<td>`'s existing `data-testid` (`col.key === ordered[0].key ? \`${side}-cells-${strike}\` : undefined`) and `data-itm` logic UNTOUCHED so the existing ITM-shading test keeps working. Replace only the value span line:

```tsx
            <span
              data-testid={col.key === 'chg' ? `chg-${side}-${strike}` : undefined}
              className={`relative ${c && col.cls ? col.cls(c) : ''}`}
            >{c ? col.val(c) : '—'}</span>
```

(d) Add the window state + props. Change the component signature and add state:

```tsx
export function ChainTable({ contracts, spot, oiBaselines }: {
  contracts: Contract[]; spot: number; oiBaselines?: Record<OiWindow, OiBaseline | null>
}) {
  const [mode, setMode] = useState<Mode>('default')
  const [win, setWin] = useState<Win>(10)
  const [oiWin, setOiWin] = useState<OiWindow>('day')
```

(e) Build the columns so the Chg column (default mode only) leads, closing over `oiWin`. Replace the existing `const cols = mode === 'greeks' ? GREEK_COLS : DEFAULT_COLS` line with:

```tsx
  const chgCol: ColDef = {
    key: 'chg', label: 'Chg',
    val: (c) => dfmt(c.oi_change?.[oiWin] ?? null),
    cls: (c) => dcls(c.oi_change?.[oiWin] ?? null),
  }
  const cols = mode === 'greeks' ? GREEK_COLS : [chgCol, ...DEFAULT_COLS]
```

(f) Add the window toggle + baseline note to the controls row. Inside the top controls `<div className="flex flex-wrap items-center gap-2 text-[11px]">`, after the existing Prices/Greeks toggle `<div>` and before the `ml-auto` strikes block, insert:

```tsx
        {mode === 'default' && (
          <div className="flex items-center gap-1 text-txtFaint">
            <span className="font-mono text-[9px] uppercase tracking-wider">Chg OI</span>
            {(['day', '1h', '3h', '4h'] as OiWindow[]).map((w) => (
              <button key={w} data-testid={`oi-window-${w}`} onClick={() => setOiWin(w)}
                className={`rounded px-2 py-0.5 ${oiWin === w ? 'bg-panel text-txt' : 'text-txtDim hover:text-txt'}`}>
                {w === 'day' ? 'Day' : w}
              </button>
            ))}
          </div>
        )}
```

Then, immediately after that controls `<div>` closes (before the `<div className="max-h-[70vh] ...">` table wrapper), add the baseline note:

```tsx
      {mode === 'default' && (
        <p data-testid="oi-baseline-note" className="text-[10px] text-txtFaint">
          {oiBaselines?.[oiWin]
            ? `Chg OI vs ${new Date(oiBaselines[oiWin]!.ts).toLocaleTimeString()} (${oiBaselines[oiWin]!.elapsed_label} ago)`
            : 'Chg OI — no earlier snapshot in range.'}
        </p>
      )}
```

- [ ] **Step 5: Run ChainTable tests to verify they pass**

Run: `cd apps/web && npx vitest run src/features/markets/ChainTable.test.tsx`
Expected: PASS (existing chain tests + the 2 new ones).

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/market.ts apps/web/src/features/markets/ChainTable.tsx apps/web/src/features/markets/ChainTable.test.tsx
git commit -m "feat(web): Chg OI column + Day/1h/3h/4h toggle + baseline note on the chain"
```

---

## Task 4: Markets wiring — pass baselines + DTE label

**Files:**
- Modify: `apps/web/src/pages/Markets.tsx`
- Test: `apps/web/src/pages/Markets.test.tsx` (extend if present; otherwise the ChainTable test covers the column — add a focused DTE test inline here)

- [ ] **Step 1: Write the failing DTE test**

Add to `apps/web/src/pages/Markets.test.tsx` (if the file does not exist, create it mirroring the existing markets test setup — a `wrap()` with `QueryClientProvider` + `MemoryRouter`, `me.entitlements.vol_surface=true`, and a stubbed `fetch` returning an iv-surface with one expiry). Add this assertion after a surface loads with `expiry='2026-09-19'`:

```tsx
// DTE label appears next to the expiry selector
await waitFor(() => expect(screen.getByTestId('expiry-dte')).toBeInTheDocument())
expect(screen.getByTestId('expiry-dte').textContent).toMatch(/\d+d/)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run src/pages/Markets.test.tsx`
Expected: FAIL — no `expiry-dte` element.

- [ ] **Step 3: Implement DTE label + pass oiBaselines**

In `apps/web/src/pages/Markets.tsx`:

(a) Add a DTE helper above the component:

```tsx
function dteDays(expiry: string): number | null {
  if (!expiry) return null
  const ms = new Date(`${expiry}T00:00:00Z`).getTime() - Date.now()
  return Number.isFinite(ms) ? Math.max(0, Math.round(ms / 86_400_000)) : null
}
```

(b) Render the DTE next to the expiry select. Immediately after the `<select data-testid="expiry-select" ...>...</select>` element, add:

```tsx
            {dteDays(activeExpiry) !== null && (
              <span data-testid="expiry-dte" className="font-mono text-[11px] text-txtFaint">
                {dteDays(activeExpiry)}d
              </span>
            )}
```

(c) Pass baselines into the table. Replace the `<ChainTable contracts={chainQ.data.contracts} spot={surface.spot} />` line with:

```tsx
              <ChainTable contracts={chainQ.data.contracts} spot={surface.spot}
                oiBaselines={chainQ.data.oi_baselines} />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run src/pages/Markets.test.tsx`
Expected: PASS.

- [ ] **Step 5: Typecheck + full web suite**

Run: `cd apps/web && npx tsc --noEmit && npx vitest run`
Expected: tsc clean; all test files pass.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/pages/Markets.tsx apps/web/src/pages/Markets.test.tsx
git commit -m "feat(web): pass oi_baselines to ChainTable + DTE label on Markets"
```

---

## Final verification

- [ ] **Backend (touched paths):**

Run: `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0" uv run python -m pytest packages/core/tests/test_oi_change.py tests/integration/test_market_oi_change.py tests/integration/test_market.py -q`
Expected: all PASS.

- [ ] **Lint:** `ruff check apps/api/saalr_api/market/oi_change.py apps/api/saalr_api/market/oi_repo.py apps/api/saalr_api/market/service.py`
Expected: no errors.

- [ ] **Manual smoke (optional, dev stack + a ticker with ≥2 snapshots):** open `/app/markets`, load a ticker, **Chain** tab → the Chg OI column shows ΔOI, the Day/1h/3h/4h toggle switches values, and the baseline note shows the timestamp. Use the **Dev Seed** panel's repeat capture to accumulate snapshots first.
