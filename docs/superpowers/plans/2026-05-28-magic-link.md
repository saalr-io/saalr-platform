# Passwordless Magic Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a self-hosted email magic link for dev (Redis one-time tokens) that verifies email ownership and issues the existing `dev:<email>` session; prod stays on Clerk.

**Architecture:** Two dev-gated endpoints — `/auth/magic/request` stores a single-use token in Redis (15-min TTL) and returns/logs a verify link; `/auth/magic/verify` atomically `GETDEL`s it and returns the session token. The frontend Login sends the link and a `/auth/verify` route exchanges it. The auth adapter, `/me`, and RLS are unchanged.

**Tech Stack:** FastAPI, redis-py (`redis.asyncio`), React + TS, Vitest, pytest (real Redis).

**Spec:** `docs/superpowers/specs/2026-05-28-magic-link-design.md`

---

## File Structure

| Path | Responsibility |
|---|---|
| `packages/core/saalr_core/config.py` | add `redis_url`, `magic_link_ttl_seconds`, `web_base_url` |
| `apps/api/pyproject.toml` | add `redis>=5` |
| `apps/api/saalr_api/auth/magic.py` | `request_link` / `consume_link` Redis service |
| `apps/api/saalr_api/main.py` | redis in lifespan; `/auth/magic/request` + `/auth/magic/verify` |
| `tests/integration/test_magic_link.py` | request/verify/single-use/expiry/clerk-404 (real Redis) |
| `apps/web/src/lib/api.ts` | `requestMagicLink`, `verifyMagicLink` |
| `apps/web/src/auth/AuthContext.tsx` | `requestLink`, `completeLink` on the context |
| `apps/web/src/pages/Login.tsx` | send-link + check-email + dev-link button |
| `apps/web/src/pages/VerifyMagicLink.tsx` | `/auth/verify` route — exchange token |
| `apps/web/src/main.tsx` | add public `/auth/verify` route |
| `apps/web/src/components/RequireAuth.test.tsx` | update mocked context shape |
| `apps/web/src/pages/Login.test.tsx`, `VerifyMagicLink.test.tsx` | frontend tests |

---

## Task 1: Backend config + Redis service

**Files:** Modify `packages/core/saalr_core/config.py`, `apps/api/pyproject.toml`; Create `apps/api/saalr_api/auth/magic.py`.

- [ ] **Step 1: Add settings**

In `packages/core/saalr_core/config.py`, inside `Settings` (after the clerk fields), add:
```python
    # Magic link (dev)
    redis_url: str = "redis://localhost:6379/0"
    magic_link_ttl_seconds: int = 900
    web_base_url: str = "http://localhost:5174"
```

- [ ] **Step 2: Add the redis dependency**

In `apps/api/pyproject.toml`, change the `dependencies` list to include redis:
```toml
dependencies = [
  "saalr-core",
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "pyjwt[crypto]>=2.9",
  "redis>=5",
]
```

- [ ] **Step 3: Create the magic-link service**

`apps/api/saalr_api/auth/magic.py`:
```python
import secrets

from redis.asyncio import Redis

_PREFIX = "magiclink:"


async def request_link(redis: Redis, email: str, ttl_seconds: int) -> str:
    """Create a single-use token mapping to the email, with a TTL. Returns the token."""
    token = secrets.token_urlsafe(32)
    await redis.set(f"{_PREFIX}{token}", email, ex=ttl_seconds)
    return token


async def consume_link(redis: Redis, token: str) -> str | None:
    """Atomically fetch-and-delete the token's email (single-use). None if absent/expired."""
    return await redis.getdel(f"{_PREFIX}{token}")
```

- [ ] **Step 4: Install + sanity import**

Run: `cd "c:/Users/sreek/myprojects/saalr-demo/SAALR F2F" && uv sync && uv run python -c "import redis.asyncio; from saalr_api.auth import magic; print('ok')"`
Expected: prints `ok` (redis installed, module imports).

- [ ] **Step 5: Commit**

```bash
git add packages/core/saalr_core/config.py apps/api/pyproject.toml apps/api/saalr_api/auth/magic.py uv.lock
git commit -m "feat(auth): redis-backed magic-link token service + config"
```

---

## Task 2: Backend endpoints + tests (real Redis)

**Files:** Modify `apps/api/saalr_api/main.py`; Test `tests/integration/test_magic_link.py`.

- [ ] **Step 1: Write the failing tests**

`tests/integration/test_magic_link.py`:
```python
import os

import httpx
import pytest_asyncio
import redis.asyncio as aioredis

from saalr_api.main import create_app

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture(autouse=True)
async def _flush_magic():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    async for k in r.scan_iter("magiclink:*"):
        await r.delete(k)
    yield
    async for k in r.scan_iter("magiclink:*"):
        await r.delete(k)
    await r.aclose()


async def test_request_then_verify_issues_session_token():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            r = await c.post("/auth/magic/request", json={"email": "Alice@Acme.com"})
            assert r.status_code == 200
            body = r.json()
            assert body["sent"] is True
            assert "/auth/verify?token=" in body["dev_link"]
            token = body["dev_link"].split("token=", 1)[1]

            v = await c.post("/auth/magic/verify", json={"token": token})
            assert v.status_code == 200
            assert v.json()["token"] == "dev:alice@acme.com"


async def test_link_is_single_use():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            token = (
                await c.post("/auth/magic/request", json={"email": "b@x.com"})
            ).json()["dev_link"].split("token=", 1)[1]
            assert (await c.post("/auth/magic/verify", json={"token": token})).status_code == 200
            assert (await c.post("/auth/magic/verify", json={"token": token})).status_code == 410


async def test_garbage_token_is_410():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            assert (await c.post("/auth/magic/verify", json={"token": "nope"})).status_code == 410


async def test_endpoints_404_under_clerk(monkeypatch):
    monkeypatch.setenv("AUTH_PROVIDER", "clerk")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://example.com/.well-known/jwks.json")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client(app) as c:
            assert (await c.post("/auth/magic/request", json={"email": "a@b.com"})).status_code == 404
            assert (await c.post("/auth/magic/verify", json={"token": "x"})).status_code == 404
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd "c:/Users/sreek/myprojects/saalr-demo/SAALR F2F" && uv run pytest tests/integration/test_magic_link.py -q`
Expected: FAIL — endpoints return 404/405 (not implemented yet).

- [ ] **Step 3: Wire Redis into the lifespan**

In `apps/api/saalr_api/main.py`, update imports and the lifespan. Add to the top imports:
```python
import logging

import redis.asyncio as aioredis

from .auth.magic import consume_link, request_link
```
Replace the `lifespan` function body so it also creates/closes redis:
```python
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_engine(settings.app_database_url)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.auth_provider = get_auth_provider(settings)
        app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        yield
        await app.state.redis.aclose()
        await engine.dispose()
```

- [ ] **Step 4: Add the endpoints + request models**

In `apps/api/saalr_api/main.py`, add a module-level logger after `_EMAIL_RE`:
```python
_logger = logging.getLogger("saalr.auth")
```
Add the request models next to `DevLoginRequest`:
```python
class MagicRequest(BaseModel):
    email: str


class MagicVerify(BaseModel):
    token: str
```
Add the endpoints inside `create_app` (after `dev_login`):
```python
    @app.post("/auth/magic/request")
    async def magic_request(body: MagicRequest) -> dict:
        if settings.auth_provider != "dev":
            raise HTTPException(status_code=404, detail="not found")
        email = body.email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise HTTPException(
                status_code=422,
                detail={"error": {"code": "VALIDATION_INVALID_EMAIL", "message": "invalid email"}},
            )
        token = await request_link(app.state.redis, email, settings.magic_link_ttl_seconds)
        verify_url = f"{settings.web_base_url}/auth/verify?token={token}"
        _logger.info("magic link for %s -> %s", email, verify_url)
        return {"sent": True, "dev_link": verify_url}

    @app.post("/auth/magic/verify")
    async def magic_verify(body: MagicVerify) -> dict:
        if settings.auth_provider != "dev":
            raise HTTPException(status_code=404, detail="not found")
        email = await consume_link(app.state.redis, body.token)
        if email is None:
            raise HTTPException(
                status_code=410,
                detail={"error": {"code": "AUTH_MAGIC_LINK_INVALID", "message": "link is invalid or expired"}},
            )
        return {"token": f"dev:{email}"}
```

- [ ] **Step 5: Run it to verify it passes**

Run: `cd "c:/Users/sreek/myprojects/saalr-demo/SAALR F2F" && uv run pytest tests/integration/test_magic_link.py -q && uv run ruff check .`
Expected: 4 passed; ruff clean. (Docker Redis must be up: `docker compose -f infra/docker/docker-compose.yml up -d`.)

- [ ] **Step 6: Commit**

```bash
git add apps/api/saalr_api/main.py tests/integration/test_magic_link.py
git commit -m "feat(auth): dev magic-link request/verify endpoints"
```

---

## Task 3: Frontend API + auth context methods

**Files:** Modify `apps/web/src/lib/api.ts`, `apps/web/src/auth/AuthContext.tsx`, `apps/web/src/components/RequireAuth.test.tsx`.

- [ ] **Step 1: Add API functions**

Append to `apps/web/src/lib/api.ts`:
```typescript
export async function requestMagicLink(email: string): Promise<{ sent: boolean; dev_link?: string }> {
  const res = await fetch(`${BASE}/auth/magic/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) throw new Error(`magic request failed: ${res.status}`)
  return (await res.json()) as { sent: boolean; dev_link?: string }
}

export async function verifyMagicLink(token: string): Promise<string> {
  const res = await fetch(`${BASE}/auth/magic/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (!res.ok) throw new Error(`magic verify failed: ${res.status}`)
  return ((await res.json()) as { token: string }).token
}
```

- [ ] **Step 2: Extend the auth context**

In `apps/web/src/auth/AuthContext.tsx`:

(a) update imports:
```typescript
import { devLogin, getMe, requestMagicLink, verifyMagicLink, type Me } from '../lib/api'
```
(b) extend the interface:
```typescript
export interface AuthContextValue {
  status: AuthStatus
  me: Me | null
  login: (email?: string) => Promise<void>
  requestLink: (email: string) => Promise<{ dev_link?: string }>
  completeLink: (token: string) => Promise<void>
  logout: () => void
}
```
(c) in `DevAuthProvider`, add these callbacks (before the `return`) and include them in the provider value:
```typescript
  const requestLink = useCallback(async (email: string) => {
    return await requestMagicLink(email)
  }, [])

  const completeLink = useCallback(
    async (token: string) => {
      const sessionToken = await verifyMagicLink(token)
      setToken(sessionToken)
      await refresh()
    },
    [refresh],
  )
```
and change the provider element to:
```tsx
    <AuthContext.Provider value={{ status, me, login, requestLink, completeLink, logout }}>
      {children}
    </AuthContext.Provider>
```

- [ ] **Step 3: Update the RequireAuth test mock shape**

In `apps/web/src/components/RequireAuth.test.tsx`, both `mockUseAuth.mockReturnValue({...})` calls must include the new fields. Replace each `{ status: '...', me: null, login: vi.fn(), logout: vi.fn() }` with:
```typescript
{ status: 'anon', me: null, login: vi.fn(), requestLink: vi.fn(), completeLink: vi.fn(), logout: vi.fn() }
```
(use `status: 'authed'` for the second test).

- [ ] **Step 4: Typecheck**

Run: `cd apps/web && pnpm typecheck`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/api.ts apps/web/src/auth/AuthContext.tsx apps/web/src/components/RequireAuth.test.tsx
git commit -m "feat(web): auth context requestLink/completeLink + magic API"
```

---

## Task 4: Login (send link) + verify route

**Files:** Modify `apps/web/src/pages/Login.tsx`, `apps/web/src/main.tsx`; Create `apps/web/src/pages/VerifyMagicLink.tsx`.

- [ ] **Step 1: Rewrite the Login page**

`apps/web/src/pages/Login.tsx`:
```tsx
import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'

export function Login() {
  const { requestLink } = useAuth()
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)
  const [devLink, setDevLink] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const r = await requestLink(email.trim().toLowerCase())
      setDevLink(r.dev_link ?? null)
      setSent(true)
    } catch {
      setError('Could not send the link — is the API running?')
    } finally {
      setBusy(false)
    }
  }

  const Brand = (
    <div className="flex items-center gap-2.5">
      <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-pos to-accent text-sm font-extrabold text-[#04110d]">
        S
      </span>
      <span className="font-semibold tracking-tight">Saalr</span>
      <span className="font-mono text-[9px] tracking-[2.5px] text-txtFaint">RESEARCH&nbsp;TERMINAL</span>
    </div>
  )

  if (sent) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="w-[360px] rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-6">
          {Brand}
          <h1 className="mt-6 text-lg font-semibold">Check your email</h1>
          <p className="mt-1 text-xs text-txtDim">
            We sent a one-time sign-in link to <span className="text-txt">{email}</span>.
          </p>
          {devLink && (
            <a
              href={devLink}
              className="mt-4 block w-full rounded-lg bg-gradient-to-br from-pos to-accent py-2 text-center text-sm font-semibold text-[#04110d]"
            >
              Dev: open magic link
            </a>
          )}
          <button
            type="button"
            onClick={() => setSent(false)}
            className="mt-3 w-full text-center text-[11px] text-txtFaint hover:text-txtDim"
          >
            Use a different email
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="grid min-h-screen place-items-center">
      <form
        onSubmit={onSubmit}
        className="w-[360px] rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-6"
      >
        {Brand}
        <h1 className="mt-6 text-lg font-semibold">Sign in</h1>
        <p className="mt-1 text-xs text-txtDim">Passwordless — we'll email you a one-time link.</p>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="mt-4 w-full rounded-lg border border-line bg-canvas px-3 py-2 text-sm outline-none focus:border-accent"
        />
        {error && <p className="mt-2 text-[11px] text-neg">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="mt-4 w-full rounded-lg bg-gradient-to-br from-pos to-accent py-2 text-sm font-semibold text-[#04110d] disabled:opacity-60"
        >
          {busy ? 'Sending…' : 'Send magic link'}
        </button>
      </form>
    </div>
  )
}
```

- [ ] **Step 2: Create the verify route**

`apps/web/src/pages/VerifyMagicLink.tsx`:
```tsx
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function VerifyMagicLink() {
  const { completeLink } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return // guard StrictMode double-invoke (token is single-use)
    ran.current = true
    const token = params.get('token')
    if (!token) {
      setError('Missing token.')
      return
    }
    completeLink(token)
      .then(() => navigate('/', { replace: true }))
      .catch(() => setError('This link is invalid or expired.'))
  }, [completeLink, params, navigate])

  return (
    <div className="grid min-h-screen place-items-center text-sm text-txtDim">
      {error ? (
        <div className="text-center">
          <p className="text-neg">{error}</p>
          <Link to="/login" className="mt-2 inline-block text-accent">
            Back to sign in
          </Link>
        </div>
      ) : (
        'Signing you in…'
      )}
    </div>
  )
}
```

- [ ] **Step 3: Register the route**

In `apps/web/src/main.tsx`, add the import and a public route (sibling of `/login`, outside `RequireAuth`):
```tsx
import { VerifyMagicLink } from './pages/VerifyMagicLink'
```
and below the `<Route path="/login" ... />` line add:
```tsx
            <Route path="/auth/verify" element={<VerifyMagicLink />} />
```

- [ ] **Step 4: Typecheck + build**

Run: `cd apps/web && pnpm typecheck && pnpm build`
Expected: clean typecheck; `dist/` builds.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/Login.tsx apps/web/src/pages/VerifyMagicLink.tsx apps/web/src/main.tsx
git commit -m "feat(web): magic-link login (send link + /auth/verify exchange)"
```

---

## Task 5: Frontend tests

**Files:** Create `apps/web/src/pages/Login.test.tsx`, `apps/web/src/pages/VerifyMagicLink.test.tsx`.

- [ ] **Step 1: Login test**

`apps/web/src/pages/Login.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../auth/AuthContext', () => ({ useAuth: vi.fn() }))

import { useAuth } from '../auth/AuthContext'
import { Login } from './Login'

const mockUseAuth = vi.mocked(useAuth)

beforeEach(() => mockUseAuth.mockReset())

describe('Login', () => {
  it('sends a magic link and shows the dev link', async () => {
    const requestLink = vi.fn().mockResolvedValue({ dev_link: 'http://localhost:5174/auth/verify?token=abc' })
    mockUseAuth.mockReturnValue({
      status: 'anon',
      me: null,
      login: vi.fn(),
      requestLink,
      completeLink: vi.fn(),
      logout: vi.fn(),
    })
    render(<Login />)
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'alice@acme.com' },
    })
    fireEvent.click(screen.getByText('Send magic link'))
    await waitFor(() => expect(screen.getByText('Check your email')).toBeInTheDocument())
    expect(requestLink).toHaveBeenCalledWith('alice@acme.com')
    const link = screen.getByText('Dev: open magic link') as HTMLAnchorElement
    expect(link.getAttribute('href')).toContain('/auth/verify?token=abc')
  })
})
```

- [ ] **Step 2: Verify-route test**

`apps/web/src/pages/VerifyMagicLink.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../auth/AuthContext', () => ({ useAuth: vi.fn() }))

import { useAuth } from '../auth/AuthContext'
import { VerifyMagicLink } from './VerifyMagicLink'

const mockUseAuth = vi.mocked(useAuth)

beforeEach(() => mockUseAuth.mockReset())

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/auth/verify" element={<VerifyMagicLink />} />
        <Route path="/" element={<div>HOME</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('VerifyMagicLink', () => {
  it('exchanges the token and navigates home', async () => {
    const completeLink = vi.fn().mockResolvedValue(undefined)
    mockUseAuth.mockReturnValue({
      status: 'anon',
      me: null,
      login: vi.fn(),
      requestLink: vi.fn(),
      completeLink,
      logout: vi.fn(),
    })
    renderAt('/auth/verify?token=abc')
    await waitFor(() => expect(screen.getByText('HOME')).toBeInTheDocument())
    expect(completeLink).toHaveBeenCalledWith('abc')
  })

  it('shows an error on an invalid link', async () => {
    const completeLink = vi.fn().mockRejectedValue(new Error('410'))
    mockUseAuth.mockReturnValue({
      status: 'anon',
      me: null,
      login: vi.fn(),
      requestLink: vi.fn(),
      completeLink,
      logout: vi.fn(),
    })
    renderAt('/auth/verify?token=bad')
    await waitFor(() =>
      expect(screen.getByText('This link is invalid or expired.')).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 3: Run web tests**

Run: `cd apps/web && pnpm test:run`
Expected: PASS (all suites, incl. the 3 new tests).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/pages/Login.test.tsx apps/web/src/pages/VerifyMagicLink.test.tsx
git commit -m "test(web): magic-link login + verify route"
```

---

## Task 6: Full verification

- [ ] **Step 1: Backend gate**

```bash
cd "c:/Users/sreek/myprojects/saalr-demo/SAALR F2F"
docker compose -f infra/docker/docker-compose.yml up -d
export ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/saalr"
export APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:5432/saalr"
uv run alembic upgrade head && uv run ruff check . && uv run pytest -q
```
Expected: migrations clean; ruff clean; all tests pass (incl. 4 magic-link tests).

- [ ] **Step 2: Web gate**

```bash
cd apps/web && pnpm typecheck && pnpm lint && pnpm test:run && pnpm build
```
Expected: all green.

- [ ] **Step 3: Manual end-to-end (the UI verification)**

Start the API (`uv run uvicorn saalr_api.main:create_app --factory --port 8000`) and web (`cd apps/web && pnpm dev`). In the browser:
- Open the app → redirected to **/login**.
- Enter an email → **Send magic link** → "Check your email" appears with a **Dev: open magic link** button.
- Click it → lands in the shell, authenticated, with the real tenant + tier in the topbar.
- Click the dev link again (or reload `/auth/verify?token=...`) → "This link is invalid or expired" (single-use confirmed).

Report explicitly whether the browser flow passed.

---

## Self-Review

**Spec coverage:**
- §3.1 redis client + magic service → Task 1 (service) + Task 2 Step 3 (lifespan).
- §3.2 request/verify endpoints, dev-gated, 410 on invalid → Task 2.
- §3.3 config (redis_url/ttl/web_base_url) → Task 1 Step 1.
- §4 frontend api + context + Login + /auth/verify → Tasks 3–4.
- §5 single-use (GETDEL) + dev-only dev_link → Task 1 (service), Task 2 (endpoints + clerk-404 test).
- §6 tests (request/verify/single-use/expiry-as-invalid/clerk-404; Login + verify) → Tasks 2 & 5.
- §7 success criteria (e2e) → Task 6 Step 3.

**Placeholder scan:** none — every step has full code; the StrictMode double-invoke guard (`ran` ref) is explicit because the token is single-use.

**Type/name consistency:** `request_link`/`consume_link` (Task 1) used in Task 2 endpoints. `requestMagicLink`/`verifyMagicLink` (Task 3 api) used by `requestLink`/`completeLink` (Task 3 context), consumed by `Login`/`VerifyMagicLink` (Task 4) and the mocked context shape (Tasks 3 & 5 include all 6 fields: status, me, login, requestLink, completeLink, logout). Endpoint paths `/auth/magic/request` + `/auth/magic/verify` and the `dev_link`/`token` JSON keys match across backend, frontend, and tests.

**Resolved during review:** `RequireAuth.test.tsx`'s mocked context must gain `requestLink`/`completeLink` (Task 3 Step 3) or its existing tests fail to typecheck — added as an explicit step.
