# Onboarding & Account/Settings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship a beginner onboarding loop (Dashboard checklist + guided `/app/start`, server-side step state) and a fuller Account/Settings page (marketing opt-in, profile edit, manage-subscription, request-deletion).

**Architecture:** Slice 1 = migration `0014` (onboarding_progress table + RLS) + an `onboarding` API + frontend checklist/guided-flow. Slice 2 = extend `/me` + an `account` API (opt-in/profile/request-deletion) + a Settings page. Lean: delete = a `deletion_requested_at` flag (no cascade); notifications folded into opt-in.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (psycopg2), Postgres 55432, React 18 + TS + Vitest (pnpm).

**Spec:** `docs/superpowers/specs/2026-06-07-onboarding-settings-design.md`

**Conventions:** integration tests prefix `APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" REDIS_URL="redis://localhost:6379/0"`; migrations `ADMIN_DATABASE_URL=... uv run alembic upgrade head`; web `pnpm -C apps/web test -- run <f>` + `pnpm -C apps/web typecheck`. pytest `asyncio_mode=auto` (bare `async def test_`). Commit footer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Don't touch `.env`, root `.gitignore`, `tools/equity-screener`, `.omc`.

---

# Slice 1 — Onboarding

### Task 1: Migration `0014` — onboarding_progress + deletion flag

**Files:** Create `infra/migrations/versions/0014_onboarding.py`; Test `tests/integration/test_onboarding_migration.py`

- [ ] **Step 1: Create the migration** (mirror the baseline RLS pattern — FORCE RLS + `tenant_isolation` policy keyed on `app.current_tenant`):
```python
"""onboarding progress table + account deletion-request flag

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-07
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE onboarding_progress (
            tenant_id    UUID NOT NULL REFERENCES tenants(tenant_id),
            step         TEXT NOT NULL,
            completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, step)
        );
        ALTER TABLE onboarding_progress ENABLE ROW LEVEL SECURITY;
        ALTER TABLE onboarding_progress FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON onboarding_progress
          USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
          WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid);
        GRANT SELECT, INSERT, UPDATE, DELETE ON onboarding_progress TO saalr_app;

        ALTER TABLE users ADD COLUMN deletion_requested_at TIMESTAMPTZ;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE users DROP COLUMN IF EXISTS deletion_requested_at;
        DROP POLICY IF EXISTS tenant_isolation ON onboarding_progress;
        DROP TABLE IF EXISTS onboarding_progress;
    """)
```

- [ ] **Step 2: Apply** `ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" uv run alembic upgrade head` → `0013 -> 0014`.
- [ ] **Step 3: Round-trip** `... alembic downgrade -1` then `... alembic upgrade head` — both succeed; leave at head.
- [ ] **Step 4: Test** `tests/integration/test_onboarding_migration.py`:
```python
from sqlalchemy import text


async def test_onboarding_table_and_deletion_col_exist(admin_engine):
    async with admin_engine.begin() as conn:
        t = (await conn.execute(text("SELECT to_regclass('public.onboarding_progress')"))).scalar()
        col = (await conn.execute(text(
            "SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='deletion_requested_at'"
        ))).scalar()
    assert t is not None and col == 1
```
Run with env vars; PASS. `ruff check` the migration + test.
- [ ] **Step 5: Commit** `git add infra/migrations/versions/0014_onboarding.py tests/integration/test_onboarding_migration.py && git commit -m "feat(db): onboarding_progress table + deletion-request flag"`

---

### Task 2: Onboarding API

**Files:** Create `apps/api/saalr_api/onboarding/__init__.py` (empty), `repo.py`, `router.py`; Modify `apps/api/saalr_api/main.py`; Test `tests/integration/test_onboarding.py`

- [ ] **Step 1: Failing test** `tests/integration/test_onboarding.py`:
```python
import httpx
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_onboarding_complete_and_idempotent(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:ob1@x.com"}
            assert (await c.get("/onboarding", headers=h)).json() == {"steps": [], "all_done": False}
            r = await c.post("/onboarding/complete", json={"step": "build_strategy"}, headers=h)
            assert r.status_code == 200 and "build_strategy" in r.json()["steps"]
            await c.post("/onboarding/complete", json={"step": "build_strategy"}, headers=h)  # idempotent
            got = (await c.get("/onboarding", headers=h)).json()
            assert got["steps"].count("build_strategy") == 1 and got["all_done"] is False
            bad = await c.post("/onboarding/complete", json={"step": "nope"}, headers=h)
            assert bad.status_code == 400


async def test_onboarding_is_tenant_isolated(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            await c.post("/onboarding/complete", json={"step": "see_regime"},
                         headers={"Authorization": "Bearer dev:ob-a@x.com"})
            other = (await c.get("/onboarding", headers={"Authorization": "Bearer dev:ob-b@x.com"})).json()
    assert other["steps"] == []
```

- [ ] **Step 2: Run → FAIL** (404).
- [ ] **Step 3: Implement `apps/api/saalr_api/onboarding/repo.py`:**
```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ONBOARDING_STEPS = ("build_strategy", "see_regime", "paper_trade", "read_lesson")


async def list_steps(session: AsyncSession, tenant_id: UUID) -> list[str]:
    rows = (await session.execute(
        text("SELECT step FROM onboarding_progress WHERE tenant_id = :t"),
        {"t": str(tenant_id)},
    )).scalars().all()
    return list(rows)


async def mark_step(session: AsyncSession, tenant_id: UUID, step: str) -> None:
    await session.execute(
        text("INSERT INTO onboarding_progress (tenant_id, step) VALUES (:t, :s) "
             "ON CONFLICT (tenant_id, step) DO NOTHING"),
        {"t": str(tenant_id), "s": step},
    )
```

- [ ] **Step 4: Implement `apps/api/saalr_api/onboarding/router.py`:**
```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from ..auth.dependency import get_principal
from . import repo

router = APIRouter(tags=["onboarding"])


class CompleteRequest(BaseModel):
    step: str


def _payload(steps: list[str]) -> dict:
    return {"steps": steps, "all_done": all(s in steps for s in repo.ONBOARDING_STEPS)}


@router.get("/onboarding")
async def get_onboarding(ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    return _payload(await repo.list_steps(session, principal.tenant_id))


@router.post("/onboarding/complete")
async def complete(body: CompleteRequest,
                   ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    if body.step not in repo.ONBOARDING_STEPS:
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "unknown onboarding step"}})
    await repo.mark_step(session, principal.tenant_id, body.step)
    return _payload(await repo.list_steps(session, principal.tenant_id))
```
Create empty `apps/api/saalr_api/onboarding/__init__.py`.

- [ ] **Step 5: Mount in `main.py`** — `from .onboarding.router import router as onboarding_router` with the router imports, and `app.include_router(onboarding_router)` with the others.
- [ ] **Step 6: Run → PASS** the test with env vars (flush not needed). `ruff check` the new files + main.py.
- [ ] **Step 7: Commit** `git add apps/api/saalr_api/onboarding apps/api/saalr_api/main.py tests/integration/test_onboarding.py && git commit -m "feat(api): onboarding progress endpoints (idempotent, RLS-isolated)"`

---

### Task 3: Onboarding frontend — checklist on Dashboard

**Files:** Create `apps/web/src/lib/onboarding.ts`, `apps/web/src/features/onboarding/hooks.ts`, `apps/web/src/features/onboarding/GettingStarted.tsx`, `apps/web/src/features/onboarding/GettingStarted.test.tsx`; Modify `apps/web/src/pages/Dashboard.tsx`

- [ ] **Step 1: `lib/onboarding.ts`** (mirror the `request<T>` helper pattern from `lib/billing.ts` — import `BASE`, `authHeaders` from `./api`):
```ts
import { BASE, authHeaders } from './api'

export const ONBOARDING_STEPS = ['build_strategy', 'see_regime', 'paper_trade', 'read_lesson'] as const
export type OnboardingStep = (typeof ONBOARDING_STEPS)[number]
export interface Onboarding { steps: string[]; all_done: boolean }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init, headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (!res.ok) throw new Error(`onboarding ${res.status}`)
  return (await res.json()) as T
}

export function getOnboarding(): Promise<Onboarding> { return req('/onboarding') }
export function completeStep(step: OnboardingStep): Promise<Onboarding> {
  return req('/onboarding/complete', { method: 'POST', body: JSON.stringify({ step }) })
}
```

- [ ] **Step 2: `features/onboarding/hooks.ts`:**
```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getOnboarding, completeStep, type OnboardingStep } from '../../lib/onboarding'

export function useOnboarding(enabled: boolean) {
  return useQuery({ queryKey: ['onboarding'], queryFn: getOnboarding, enabled, retry: false })
}

export function useCompleteStep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (step: OnboardingStep) => completeStep(step),
    onSuccess: (data) => qc.setQueryData(['onboarding'], data),
  })
}
```

- [ ] **Step 3: Failing test** `features/onboarding/GettingStarted.test.tsx`:
```tsx
import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { GettingStarted } from './GettingStarted'
import * as ob from '../../lib/onboarding'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

describe('GettingStarted', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('shows the 4 steps with one completed', async () => {
    vi.spyOn(ob, 'getOnboarding').mockResolvedValue({ steps: ['build_strategy'], all_done: false })
    render(wrap(<GettingStarted />))
    expect(await screen.findByTestId('getting-started')).toBeInTheDocument()
    expect(screen.getAllByTestId(/^ob-step-/)).toHaveLength(4)
  })

  it('hides when all_done', async () => {
    vi.spyOn(ob, 'getOnboarding').mockResolvedValue({ steps: [...ob.ONBOARDING_STEPS], all_done: true })
    render(wrap(<GettingStarted />))
    await waitFor(() => expect(screen.queryByTestId('getting-started')).toBeNull())
  })

  it('hides after dismiss', async () => {
    vi.spyOn(ob, 'getOnboarding').mockResolvedValue({ steps: [], all_done: false })
    render(wrap(<GettingStarted />))
    fireEvent.click(await screen.findByTestId('ob-dismiss'))
    await waitFor(() => expect(screen.queryByTestId('getting-started')).toBeNull())
  })
})
```

- [ ] **Step 4: Run → FAIL.**
- [ ] **Step 5: Implement `features/onboarding/GettingStarted.tsx`:**
```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useOnboarding } from './hooks'
import { ONBOARDING_STEPS } from '../../lib/onboarding'

const META: Record<string, { label: string; to: string }> = {
  build_strategy: { label: 'Build your first strategy', to: '/strategies' },
  see_regime: { label: 'See a ticker’s market regime', to: '/ideas' },
  paper_trade: { label: 'Paper-trade a strategy', to: '/start' },
  read_lesson: { label: 'Read an OptionsAcademy lesson', to: '/education' },
}
const KEY = 'saalr.onboarding.dismissed'

export function GettingStarted() {
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(KEY) === '1')
  const { data } = useOnboarding(!dismissed)
  if (dismissed || !data || data.all_done) return null
  const done = new Set(data.steps)
  return (
    <div className="rounded-lg border border-accent/40 bg-accent/5 p-4" data-testid="getting-started">
      <div className="mb-2 flex items-center justify-between">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
          Getting started · {data.steps.filter((s) => s in META).length}/{ONBOARDING_STEPS.length}
        </p>
        <button data-testid="ob-dismiss" onClick={() => { localStorage.setItem(KEY, '1'); setDismissed(true) }}
          className="text-[11px] text-txtFaint hover:text-txt">Dismiss</button>
      </div>
      <ul className="space-y-1.5">
        {ONBOARDING_STEPS.map((s) => (
          <li key={s} data-testid={`ob-step-${s}`} className="flex items-center gap-2 text-sm">
            <span className={done.has(s) ? 'text-pos' : 'text-txtFaint'}>{done.has(s) ? '✓' : '○'}</span>
            {done.has(s)
              ? <span className="text-txtDim line-through">{META[s].label}</span>
              : <Link to={META[s].to} className="text-txt hover:text-accent">{META[s].label} →</Link>}
          </li>
        ))}
      </ul>
    </div>
  )
}
```

- [ ] **Step 6: Wire into `Dashboard.tsx`** — import `GettingStarted` and render `<GettingStarted />` as the first child of the dashboard's top-level container (above `StatStrip`).
- [ ] **Step 7: Run → PASS** `pnpm -C apps/web test -- run src/features/onboarding src/pages/Dashboard` + `pnpm -C apps/web typecheck`.
- [ ] **Step 8: Commit** the 4 new files + Dashboard.tsx: `git commit -m "feat(web): getting-started onboarding checklist on Dashboard"`

---

### Task 4: Guided `/app/start` flow + completeStep wiring

**Files:** Create `apps/web/src/pages/Start.tsx`, `apps/web/src/pages/Start.test.tsx`; Modify `apps/web/src/app/Router.tsx`; Modify the action sites (`pages/Strategies.tsx`, `features/ideas/RecoCard.tsx` or wherever paper-trade succeeds, `pages/Ideas.tsx`, `pages/Education.tsx`)

- [ ] **Step 1: Read** `pages/Ideas.tsx` + its regime/recommendation hooks and `features/portfolio/usePaperTrade.ts` (`usePaperTradeStrategy`) to learn the exact hook signatures the guided flow will reuse.
- [ ] **Step 2: Build `pages/Start.tsx`** — a linear flow with local `step` state (0=ticker, 1=regime+reco, 2=trade, 3=done):
  - Step 0: a ticker input → "See its regime".
  - Step 1: call the same regime + top-recommendation hook(s) Ideas uses for that ticker; on load, `useCompleteStep().mutate('see_regime')` (once). Show the regime + the #1 recommended template with a "Paper-trade this" button.
  - Step 2: call `usePaperTradeStrategy()` with the recommended config; on success `completeStep('paper_trade')` and advance.
  - Step 3: a done panel with `<Link to="/portfolio">View your positions →</Link>`.
  Add `data-testid` per step (`start-step-ticker`, `start-step-regime`, `start-step-done`).
- [ ] **Step 3: Route** — in `Router.tsx` add `<Route path="start" element={<Start />} />` (import `Start`) inside the `RequireAuth`/`AppShell` block.
- [ ] **Step 4: completeStep at action sites** (each guarded so it fires once; backend is idempotent):
  - `Strategies.tsx` save success (`create.mutate(..., { onSuccess })`) → `completeStep('build_strategy')`.
  - paper-trade success (the `usePaperTradeStrategy` `onSuccess` in `RecoCard`/`Strategies`/`Start`) → `completeStep('paper_trade')`.
  - `Ideas.tsx` once a regime result is loaded → `completeStep('see_regime')`.
  - `Education.tsx` when a lesson is opened/selected → `completeStep('read_lesson')`.
  Use `useCompleteStep()` and a `useRef` "already fired" guard per component to avoid loops.
- [ ] **Step 5: Test `Start.test.tsx`** — renders step 0 (ticker input); entering a ticker + stubbing the regime/reco fetch advances to the regime step and calls `completeStep('see_regime')` (spy on `lib/onboarding.completeStep`). Mirror the mock pattern used in `Ideas.test.tsx`.
- [ ] **Step 6: Run → PASS** `pnpm -C apps/web test -- run src/pages/Start src/pages/Strategies src/pages/Ideas src/pages/Education src/features/ideas` + `pnpm -C apps/web typecheck`. Fix any existing test affected by the added `completeStep` call (mock `lib/onboarding` where needed so it no-ops).
- [ ] **Step 7: Commit** the new + modified files: `git commit -m "feat(web): guided /app/start activation flow + onboarding step wiring"`

---

# Slice 2 — Account / Settings

### Task 5: Account API — extend /me + opt-in/profile/request-deletion

**Files:** Modify `apps/api/saalr_api/main.py` (the `/me` handler); Create `apps/api/saalr_api/account/__init__.py` (empty), `apps/api/saalr_api/account/router.py`; Test `tests/integration/test_account.py`

- [ ] **Step 1: Extend `/me`** — in the `me()` handler in `main.py`, after the tenant fetch, also fetch the user row and include the new fields. Add to the returned dict:
```python
        urow = (await session.execute(
            text("SELECT marketing_opt_in, preferred_tz, preferred_locale, deletion_requested_at "
                 "FROM users WHERE user_id = :u"),
            {"u": str(principal.user_id)},
        )).first()
        # ... existing return dict, add:
        #   "marketing_opt_in": bool(urow.marketing_opt_in) if urow else False,
        #   "preferred_tz": urow.preferred_tz if urow else "UTC",
        #   "preferred_locale": urow.preferred_locale if urow else "en-US",
        #   "deletion_requested": bool(urow.deletion_requested_at) if urow and urow.deletion_requested_at else False,
```

- [ ] **Step 2: Failing test** `tests/integration/test_account.py`:
```python
import httpx
from sqlalchemy import text
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_me_includes_account_fields(app_sessionmaker):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            me = (await c.get("/me", headers={"Authorization": "Bearer dev:acc1@x.com"})).json()
    assert me["marketing_opt_in"] is False and me["preferred_tz"] and me["deletion_requested"] is False


async def test_opt_in_profile_and_deletion(app_sessionmaker, admin_engine):
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            h = {"Authorization": "Bearer dev:acc2@x.com"}
            await c.get("/me", headers=h)
            assert (await c.post("/me/marketing/opt-in", json={"opt_in": True}, headers=h)).status_code == 200
            assert (await c.get("/me", headers=h)).json()["marketing_opt_in"] is True
            assert (await c.patch("/me/profile", json={"preferred_tz": "America/New_York"}, headers=h)).status_code == 200
            assert (await c.get("/me", headers=h)).json()["preferred_tz"] == "America/New_York"
            bad = await c.patch("/me/profile", json={"nope": "x"}, headers=h)
            assert bad.status_code == 422
            assert (await c.post("/me/request-deletion", headers=h)).json()["requested"] is True
            assert (await c.get("/me", headers=h)).json()["deletion_requested"] is True
```

- [ ] **Step 3: Run → FAIL.**
- [ ] **Step 4: Implement `apps/api/saalr_api/account/router.py`:**
```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from ..auth.dependency import get_principal

router = APIRouter(tags=["account"])


class OptInRequest(BaseModel):
    opt_in: bool


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown keys -> 422
    preferred_tz: str | None = Field(default=None, max_length=64)
    preferred_locale: str | None = Field(default=None, max_length=64)


@router.post("/me/marketing/opt-in")
async def set_opt_in(body: OptInRequest,
                     ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    async with session.begin():
        await session.execute(
            text("UPDATE users SET marketing_opt_in = :v WHERE user_id = :u"),
            {"v": body.opt_in, "u": str(principal.user_id)},
        )
    return {"marketing_opt_in": body.opt_in}


@router.patch("/me/profile")
async def patch_profile(body: ProfilePatch,
                        ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    fields = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if fields:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        async with session.begin():
            await session.execute(
                text(f"UPDATE users SET {sets} WHERE user_id = :u"),
                {**fields, "u": str(principal.user_id)},
            )
    return {"updated": list(fields)}


@router.post("/me/request-deletion")
async def request_deletion(ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    async with session.begin():
        await session.execute(
            text("UPDATE users SET deletion_requested_at = now() "
                 "WHERE user_id = :u AND deletion_requested_at IS NULL"),
            {"u": str(principal.user_id)},
        )
    return {"requested": True}
```
NOTE: `get_principal` yields a session already inside a transaction context (it sets the GUC in `session.begin()` then yields). If `async with session.begin()` errors with "already in a transaction", drop the explicit `session.begin()` blocks here and rely on the dependency's transaction (the writes will commit when the dependency's context exits). Verify against how other write endpoints (e.g. oms) use the session: match that pattern. Create empty `account/__init__.py`.

- [ ] **Step 5: Mount in `main.py`** — `from .account.router import router as account_router` + `app.include_router(account_router)`.
- [ ] **Step 6: Run → PASS** with env vars. `ruff check` new files + main.py.
- [ ] **Step 7: Commit** `git add apps/api/saalr_api/account apps/api/saalr_api/main.py tests/integration/test_account.py && git commit -m "feat(api): account fields on /me + opt-in/profile/request-deletion"`

---

### Task 6: Settings page

**Files:** Create `apps/web/src/lib/account.ts`, `apps/web/src/features/account/hooks.ts`, `apps/web/src/pages/Settings.tsx`, `apps/web/src/pages/Settings.test.tsx`; Modify `apps/web/src/app/Router.tsx`, `apps/web/src/lib/api.ts` (extend `Me` type), and the app nav (add a Settings link).

- [ ] **Step 1: Extend the `Me` type** in `apps/web/src/lib/api.ts` with the new optional fields:
```ts
  marketing_opt_in?: boolean
  preferred_tz?: string
  preferred_locale?: string
  deletion_requested?: boolean
```

- [ ] **Step 2: `lib/account.ts`** (reuse the `req`/auth pattern):
```ts
import { BASE, authHeaders } from './api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init, headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (!res.ok) throw new Error(`account ${res.status}`)
  return (await res.json()) as T
}

export function setOptIn(opt_in: boolean) { return req('/me/marketing/opt-in', { method: 'POST', body: JSON.stringify({ opt_in }) }) }
export function updateProfile(p: { preferred_tz?: string; preferred_locale?: string }) {
  return req('/me/profile', { method: 'PATCH', body: JSON.stringify(p) })
}
export function requestDeletion() { return req('/me/request-deletion', { method: 'POST' }) }
```

- [ ] **Step 3: `features/account/hooks.ts`** — `useOptIn()`, `useUpdateProfile()`, `useRequestDeletion()` mutations that call `useAuth().refresh()` (re-fetch `/me`) on success so the UI reflects server state.

- [ ] **Step 4: Failing test** `pages/Settings.test.tsx` — mock `useAuth` to return `me` with `marketing_opt_in:false, preferred_tz:'UTC', tier:'pro', user:{email}`; assert the page renders an Account section (email/tier), a Profile section, an Email-preferences toggle (`data-testid="optin-toggle"`), and a Danger-zone with a delete button that is **disabled until** the user types `DELETE` (`data-testid="delete-confirm-input"` → `data-testid="delete-request-btn"`). Mirror the mock pattern in `Models.test.tsx`/`Billing.test.tsx`.

- [ ] **Step 5: Implement `pages/Settings.tsx`** — four sections (Account / Profile / Email preferences / Danger zone) using the hooks; the opt-in toggle reflects `me.marketing_opt_in`; "Manage subscription" uses `usePortal()` (from `features/billing/hooks`) or a `<Link to="/billing">`; delete button enabled only when the confirm input === 'DELETE', and after success shows "Deletion requested." Use existing Tailwind tokens/classes.

- [ ] **Step 6: Route + nav** — `Router.tsx` add `<Route path="settings" element={<Settings />} />`; add a "Settings" link to the app nav (find the nav in `app/AppShell` or the nav component; mirror the existing nav-item pattern).

- [ ] **Step 7: Run → PASS** `pnpm -C apps/web test -- run src/pages/Settings src/features/account` + `pnpm -C apps/web typecheck`.
- [ ] **Step 8: Commit** the new + modified files: `git commit -m "feat(web): account/settings page (opt-in, profile, manage sub, request-deletion)"`

---

## Final verification
- [ ] `python -m pytest tests/integration/test_onboarding.py tests/integration/test_account.py tests/integration/test_onboarding_migration.py -q` (env vars) — green.
- [ ] `pnpm -C apps/web test -- run src/features/onboarding src/features/account src/pages/Start src/pages/Settings src/pages/Dashboard` + `pnpm -C apps/web typecheck` — green/clean.
- [ ] Final code-reviewer over the whole diff.
- [ ] Note to founder: restart the dev API to serve the new `/me` fields + onboarding/account routes.

## Self-review notes
- **Spec coverage:** migration→T1; onboarding API→T2; checklist→T3; guided flow + wiring→T4; account API→T5; Settings page→T6. ✅
- **Type/contract consistency:** `ONBOARDING_STEPS` shared (repo.py ↔ lib/onboarding.ts); `_payload` all_done logic matches the canonical 4; `/me` new fields (T5) match the `Me` type extension + Settings consumption (T6); `ProfilePatch extra="forbid"` gives the 422 the test asserts. ✅
- **RLS:** onboarding_progress follows the baseline FORCE-RLS + tenant_isolation pattern; `users` writes are keyed by user_id (users not tenant-scoped), matching `/unsubscribe`. ✅
- **Lean:** delete = flag only; notifications folded into opt-in. ✅
