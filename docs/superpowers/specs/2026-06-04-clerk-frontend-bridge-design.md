# Clerk frontend bridge — design

**Status:** approved design, 2026-06-04.

## Goal

Make `VITE_AUTH_PROVIDER=clerk` work on the web frontend (today `AuthProvider` throws). Add the
`@clerk/clerk-react` SDK, a `ClerkAuthProvider` bridge that maps a Clerk session into our existing
`AuthContextValue`, and a token feed that puts a Clerk-issued JWT (carrying `email`) into the bearer
the API client already sends. The dev magic-link flow is untouched when the flag is unset or `dev`.

## Current state (what exists)

- **Backend** `ClerkAuthProvider` (`apps/api/saalr_api/auth/providers.py`) verifies a Clerk RS256 JWT
  against Clerk's JWKS and requires both `sub` and `email` claims (`AuthClaims(email, clerk_user_id)`).
  Selected when `settings.auth_provider == "clerk"` with `CLERK_JWKS_URL` (+ optional `CLERK_ISSUER`).
- **Frontend** token plumbing is synchronous: `lib/api.ts` `authHeaders()` reads a static string via
  `tokenStore.getToken()` and sends `Authorization: Bearer <token>`. `getMe()` resolves the current
  user → `{ user, tenant, tier, entitlements }`.
- **`src/auth/AuthContext.tsx`**: `DevAuthProvider` (magic-link / dev-login → `tokenStore` → `getMe`)
  implements `AuthContextValue = { status, me, login, requestLink, completeLink, logout, refresh }`.
  `AuthProvider` switches on `import.meta.env.VITE_AUTH_PROVIDER` and **throws** for `clerk`.
- **Mount**: `pages/app/+Page.tsx` renders `<QueryClientProvider><BrowserRouter basename="/app">
  <AuthProvider><AppRoutes/></AuthProvider>…`. So whatever `AuthProvider` renders sits **inside** the
  router — fine for `<ClerkProvider>` and an embedded `<SignIn/>` (default virtual routing).
- `@clerk/clerk-react` is **not** installed.

## The core challenge

Clerk session tokens are short-lived and fetched asynchronously (`getToken()` is a Promise), but
`authHeaders()` reads a static string synchronously. Rather than refactor every API caller to fetch a
token per request, the bridge **keeps `tokenStore` fed** with a fresh Clerk JWT: on sign-in it
`getToken({ template })` → `setToken()` → `getMe()`, and a ~50s interval refreshes the stored token
(Clerk's `getToken()` returns a cached token and auto-renews near expiry). `lib/api.ts` and every
existing caller stay unchanged. (A future improvement — an async per-request token provider — is
deferred; noted in Out of scope.)

## Decisions (locked)

- **Email claim via a named JWT template.** The bridge calls `getToken({ template: TEMPLATE })` where
  `TEMPLATE = import.meta.env.VITE_CLERK_JWT_TEMPLATE ?? 'saalr'`. The Clerk dashboard must define a
  JWT template (default name `saalr`) mapping `{{user.primary_email_address}}` → an `email` claim
  (and Clerk includes `sub` automatically). If `VITE_CLERK_JWT_TEMPLATE` is set to an empty string,
  the bridge falls back to plain `getToken()` (for teams who instead add `email` to the default
  session token). The backend reads `claims["email"]` / `claims["sub"]` either way.
- **Embedded sign-in.** `/login` renders Clerk's `<SignIn/>` component in-app (styled container) when
  the provider is `clerk`; the dev magic-link form stays for `dev`/unset. `RequireAuth` still routes
  `anon → /login` unchanged.
- **Keep the custom Topbar identity.** The Topbar's email + Logout stay; in clerk mode `logout`
  calls Clerk `signOut()`. Clerk's `<UserButton/>` is not adopted (out of scope).

## Components / files

- **`apps/web/package.json`** — add dependency `@clerk/clerk-react` (v5.x).
- **`apps/web/src/auth/context.ts`** *(new)* — the shared context module: `export type AuthStatus`,
  `export interface AuthContextValue`, `export const AuthContext = createContext<AuthContextValue | null>(null)`,
  and `export function useAuth()` (throws if used outside a provider). Both providers import these.
- **`apps/web/src/auth/AuthContext.tsx`** *(modify)* — import `AuthContext`/`useAuth`/types from
  `./context`; keep `DevAuthProvider` (unchanged behaviour) now providing the imported `AuthContext`.
  `AuthProvider` switch: `provider === 'clerk'` → `<ClerkAuthProvider>{children}</ClerkAuthProvider>`;
  else `<DevAuthProvider>`. Re-export `useAuth` (and keep exporting `AuthProvider`) so existing imports
  (`AuthContext.test.tsx`, all pages) keep working.
- **`apps/web/src/auth/ClerkAuthProvider.tsx`** *(new)* —
  - Reads `const pk = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY`. If missing → throw
    `Error("VITE_CLERK_PUBLISHABLE_KEY is required when VITE_AUTH_PROVIDER=clerk")`.
  - `const template = import.meta.env.VITE_CLERK_JWT_TEMPLATE ?? 'saalr'`.
  - Renders `<ClerkProvider publishableKey={pk}><ClerkBridge template={template}>{children}</ClerkBridge></ClerkProvider>`.
  - **`ClerkBridge`** uses Clerk's `useAuth()` → `{ isLoaded, isSignedIn, getToken, signOut }`. Local
    `status`/`me` state. An effect keyed on `[isLoaded, isSignedIn]`:
    - `!isLoaded` → `status = 'loading'`.
    - loaded & signed-in → `const t = await getToken(template ? { template } : undefined)`;
      if `t` → `setToken(t)` → `me = await getMe()` → `status = 'authed'`; on `getMe` failure →
      `setToken(null)`, `status = 'anon'`, `console.warn` hinting the JWT template may be missing the
      `email` claim.
    - loaded & signed-out → `setToken(null)`, `me = null`, `status = 'anon'`.
  - A `setInterval` (50s) while signed-in re-runs `getToken` → `setToken` to keep the bearer fresh;
    cleared on unmount / sign-out.
  - Provides `AuthContextValue`: `logout: () => { void signOut(); setToken(null); setMe(null) }`;
    `refresh`: re-run the token+me fetch; `login`/`requestLink`/`completeLink`: `async () => { throw
    new Error('magic-link auth is disabled under Clerk') }` (defensive — Login branches so these are
    never called in clerk mode).
- **`apps/web/src/auth/ClerkSignIn.tsx`** *(new)* — a small wrapper rendering Clerk's `<SignIn/>`
  inside the same centered card container the dev Login uses (keeps the Clerk import out of `Login.tsx`).
- **`apps/web/src/pages/Login.tsx`** *(modify)* — at the top, `const clerk = import.meta.env.VITE_AUTH_PROVIDER === 'clerk'`;
  if `clerk` → `return <ClerkSignIn />`; else the existing magic-link form (the default path, so
  `Login.test.tsx` stays green).
- **`apps/web/src/vite-env.d.ts`** — extend (or create) `interface ImportMetaEnv` with
  `VITE_AUTH_PROVIDER?: string`, `VITE_CLERK_PUBLISHABLE_KEY?: string`, `VITE_CLERK_JWT_TEMPLATE?: string`
  (alongside the existing `VITE_API_BASE_URL`). If a vite-env types file already declares some of
  these, only add the missing ones.

## Data flow

App boot → `AuthProvider` reads `VITE_AUTH_PROVIDER`. `dev`/unset → `DevAuthProvider` (magic-link /
dev-login → `tokenStore` → `getMe`, exactly as today). `clerk` → `ClerkProvider(publishableKey)` >
`ClerkBridge` > `AuthContext.Provider`. Clerk loads → if signed in, `getToken({template})` →
`tokenStore.setToken` → `getMe()` → `me`, `status='authed'`; the 50s interval keeps the token fresh.
`RequireAuth`/`Topbar`/pages consume `useAuth()` unchanged. `/login` renders `<SignIn/>`; after Clerk
auth the bridge flips to `authed` and the app renders. `logout` → `signOut()`.

## Error handling

- Missing `VITE_CLERK_PUBLISHABLE_KEY` in clerk mode → a clear actionable throw at provider init
  (replaces today's generic "not yet wired" throw).
- `getToken()` returns `null` (signed out / mid-load) → treated as `anon`.
- `getMe()` 401 (backend rejected the token — usually the JWT template is missing the `email` claim,
  or `CLERK_JWKS_URL`/issuer mismatch) → `setToken(null)`, `status='anon'`, and a `console.warn`
  pointing at the JWT-template requirement. The user lands back on `/login`.
- `login`/`requestLink`/`completeLink` invoked under Clerk → reject with a clear error (defensive).

## Testing (vitest + @testing-library/react; mock `@clerk/clerk-react` and `lib/api`)

Mock `@clerk/clerk-react` with a passthrough `ClerkProvider`, a controllable `useAuth`
(`{ isLoaded, isSignedIn, getToken, signOut }`), and a `SignIn` stub. Mock `getMe` from `lib/api`.

- `ClerkAuthProvider.test.tsx`:
  - signed-in (`isLoaded:true, isSignedIn:true`, `getToken` resolves a token) → `getToken` called with
    `{ template: 'saalr' }`, `tokenStore` holds the token, `getMe` called, the consumed context shows
    `status:'authed'` + the mocked `me`.
  - signed-out (`isLoaded:true, isSignedIn:false`) → `status:'anon'`, `getMe` not called, token cleared.
  - not loaded (`isLoaded:false`) → `status:'loading'`.
  - `logout()` → Clerk `signOut` called and token cleared.
  - missing `VITE_CLERK_PUBLISHABLE_KEY` → render throws the actionable error.
- `AuthContext.test.tsx` (extend or add): with `vi.stubEnv('VITE_AUTH_PROVIDER','clerk')` the
  `AuthProvider` renders the Clerk path (mocked, does not throw); default/`dev` renders
  `DevAuthProvider`. Existing dev-path assertions still pass.
- `Login.test.tsx` (extend): `vi.stubEnv('VITE_AUTH_PROVIDER','clerk')` → renders the `SignIn` stub;
  default → renders the magic-link form (existing test).
- **Manual smoke (documented, not automated — needs a live Clerk app):** set
  `VITE_AUTH_PROVIDER=clerk`, `VITE_CLERK_PUBLISHABLE_KEY`, optional `VITE_CLERK_JWT_TEMPLATE=saalr`;
  create a Clerk JWT template `saalr` mapping `{{user.primary_email_address}}`→`email`; backend
  `AUTH_PROVIDER=clerk` + `CLERK_JWKS_URL`; sign in → confirm `/me` resolves and the app renders.
- Gate: `npm run typecheck && npm run lint && npm run test:run` (all green); `npm run build` still
  prerenders 17 docs (the `/app` mount is client-only).

## Out of scope (later)

Clerk webhooks for user→tenant provisioning (a backend concern); Clerk Organizations / org-scoped
tenancy; an async per-request token provider replacing the timer-refresh; adopting Clerk's
`<UserButton/>` in the Topbar; Clerk-driven sign-up theming beyond the default `<SignIn/>`; wiring a
real Clerk app/keys (env + dashboard config is an operational step, not code).
