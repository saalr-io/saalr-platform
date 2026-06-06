# Paper-Trade a Strategy (Beginner Practice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One-click "Paper trade" that places every leg of a strategy into a Practice paper account, surfaced on the Ideas recommendations and the Strategies builder, so beginners can practise.

**Architecture:** A new `POST /v1/orders/strategy` endpoint loops the existing `place_order` (risk + paper-fill) over each option/equity leg (skips cash, places with no `strategy_id`), returning honest per-leg results. The web `usePaperTradeStrategy` hook auto-ensures a Practice paper account, then calls it; entry points are the Ideas `RecoCard` (with a guided confirm) and the Strategies builder.

**Tech Stack:** FastAPI + asyncpg + pytest (backend); React 18 + TS strict + Tailwind (theme tokens only) + TanStack Query + Vitest (web). **pnpm/npm — NOT yarn.**

**Spec:** `docs/superpowers/specs/2026-06-06-paper-trade-strategy-practice-design.md`

**Conventions:** commit footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`; theme tokens only for Tailwind class colors; double-quote JSX strings; NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`; branch `feat/scaffold-data-layer`. Backend tests need Postgres on **55432** (`APP_DATABASE_URL`/`ADMIN_DATABASE_URL` env; ADMIN as the `postgres` superuser); if the DB is down locally they error on connect like other DB tests — the unit logic is still covered. Web: from `apps/web`, `npx vitest run <file>`; gate `npm run typecheck`/`npm run lint`.

---

## File Structure

- **Modify** `apps/api/saalr_api/oms/schemas.py` — `LegSpec` + `StrategyOrderCreate`.
- **Modify** `apps/api/saalr_api/oms/service.py` — `place_strategy()`.
- **Modify** `apps/api/saalr_api/oms/router.py` — `POST /v1/orders/strategy`.
- **Create** `tests/integration/test_paper_strategy.py`.
- **Modify** `apps/web/src/lib/oms.ts` — `placeStrategy` + types.
- **Create** `apps/web/src/features/portfolio/usePaperTrade.ts` + `usePaperTrade.test.ts`.
- **Modify** `apps/web/src/features/ideas/RecoCard.tsx` + `RecoCard.test.tsx` (new) — Paper-trade + confirm.
- **Modify** `apps/web/src/pages/Ideas.tsx` — wire the mutation + per-card state.
- **Modify** `apps/web/src/pages/Strategies.tsx` — a Paper-trade button on the builder.

---

## Task 1: Backend — `POST /v1/orders/strategy`

**Files:** Modify `oms/schemas.py`, `oms/service.py`, `oms/router.py`; Test `tests/integration/test_paper_strategy.py`.

- [ ] **Step 1: Add schemas** to `apps/api/saalr_api/oms/schemas.py` — append at the end of the file:

```python
class LegSpec(BaseModel):
    kind: str                       # "option" | "equity" | "cash"
    side: str | None = None         # BUY | SELL (option/equity)
    qty: int | None = None
    option_type: str | None = None  # CALL | PUT
    strike: Decimal | None = None
    expiry: date | None = None
    amount: Decimal | None = None   # cash legs (ignored for orders)


class StrategyOrderCreate(BaseModel):
    broker_account_id: str
    underlying: str = Field(min_length=1)
    legs: list[LegSpec] = Field(min_length=1)
```
(`BaseModel`, `Field`, `Decimal`, `date` are already imported in this file — `OrderCreate` uses them.)

- [ ] **Step 2: Add the service** to `apps/api/saalr_api/oms/service.py` — append after `place_order`:

```python
async def place_strategy(session: AsyncSession, principal, body, idem, request_id,
                         adapter_factory=None) -> dict:
    """Place each option/equity leg of a strategy as a standalone paper order (no strategy_id —
    the risk gate rejects a strategy_id whose strategy isn't in paper/live state). Cash legs are
    skipped. place_order raises HTTPException on a reject, so each leg is wrapped; a leg placed
    before a later reject stays placed — the per-leg result is the honest record."""
    results: list[dict] = []
    for i, leg in enumerate(body.legs):
        if leg.kind == "cash":
            results.append({"leg_index": i, "kind": "cash", "status": "skipped"})
            continue
        order = OrderCreate(
            broker_account_id=body.broker_account_id,
            symbol=body.underlying.upper(),
            side=leg.side or "BUY",
            qty=leg.qty or 0,
            order_type="market",
            option_type=leg.option_type if leg.kind == "option" else None,
            strike=leg.strike if leg.kind == "option" else None,
            expiry=leg.expiry if leg.kind == "option" else None,
            time_in_force="day",
        )
        try:
            res = await place_order(session, principal, order, f"{idem}:{i}", request_id, adapter_factory)
            results.append({"leg_index": i, "kind": leg.kind, "status": res["status"],
                            "order_id": res["order_id"]})
        except HTTPException as exc:
            code = (exc.detail["error"]["code"]
                    if isinstance(exc.detail, dict) and "error" in exc.detail else str(exc.detail))
            results.append({"leg_index": i, "kind": leg.kind, "status": "rejected", "reject_code": code})
    placed = sum(1 for r in results if r["status"] not in ("rejected", "skipped"))
    rejected = sum(1 for r in results if r["status"] == "rejected")
    return {"broker_account_id": str(body.broker_account_id), "results": results,
            "placed": placed, "rejected": rejected}
```

- [ ] **Step 3: Add the route** to `apps/api/saalr_api/oms/router.py`:
  1. Add `StrategyOrderCreate` to the schemas import:
     ```python
     from .schemas import BrokerAccountCreate, OrderCreate, StrategyOrderCreate
     ```
  2. Add the endpoint right after the existing `place` handler (the `POST /v1/orders` one):
     ```python
     @router.post("/v1/orders/strategy")
     async def place_strategy(body: StrategyOrderCreate, request: Request,
                              idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                              ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
         session, principal = ctx
         factory = getattr(request.app.state, "alpaca_adapter_factory", None)
         idem = idempotency_key or str(new_id())
         return await service.place_strategy(session, principal, body, idem, _request_id(request), factory)
     ```
     (`Header`, `new_id`, `Request`, `Depends`, `get_principal`, `_request_id` are already imported/defined in this router.)

- [ ] **Step 4: Write the integration test** `tests/integration/test_paper_strategy.py`:

```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import text

from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _seed_bars(admin_engine, symbol, px=50.0, n=40):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    async with admin_engine.begin() as conn:
        await conn.execute(text("DELETE FROM bars WHERE symbol=:s"), {"s": symbol})
        for i in range(n):
            ts = start + timedelta(days=i)
            await conn.execute(
                text("""INSERT INTO bars (ts, symbol, market, interval, open, high, low, close, volume)
                        VALUES (:ts,:sym,'US','1d',:o,:h,:l,:c,:v)"""),
                {"ts": ts, "sym": symbol, "o": Decimal(str(px)), "h": Decimal(str(px + 1)),
                 "l": Decimal(str(px - 1)), "c": Decimal(str(px)), "v": 1000},
            )


async def _account(c, h):
    r = await c.post("/v1/broker-accounts", json={"account_label": "Practice"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["broker_account_id"]


async def test_place_strategy_skips_cash_and_fills_equity(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ps-1@x.com"}
            acct = await _account(c, h)
            body = {
                "broker_account_id": acct, "underlying": "AAPL",
                "legs": [
                    {"kind": "equity", "side": "BUY", "qty": 1},
                    {"kind": "cash", "amount": "5000"},
                ],
            }
            r = await c.post("/v1/orders/strategy", json=body, headers={**h, "Idempotency-Key": "ps1"})
            assert r.status_code == 200, r.text
            out = r.json()
            assert len(out["results"]) == 2
            kinds = {res["kind"]: res["status"] for res in out["results"]}
            assert kinds["cash"] == "skipped"
            assert kinds["equity"] == "filled"
            assert out["placed"] == 1 and out["rejected"] == 0


async def test_place_strategy_reports_a_rejected_leg(app_sessionmaker, admin_engine):
    await _seed_bars(admin_engine, "AAPL", px=50.0)
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ps-2@x.com"}
            acct = await _account(c, h)
            future = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
            body = {
                "broker_account_id": acct, "underlying": "AAPL",
                "legs": [
                    {"kind": "equity", "side": "BUY", "qty": 1},
                    {"kind": "option", "side": "BUY", "qty": 1, "option_type": "CALL",
                     "strike": "50", "expiry": future},
                ],
            }
            r = await c.post("/v1/orders/strategy", json=body, headers={**h, "Idempotency-Key": "ps2"})
            assert r.status_code == 200, r.text
            out = r.json()
            assert out["placed"] == 1 and out["rejected"] == 1
            opt = [res for res in out["results"] if res["kind"] == "option"][0]
            assert opt["status"] == "rejected" and opt["reject_code"] == "RISK_NO_MARKET_DATA"
```

- [ ] **Step 5: Run the tests**

Run (needs DB on 55432 — set `APP_DATABASE_URL`/`ADMIN_DATABASE_URL`; ADMIN as `postgres`):
`uv run pytest tests/integration/test_paper_strategy.py -q`
Expected: 2 passed. Also `uv run python -c "from saalr_api.main import create_app; create_app()"` → clean (catches wiring typos even without a DB). If the DB is unavailable, that build check + the web tasks still proceed; verify in the final-gate live smoke.

- [ ] **Step 6: Commit**

```bash
git add apps/api/saalr_api/oms/schemas.py apps/api/saalr_api/oms/service.py apps/api/saalr_api/oms/router.py tests/integration/test_paper_strategy.py
git commit -m "feat(oms): POST /v1/orders/strategy — place a strategy's legs as paper orders

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Web client — `placeStrategy`

**Files:** Modify `apps/web/src/lib/oms.ts`.

- [ ] **Step 1: Add types + the function** to `apps/web/src/lib/oms.ts` — append after the existing `placeOrder` function:

```ts
export interface StrategyLeg {
  kind: 'option' | 'equity' | 'cash'
  side?: 'BUY' | 'SELL'
  qty?: number
  option_type?: 'CALL' | 'PUT'
  strike?: number
  expiry?: string
  amount?: number
}

export interface StrategyOrderResult {
  broker_account_id: string
  results: { leg_index: number; kind: string; status: string; order_id?: string; reject_code?: string }[]
  placed: number
  rejected: number
}

export function placeStrategy(
  body: { broker_account_id: string; underlying: string; legs: StrategyLeg[] },
): Promise<StrategyOrderResult> {
  return request('/v1/orders/strategy', {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(body),
  })
}
```
(`request` already injects `Content-Type` + auth headers and merges `init.headers`.)

- [ ] **Step 2: Typecheck**

Run (from `apps/web`): `npm run typecheck` → clean. (No test for the bare client wrapper; it's covered via the hook in Task 3.)

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/oms.ts
git commit -m "feat(web): oms client placeStrategy (POST /v1/orders/strategy)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `usePaperTradeStrategy` hook

**Files:** Create `apps/web/src/features/portfolio/usePaperTrade.ts` + `usePaperTrade.test.ts`.

- [ ] **Step 1: Write the failing test** `apps/web/src/features/portfolio/usePaperTrade.test.ts`:

```ts
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import * as oms from '../../lib/oms'
import { usePaperTradeStrategy } from './usePaperTrade'
import type { StrategyConfig } from '../../lib/strategies'

const CONFIG: StrategyConfig = {
  underlying: 'SPY',
  legs: [{ kind: 'option', option_type: 'CALL', side: 'BUY', strike: 580, expiry: '2026-12-18', qty: 1 }],
}
const RESULT = { broker_account_id: 'a1', results: [{ leg_index: 0, kind: 'option', status: 'filled' }], placed: 1, rejected: 0 }

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('usePaperTradeStrategy', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('reuses an existing paper account', async () => {
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [
      { broker_account_id: 'a1', broker: 'paper', account_label: 'Practice', is_paper: true, status: 'active' } as never] })
    const create = vi.spyOn(oms, 'createBrokerAccount')
    const place = vi.spyOn(oms, 'placeStrategy').mockResolvedValue(RESULT as never)
    const { result } = renderHook(() => usePaperTradeStrategy(), { wrapper: wrapper() })
    result.current.mutate(CONFIG)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(create).not.toHaveBeenCalled()
    expect(place).toHaveBeenCalledWith({ broker_account_id: 'a1', underlying: 'SPY', legs: CONFIG.legs })
  })

  it('creates a Practice account when none exists', async () => {
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [] })
    const create = vi.spyOn(oms, 'createBrokerAccount').mockResolvedValue(
      { broker_account_id: 'new', broker: 'paper', account_label: 'Practice', is_paper: true, status: 'active' } as never)
    const place = vi.spyOn(oms, 'placeStrategy').mockResolvedValue({ ...RESULT, broker_account_id: 'new' } as never)
    const { result } = renderHook(() => usePaperTradeStrategy(), { wrapper: wrapper() })
    result.current.mutate(CONFIG)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(create).toHaveBeenCalledWith('Practice')
    expect(place).toHaveBeenCalledWith({ broker_account_id: 'new', underlying: 'SPY', legs: CONFIG.legs })
  })
})
```

- [ ] **Step 2: Run it, verify it fails**

Run (from `apps/web`): `npx vitest run src/features/portfolio/usePaperTrade.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Create** `apps/web/src/features/portfolio/usePaperTrade.ts`:

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { listBrokerAccounts, createBrokerAccount, placeStrategy, type StrategyOrderResult } from '../../lib/oms'
import type { StrategyConfig } from '../../lib/strategies'

// Ensure a Practice paper account exists, then place every leg of the strategy into it.
export function usePaperTradeStrategy() {
  const qc = useQueryClient()
  return useMutation<StrategyOrderResult, Error, StrategyConfig>({
    mutationFn: async (config) => {
      const { broker_accounts } = await listBrokerAccounts()
      const existing = broker_accounts.find((a) => a.is_paper)
      const account = existing ?? (await createBrokerAccount('Practice'))
      return placeStrategy({
        broker_account_id: account.broker_account_id,
        underlying: config.underlying,
        legs: config.legs as never,
      })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['broker-accounts'] })
      void qc.invalidateQueries({ queryKey: ['orders'] })
      void qc.invalidateQueries({ queryKey: ['positions'] })
    },
  })
}
```
(`config.legs` is the strategy builder's `Leg[]`; the OMS `StrategyLeg[]` is structurally the option/equity/cash subset, so the `as never` cast bridges the two leg unions without a runtime change.)

- [ ] **Step 4: Run the test, verify it passes**

Run: `npx vitest run src/features/portfolio/usePaperTrade.test.ts` → 2 passed. Then `npm run typecheck` + `npm run lint` clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/portfolio/usePaperTrade.ts apps/web/src/features/portfolio/usePaperTrade.test.ts
git commit -m "feat(web): usePaperTradeStrategy hook — ensure Practice account then place the legs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Ideas — Paper-trade with a guided confirm

**Files:** Modify `apps/web/src/features/ideas/RecoCard.tsx`; Create `apps/web/src/features/ideas/RecoCard.test.tsx`; Modify `apps/web/src/pages/Ideas.tsx`.

- [ ] **Step 1: Write the failing test** `apps/web/src/features/ideas/RecoCard.test.tsx`:

```tsx
import type React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { RecoCard } from './RecoCard'
import type { Recommendation } from '../../lib/regime'

const RECO: Recommendation = {
  template_key: 'bull_put_spread', name: 'Bull Put Spread', score: 7, market_view: 'bullish',
  vol_view: 'short_vol', net: 'credit', risk: 'defined', complexity: 'beginner', rationale: 'Fits a bullish view.',
}

function wrap(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('RecoCard', () => {
  it('Apply fires onApply', () => {
    const onApply = vi.fn()
    wrap(<RecoCard reco={RECO} onApply={onApply} applying={false} onPaperTrade={vi.fn()} paperState="idle" />)
    fireEvent.click(screen.getByTestId('reco-apply-bull_put_spread'))
    expect(onApply).toHaveBeenCalledWith('bull_put_spread')
  })

  it('Paper-trade opens a confirm and Place fires onPaperTrade', () => {
    const onPaperTrade = vi.fn()
    wrap(<RecoCard reco={RECO} onApply={vi.fn()} applying={false} onPaperTrade={onPaperTrade} paperState="idle" />)
    fireEvent.click(screen.getByTestId('reco-paper-bull_put_spread'))
    expect(screen.getByTestId('reco-confirm-bull_put_spread')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('reco-confirm-place-bull_put_spread'))
    expect(onPaperTrade).toHaveBeenCalledWith('bull_put_spread')
  })

  it('shows a placed result with a Portfolio link', () => {
    wrap(<RecoCard reco={RECO} onApply={vi.fn()} applying={false} onPaperTrade={vi.fn()}
      paperState={{ placed: 2, rejected: 0 }} />)
    const done = screen.getByTestId('reco-paper-done-bull_put_spread')
    expect(done.textContent).toContain('2')
    expect(screen.getByText(/portfolio/i).getAttribute('href')).toBe('/portfolio')
  })
})
```

- [ ] **Step 2: Run it, verify it fails**

Run: `npx vitest run src/features/ideas/RecoCard.test.tsx`
Expected: FAIL (the new props/testids don't exist).

- [ ] **Step 3: Rewrite** `apps/web/src/features/ideas/RecoCard.tsx`:

```tsx
import type React from 'react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Recommendation } from '../../lib/regime'

function Badge({ children, tone }: { children: React.ReactNode; tone?: 'warn' }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide ${
        tone === 'warn' ? 'bg-warn/15 text-warn' : 'border border-lineSoft text-txtFaint'
      }`}
    >
      {children}
    </span>
  )
}

export type PaperState = 'idle' | 'pending' | { placed: number; rejected: number }

export function RecoCard({
  reco, onApply, applying, onPaperTrade, paperState,
}: {
  reco: Recommendation
  onApply: (key: string) => void
  applying: boolean
  onPaperTrade: (key: string) => void
  paperState: PaperState
}) {
  const [confirming, setConfirming] = useState(false)
  const k = reco.template_key
  const done = typeof paperState === 'object' ? paperState : null

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line bg-panel p-3" data-testid={`reco-${k}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium text-txt">{reco.name}</span>
        <span className="tnum font-mono text-[10px] text-txtFaint">score {reco.score}</span>
      </div>
      <p className="text-[11px] leading-snug text-txtDim">{reco.rationale}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge>{reco.net}</Badge>
        <Badge tone={reco.risk === 'undefined' ? 'warn' : undefined}>
          {reco.risk === 'undefined' ? 'undefined risk' : 'defined risk'}
        </Badge>
        <button
          type="button"
          data-testid={`reco-paper-${k}`}
          onClick={() => setConfirming(true)}
          disabled={paperState === 'pending'}
          className="ml-auto rounded-md border border-line px-3 py-1 text-[11px] text-txtDim transition-colors hover:text-txt disabled:opacity-40"
        >
          {paperState === 'pending' ? "Placing…" : "Paper trade"}
        </button>
        <button
          type="button"
          data-testid={`reco-apply-${k}`}
          onClick={() => onApply(k)}
          disabled={applying}
          className="rounded-md bg-accent px-3 py-1 text-[11px] font-medium text-canvas transition hover:opacity-90 disabled:opacity-40"
        >
          {applying ? "Opening…" : "Apply"}
        </button>
      </div>

      {confirming && !done && (
        <div className="rounded-md border border-dashed border-line bg-panel2 p-2.5 text-[11px] text-txtDim" data-testid={`reco-confirm-${k}`}>
          Places risk-free paper orders for <span className="text-txt">{reco.name}</span> into your Practice
          account so you can watch how the trade behaves.
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              data-testid={`reco-confirm-place-${k}`}
              onClick={() => { setConfirming(false); onPaperTrade(k) }}
              className="rounded bg-accent px-3 py-1 text-[11px] font-medium text-canvas hover:opacity-90"
            >
              Place paper trade
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="px-2 py-1 text-[11px] text-txtFaint hover:text-txt">
              Cancel
            </button>
          </div>
        </div>
      )}

      {done && (
        <p className="text-[11px] text-txtDim" data-testid={`reco-paper-done-${k}`}>
          Placed {done.placed} paper order{done.placed === 1 ? '' : 's'}
          {done.rejected > 0 ? ` · ${done.rejected} couldn't fill (need market data)` : ''} ·{' '}
          <Link to="/portfolio" className="text-accent hover:underline">View in Portfolio →</Link>
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Wire** `apps/web/src/pages/Ideas.tsx`:

Add imports (after the existing `buildTemplate` import):
```tsx
import { usePaperTradeStrategy } from '../features/portfolio/usePaperTrade'
import type { PaperState } from '../features/ideas/RecoCard'
```
Inside `Ideas()`, after `const navigate = useNavigate()` add the mutation + per-card state:
```tsx
  const paper = usePaperTradeStrategy()
  const [paperKey, setPaperKey] = useState<string | null>(null)

  async function paperTrade(key: string) {
    if (!data) return
    setPaperKey(key)
    try {
      const config = await buildTemplate(key, {
        underlying: data.ticker, expiry: defaultExpiry(), atm_strike: data.regime.last_close,
      })
      await paper.mutateAsync(config)
    } catch {
      setPaperKey(null)
    }
  }

  function paperStateFor(key: string): PaperState {
    if (paperKey !== key) return 'idle'
    if (paper.isPending) return 'pending'
    if (paper.data) return { placed: paper.data.placed, rejected: paper.data.rejected }
    return 'idle'
  }
```
Update the `RecoCard` render to pass the new props:
```tsx
            {recos.slice(0, 5).map((r) => (
              <RecoCard
                key={r.template_key}
                reco={r}
                onApply={apply}
                applying={applyingKey === r.template_key}
                onPaperTrade={paperTrade}
                paperState={paperStateFor(r.template_key)}
              />
            ))}
```

- [ ] **Step 5: Run the tests + gate**

Run (from `apps/web`):
- `npx vitest run src/features/ideas/RecoCard.test.tsx src/pages/Ideas.test.tsx` → green.
- `npm run typecheck` + `npm run lint` → clean.

(`Ideas.test.tsx` renders `RecoCard`; if it asserts on the Apply button it still passes — the testids are unchanged. If TypeScript complains that the test's `<RecoCard>` lacks the new required props, that's only in `RecoCard.test`/`Ideas` which now pass them; the page passes them too.)

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/features/ideas/RecoCard.tsx apps/web/src/features/ideas/RecoCard.test.tsx apps/web/src/pages/Ideas.tsx
git commit -m "feat(web): Paper-trade a recommended strategy from Ideas (guided confirm + result)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Strategies builder — Paper-trade button

**Files:** Modify `apps/web/src/pages/Strategies.tsx`.

- [ ] **Step 1: Add the hook + button.** In `apps/web/src/pages/Strategies.tsx`:

Add the import:
```tsx
import { usePaperTradeStrategy } from '../features/portfolio/usePaperTrade'
import { Link } from 'react-router-dom'
```
(If `Link` is already imported from `react-router-dom`, merge it into the existing import instead of duplicating.)

Inside `Strategies()`, near the other hooks (after `const create = useCreateStrategy()`):
```tsx
  const paper = usePaperTradeStrategy()
```
In the analyze-row button group (where `analyze-btn` and `save-btn` live), add a Paper-trade button after Save:
```tsx
          <button data-testid="paper-trade-btn" onClick={() => paper.mutate(config)} disabled={paper.isPending}
                  className="rounded border border-line px-4 py-1 text-xs text-txtDim hover:text-txt disabled:opacity-40">
            {paper.isPending ? 'Placing…' : 'Paper trade'}
          </button>
```
And a result line after the `saved-ok` span (still inside the same flex row or just below it):
```tsx
          {paper.data && (
            <span className="text-xs text-txtDim" data-testid="paper-trade-result">
              Placed {paper.data.placed}{paper.data.rejected > 0 ? ` · ${paper.data.rejected} rejected` : ''} ·{' '}
              <Link to="/portfolio" className="text-accent hover:underline">Portfolio →</Link>
            </span>
          )}
```

- [ ] **Step 2: Add a test** to `apps/web/src/pages/Strategies.test.tsx`. Add `import * as oms from '../lib/oms'` at the top, ensure `beforeEach` also restores spies (`beforeEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })`), and add inside the existing `describe`:

```tsx
  it('paper-trades the current config', async () => {
    // the builder's initial loads (templates + strategies) go through fetch
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) return new Response(JSON.stringify({ templates: [] }), { status: 200 })
      if (String(url).endsWith('/v1/strategies')) return new Response(JSON.stringify({ strategies: [], next_cursor: null }), { status: 200 })
      return new Response('{}', { status: 200 })
    }))
    // the paper-trade flow goes through the oms module (spied, bypassing fetch)
    const list = vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [
      { broker_account_id: 'a1', broker: 'paper', account_label: 'Practice', is_paper: true, status: 'active' } as never] })
    const place = vi.spyOn(oms, 'placeStrategy').mockResolvedValue(
      { broker_account_id: 'a1', results: [], placed: 2, rejected: 0 } as never)
    render(wrap(<Strategies />))
    fireEvent.click(screen.getByTestId('paper-trade-btn'))
    await waitFor(() => expect(place).toHaveBeenCalled())
    expect(list).toHaveBeenCalled()
    await waitFor(() => expect(screen.getByTestId('paper-trade-result')).toBeInTheDocument())
  })
```
(If the existing `beforeEach` is only `vi.unstubAllGlobals()`, extend it to also `vi.restoreAllMocks()` so these spies don't leak into the other tests.)

- [ ] **Step 3: Run the test + gate**

Run (from `apps/web`):
- `npx vitest run src/pages/Strategies.test.tsx` → green.
- `npm run typecheck` + `npm run lint` → clean.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/pages/Strategies.tsx apps/web/src/pages/Strategies.test.tsx
git commit -m "feat(web): Paper-trade button on the strategy builder

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Final gate

- [ ] **Step 1: Python** — with the 55432 DB env: `uv run pytest tests/integration/test_paper_strategy.py tests/integration/test_oms.py -q` → green. `uv run python -c "from saalr_api.main import create_app; create_app()"` → clean.
- [ ] **Step 2: Web** — from `apps/web`: `npm run typecheck && npm run lint && npm run test:run` → green (+~9 tests). `npm run build` → still "48 HTML documents pre-rendered".
- [ ] **Step 3 (optional, local stack running): live smoke** — restart the API (editable install), log in (`founder@saalr.com`), and from `/app/ideas` → SPY → a recommendation → **Paper trade** → confirm. Expect a "Placed N" result (option legs may show "couldn't fill" if no option market data — that's honest); check `/app/portfolio` for the new orders/positions. Also try the builder's **Paper trade** button. (See [[local-postgres-port-conflict]] for the restart override.)

---

## Self-Review notes (for the executor)

- **No `strategy_id` on the placed orders** — by design (the risk gate rejects a non-`paper`/`live` strategy_id, and reaching `paper` needs the draft→backtested→paper FSM path). Slice 3 grouping is deferred.
- **`place_order` raises on a reject** — the per-leg `try/except HTTPException` in `place_strategy` is what turns a rejected leg into a reported result instead of failing the whole request.
- **Cash legs are skipped** (collateral, not orders); equity + option legs become market orders on the underlying symbol.
- **Per-leg idempotency** `f"{idem}:{i}"` from the request `Idempotency-Key` makes a network retry safe; the client sends a fresh `crypto.randomUUID()` per click.
- **Auto Practice account** — the hook reuses the first `is_paper` account or creates `"Practice"`; success invalidates broker-accounts/orders/positions so the Portfolio updates.
- **Honest partials** — option legs with no market data show "couldn't fill (need market data)"; this is expected for tickers without a seeded/looked-up chain and must NOT be hidden.
- **Leg union bridge** — the builder's `Leg[]` is a superset of the OMS `StrategyLeg[]`; the `as never` cast in the hook is intentional (structural, no runtime change).
