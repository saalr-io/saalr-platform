# Clerk frontend bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `VITE_AUTH_PROVIDER=clerk` work — add `@clerk/clerk-react`, a `ClerkAuthProvider` bridge mapping a Clerk session into our `AuthContextValue`, and a token feed that keeps a Clerk JWT (with an `email` claim) in the bearer the API client sends. Dev magic-link auth is unchanged for `dev`/unset.

**Architecture:** Extract the shared `AuthContext` into `auth/context.ts` so a new `ClerkAuthProvider` and the existing `DevAuthProvider` both feed one context. `AuthProvider` switches on the env flag. The bridge fetches a Clerk JWT via a named template into `tokenStore` on sign-in and on a 50s interval, so the synchronous `authHeaders()` keeps working untouched. `/login` renders Clerk `<SignIn/>` in clerk mode.

**Tech Stack:** React 18 + TS strict + Vite + react-router 6 + Vitest + @testing-library/react + @clerk/clerk-react v5.

**Conventions (apply to every task):**
- Run web tests from `apps/web`: `npx vitest run <files>`. Gate: `npm run typecheck` + `npm run lint`.
- Commit footer (exact): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Theme tokens only for Tailwind class colors. Double-quote JSX strings with apostrophes.
- NEVER modify root `.gitignore` or `tools/equity-screener/equity_screener/cli.py`. Stage ONLY each task's files. `package-lock.json` IS committed for a legitimate, diff-verified dependency addition.

---

### Task 1: install `@clerk/clerk-react` + env types

**Files:**
- Modify: `apps/web/package.json`, `apps/web/package-lock.json` (via install)
- Modify: `apps/web/src/vite-env.d.ts`

- [ ] **Step 1: install** — from `apps/web`:

```bash
npm install @clerk/clerk-react@^5
```

Expected: `package.json` gains `"@clerk/clerk-react": "^5.x"` under `dependencies`; `package-lock.json` updates. Verify the `git diff` touches only `package.json` + `package-lock.json` and the additions are `@clerk/*` + its transitive deps (no unrelated churn).

- [ ] **Step 2: extend env types** — replace `apps/web/src/vite-env.d.ts` with:

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_AUTH_PROVIDER?: string
  readonly VITE_CLERK_PUBLISHABLE_KEY?: string
  readonly VITE_CLERK_JWT_TEMPLATE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

- [ ] **Step 3: verify** — `npm run typecheck` clean (the import in later tasks resolves now that the package is installed). `npx vitest run` (full) still green — installing a dep shouldn't change behaviour.

- [ ] **Step 4: commit**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/src/vite-env.d.ts
git commit -m "build(web): add @clerk/clerk-react + Clerk env types

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: extract shared `auth/context.ts`

**Files:**
- Create: `apps/web/src/auth/context.ts`
- Modify: `apps/web/src/auth/AuthContext.tsx`

This is a refactor — behaviour must not change. The existing `AuthContext.test.tsx` (dev provider) is the regression guard and must stay green.

- [ ] **Step 1: create** `apps/web/src/auth/context.ts`:

```typescript
import { createContext, useContext } from 'react'
import type { Me } from '../lib/api'

export type AuthStatus = 'loading' | 'authed' | 'anon'

export interface AuthContextValue {
  status: AuthStatus
  me: Me | null
  login: (email?: string) => Promise<void>
  requestLink: (email: string) => Promise<{ dev_link?: string }>
  completeLink: (token: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within an AuthProvider')
  return value
}
```

- [ ] **Step 2: rewrite** `apps/web/src/auth/AuthContext.tsx` (keeps `DevAuthProvider` behaviour identical; imports the context from `./context`; switches to Clerk; re-exports for back-compat):

```typescript
import {
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { devLogin, getMe, requestMagicLink, verifyMagicLink, type Me } from '../lib/api'
import { getToken, setToken } from '../lib/tokenStore'
import { AuthContext, useAuth, type AuthStatus } from './context'
import { ClerkAuthProvider } from './ClerkAuthProvider'

export { useAuth }
export type { AuthStatus, AuthContextValue } from './context'

function DevAuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [me, setMe] = useState<Me | null>(null)

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setMe(null)
      setStatus('anon')
      return
    }
    try {
      setMe(await getMe())
      setStatus('authed')
    } catch {
      setToken(null)
      setMe(null)
      setStatus('anon')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(
    async (email?: string) => {
      const token = await devLogin(email ?? '')
      setToken(token)
      await refresh()
    },
    [refresh],
  )

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

  const logout = useCallback(() => {
    setToken(null)
    setMe(null)
    setStatus('anon')
  }, [])

  return (
    <AuthContext.Provider value={{ status, me, login, requestLink, completeLink, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const provider = import.meta.env.VITE_AUTH_PROVIDER ?? 'dev'
  if (provider === 'clerk') {
    return <ClerkAuthProvider>{children}</ClerkAuthProvider>
  }
  return <DevAuthProvider>{children}</DevAuthProvider>
}
```

NOTE: this file now imports `./ClerkAuthProvider`, which is created in Task 3. To keep Task 2 independently compilable, **do Task 3 before running typecheck on Task 2**, OR create a temporary one-line stub. Recommended: implement Task 2 and Task 3 together in one batch, run typecheck once both exist, then commit Task 2 and Task 3 as their own commits. (The plan lists them separately for review clarity.)

- [ ] **Step 3: run the regression** — `cd apps/web && npx vitest run src/auth/AuthContext.test.tsx` → both existing tests pass (dev provider unaffected). (Requires Task 3's file to exist — see note.)

- [ ] **Step 4: commit**

```bash
git add apps/web/src/auth/context.ts apps/web/src/auth/AuthContext.tsx
git commit -m "refactor(web): extract shared auth context; AuthProvider switches dev|clerk

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `ClerkAuthProvider.tsx` bridge + test

**Files:**
- Create: `apps/web/src/auth/ClerkAuthProvider.tsx`
- Create: `apps/web/src/auth/ClerkAuthProvider.test.tsx`

- [ ] **Step 1: write the failing test** `apps/web/src/auth/ClerkAuthProvider.test.tsx`:

```typescript
import type React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { getToken, setToken } from '../lib/tokenStore'

const h = vi.hoisted(() => ({
  clerk: {
    isLoaded: true,
    isSignedIn: true,
    getToken: vi.fn(async (_opts?: { template?: string }) => 'clerk-jwt'),
    signOut: vi.fn(),
  },
  getMe: vi.fn(),
}))

vi.mock('@clerk/clerk-react', () => ({
  ClerkProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => h.clerk,
  SignIn: () => null,
}))

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return { ...actual, getMe: h.getMe }
})

import { ClerkAuthProvider } from './ClerkAuthProvider'
import { useAuth } from './context'

function Probe() {
  const { status, me, logout } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="tenant">{me?.tenant.display_name ?? ''}</span>
      <button onClick={() => logout()}>logout</button>
    </div>
  )
}

const ME = {
  user: { id: 'u1', email: 'alice@acme.com' },
  tenant: { id: 't1', display_name: 'acme', country_code: 'US' },
  tier: 'pro', entitlements: {},
}

beforeEach(() => {
  vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', 'pk_test_x')
  vi.stubEnv('VITE_CLERK_JWT_TEMPLATE', 'saalr')
  h.clerk.isLoaded = true
  h.clerk.isSignedIn = true
  h.clerk.getToken.mockResolvedValue('clerk-jwt')
  h.clerk.signOut.mockReset()
  h.getMe.mockReset()
  setToken(null)
})
afterEach(() => vi.unstubAllEnvs())

describe('ClerkAuthProvider', () => {
  it('signed in: fetches a templated token, stores it, loads me, status authed', async () => {
    h.getMe.mockResolvedValue(ME)
    render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('authed'))
    expect(h.clerk.getToken).toHaveBeenCalledWith({ template: 'saalr' })
    expect(getToken()).toBe('clerk-jwt')
    expect(h.getMe).toHaveBeenCalled()
    expect(screen.getByTestId('tenant').textContent).toBe('acme')
  })

  it('signed out: status anon and does not call getMe', async () => {
    h.clerk.isSignedIn = false
    render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anon'))
    expect(h.getMe).not.toHaveBeenCalled()
  })

  it('not loaded: status loading', () => {
    h.clerk.isLoaded = false
    render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)
    expect(screen.getByTestId('status').textContent).toBe('loading')
  })

  it('logout calls Clerk signOut and clears the token', async () => {
    h.getMe.mockResolvedValue(ME)
    render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('authed'))
    fireEvent.click(screen.getByText('logout'))
    await waitFor(() => expect(h.clerk.signOut).toHaveBeenCalled())
    expect(getToken()).toBeNull()
  })

  it('throws a clear error when the publishable key is missing', () => {
    vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', '')
    expect(() => render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)).toThrow(/VITE_CLERK_PUBLISHABLE_KEY/)
  })
})
```

- [ ] **Step 2: run → FAIL** — `cd apps/web && npx vitest run src/auth/ClerkAuthProvider.test.tsx`

- [ ] **Step 3: create** `apps/web/src/auth/ClerkAuthProvider.tsx`:

```typescript
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ClerkProvider, useAuth as useClerkAuth } from '@clerk/clerk-react'
import { getMe, type Me } from '../lib/api'
import { setToken } from '../lib/tokenStore'
import { AuthContext, type AuthStatus } from './context'

const REFRESH_MS = 50_000

function tokenOpts(template: string): { template: string } | undefined {
  return template ? { template } : undefined
}

function ClerkBridge({ template, children }: { template: string; children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken, signOut } = useClerkAuth()
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [me, setMe] = useState<Me | null>(null)

  const sync = useCallback(async () => {
    if (!isLoaded) {
      setStatus('loading')
      return
    }
    if (!isSignedIn) {
      setToken(null)
      setMe(null)
      setStatus('anon')
      return
    }
    const t = await getToken(tokenOpts(template))
    if (!t) {
      setToken(null)
      setMe(null)
      setStatus('anon')
      return
    }
    setToken(t)
    try {
      setMe(await getMe())
      setStatus('authed')
    } catch {
      setToken(null)
      setMe(null)
      setStatus('anon')
      console.warn(
        'Clerk sign-in succeeded but /me was rejected — check that the Clerk JWT template includes an `email` claim.',
      )
    }
  }, [isLoaded, isSignedIn, getToken, template])

  useEffect(() => {
    void sync()
  }, [sync])

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return
    const id = setInterval(() => {
      void getToken(tokenOpts(template)).then((t) => {
        if (t) setToken(t)
      })
    }, REFRESH_MS)
    return () => clearInterval(id)
  }, [isLoaded, isSignedIn, getToken, template])

  const logout = useCallback(() => {
    setToken(null)
    setMe(null)
    setStatus('anon')
    void signOut()
  }, [signOut])

  const disabled = useCallback(async (): Promise<never> => {
    throw new Error('magic-link auth is disabled under Clerk')
  }, [])

  return (
    <AuthContext.Provider
      value={{
        status,
        me,
        login: disabled,
        requestLink: disabled,
        completeLink: disabled,
        logout,
        refresh: sync,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function ClerkAuthProvider({ children }: { children: ReactNode }) {
  const pk = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
  if (!pk) {
    throw new Error('VITE_CLERK_PUBLISHABLE_KEY is required when VITE_AUTH_PROVIDER=clerk')
  }
  const template = import.meta.env.VITE_CLERK_JWT_TEMPLATE ?? 'saalr'
  return (
    <ClerkProvider publishableKey={pk}>
      <ClerkBridge template={template}>{children}</ClerkBridge>
    </ClerkProvider>
  )
}
```

NOTE on the `disabled` stubs: a `() => Promise<never>` is assignable to `login`/`requestLink`/`completeLink` because `never` is assignable to any return payload and a zero-arg fn satisfies the param signatures. If `tsc` rejects any assignment, wrap them explicitly, e.g. `requestLink: () => disabled()`.

- [ ] **Step 4: run → 5 passed** — `cd apps/web && npx vitest run src/auth/ClerkAuthProvider.test.tsx`; then `npm run typecheck` + `npm run lint` clean.

- [ ] **Step 5: commit**

```bash
git add apps/web/src/auth/ClerkAuthProvider.tsx apps/web/src/auth/ClerkAuthProvider.test.tsx
git commit -m "feat(web): ClerkAuthProvider bridge (Clerk session -> AuthContext, templated JWT into tokenStore)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `AuthProvider` switch test (env-driven)

**Files:**
- Modify: `apps/web/src/auth/AuthContext.test.tsx` (add a case; keep the existing two)

- [ ] **Step 1: add a test case** to `apps/web/src/auth/AuthContext.test.tsx`. Append this `describe` block at the end of the file (after the existing `describe('useAuth (dev provider)', …)`), and add the imports it needs at the top (`vi` is already imported):

```typescript
describe('AuthProvider switch', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('renders the Clerk bridge (not the dev provider) when VITE_AUTH_PROVIDER=clerk', async () => {
    vi.stubEnv('VITE_AUTH_PROVIDER', 'clerk')
    vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', 'pk_test_x')
    // Mocked Clerk is signed-out, so the bridge resolves to 'anon' without throwing.
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anon'))
  })
})
```

This case relies on the same `@clerk/clerk-react` mock as Task 3. Add this mock near the top of `AuthContext.test.tsx` (the dev tests do not use Clerk, so a default signed-out mock is inert for them):

```typescript
const clerkMock = vi.hoisted(() => ({
  isLoaded: true, isSignedIn: false,
  getToken: vi.fn(async () => null), signOut: vi.fn(),
}))
vi.mock('@clerk/clerk-react', () => ({
  ClerkProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => clerkMock,
  SignIn: () => null,
}))
```

(Add `import type React from 'react'` at the top if not present.)

- [ ] **Step 2: run → all green** — `cd apps/web && npx vitest run src/auth/AuthContext.test.tsx` → 3 tests pass (2 dev + 1 switch). typecheck + lint clean.

- [ ] **Step 3: commit**

```bash
git add apps/web/src/auth/AuthContext.test.tsx
git commit -m "test(web): AuthProvider routes to the Clerk bridge under VITE_AUTH_PROVIDER=clerk

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `ClerkSignIn.tsx` + `Login` branch + test

**Files:**
- Create: `apps/web/src/auth/ClerkSignIn.tsx`
- Modify: `apps/web/src/pages/Login.tsx`
- Modify: `apps/web/src/pages/Login.test.tsx`

- [ ] **Step 1: create** `apps/web/src/auth/ClerkSignIn.tsx`:

```typescript
import { SignIn } from '@clerk/clerk-react'
import { Logo } from '../components/Logo'

export function ClerkSignIn() {
  return (
    <div className="grid min-h-screen place-items-center" data-testid="clerk-signin">
      <div className="w-[360px] rounded-xl border border-line bg-gradient-to-b from-panel to-[#0b1018] p-6">
        <Logo size={24} descriptor />
        <div className="mt-6">
          <SignIn />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: branch `Login.tsx`** — add at the very top of the `Login` function body (before any other hooks/logic), and the import:

```typescript
import { ClerkSignIn } from '../auth/ClerkSignIn'
```

```typescript
export function Login() {
  if (import.meta.env.VITE_AUTH_PROVIDER === 'clerk') {
    return <ClerkSignIn />
  }
  // ...existing magic-link form unchanged below
```

IMPORTANT: the `if` must come before the existing `useState`/`useAuth` calls would normally be a Rules-of-Hooks violation. To stay compliant, the env is a module-constant for the lifetime of the app, but to be safe put the check as the FIRST statement so the component either always takes the Clerk path or always the dev path within a given build — env does not change between renders. (This mirrors how `AuthProvider` already branches on the same env constant.)

- [ ] **Step 3: extend `Login.test.tsx`** — add the Clerk mock + a case. At the top of the file add:

```typescript
vi.mock('@clerk/clerk-react', () => ({
  SignIn: () => <div data-testid="clerk-signin-widget" />,
}))
```

and a test (keep the existing dev-form tests):

```typescript
it('renders the Clerk sign-in when VITE_AUTH_PROVIDER=clerk', () => {
  vi.stubEnv('VITE_AUTH_PROVIDER', 'clerk')
  render(/* the same wrapper the existing tests use for <Login /> */)
  expect(screen.getByTestId('clerk-signin')).toBeInTheDocument()
  vi.unstubAllEnvs()
})
```

(Use the same render wrapper/imports the existing `Login.test.tsx` uses — match its `MemoryRouter`/provider setup. The dev tests must still pass with the default env.)

- [ ] **Step 4: run** — `cd apps/web && npx vitest run src/pages/Login.test.tsx` → all green (existing dev cases + the new clerk case). typecheck + lint clean.

- [ ] **Step 5: commit**

```bash
git add apps/web/src/auth/ClerkSignIn.tsx apps/web/src/pages/Login.tsx apps/web/src/pages/Login.test.tsx
git commit -m "feat(web): embedded Clerk <SignIn/> on /login under clerk auth

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: final gate

- [ ] **Step 1** — from `apps/web`: `npm run typecheck && npm run lint && npm run test:run`. Expected: clean; full suite green (260 + ~9 new ≈ 269). Then `npm run build` → still "17 HTML documents pre-rendered" (auth lives only in the client-only `/app` mount; the Clerk SDK is not pulled into the SSG public pages). Report the exact final test count and confirm the 17-doc build.

---

## Self-Review notes (for the executor)

- **Task ordering:** Task 2's `AuthContext.tsx` imports `./ClerkAuthProvider` (Task 3). Implement Task 2 + Task 3 together, run typecheck once both files exist, then commit them as separate commits in order (context refactor, then bridge). Do not run typecheck on Task 2 in isolation.
- **Dev path untouched:** `DevAuthProvider`'s body is copied verbatim — the only change is importing the context from `./context`. The existing `AuthContext.test.tsx` dev cases are the regression guard.
- **Clerk `useAuth` alias:** the bridge imports Clerk's hook as `useClerkAuth` to avoid colliding with our `useAuth`.
- **Token freshness:** the 50s interval re-fetches the token into `tokenStore`; `lib/api.ts` is never touched. The async-per-request token is deferred (spec Out of scope).
- **Mocking Clerk:** tests `vi.mock('@clerk/clerk-react', …)` with a passthrough `ClerkProvider` (`({children}) => children`), a hoisted controllable `useAuth`, and a `SignIn` stub — the real package need not run in jsdom, but it MUST be installed (Task 1) for `tsc` and the build to resolve its types.
- **No new behaviour for dev:** building/serving with the flag unset behaves exactly as before.
```
