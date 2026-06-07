# Slice 3 — Auth (Clerk adapter) + Tenant Bootstrap

**Date:** 2026-05-28
**Status:** Approved design — ready for implementation planning
**Source specs:** `docs/hld.md` §3 (Identity & Tenancy), §8 (Auth flow), §4.4 (entitlements); `docs/lld.md` §3.1, §8, §10, §11; ADR-001 (Clerk via internal adapter)
**Builds on:** Slice 1 (data layer, RLS) + Slice 2 (frontend foundation)

---

## 1. Goal & scope

Add authenticated, tenant-scoped access end-to-end, behind an internal **`AuthProvider` adapter** (ADR-001). Two implementations: a local **DevAuthProvider** (no Clerk account — fully runnable/verifiable now) and a **ClerkAuthProvider** (verifies Clerk JWT via JWKS), selected by config. On first login, **bootstrap** a `user` + `tenant` + `memberships(owner)` + free active `subscription`; every authenticated request sets `app.current_tenant` so RLS scopes all queries. The frontend gains a **Login** screen, **protected routes**, attaches the token to API calls, and shows the **real tenant + tier in the topbar** (replacing the static placeholder).

### In scope
- Backend `AuthProvider` adapter + `DevAuthProvider` + `ClerkAuthProvider` (selected by `AUTH_PROVIDER=dev|clerk`).
- `SECURITY DEFINER` identity functions (`auth_resolve_principal`, `auth_bootstrap`) added via Alembic; `EXECUTE`-granted to `saalr_app`.
- `get_principal` FastAPI dependency: authenticate → resolve/bootstrap → open `saalr_app` session with `app.current_tenant` set → yield `(session, principal)`.
- `GET /me`; dev-only `POST /auth/dev/login`. Entitlements `TIERS` map.
- Frontend auth adapter (`DevAuthClient` + `ClerkAuthClient`), `useAuth()` context, Login route, protected routes, token-on-requests + 401 handling, real `/me` topbar + logout.

### Out of scope (deferred)
- Clerk **webhooks** (user-state sync) — bootstrap-on-first-login covers the MVP.
- **API-key auth** (LLD §8.2), **MFA** gating.
- **Live Clerk verification** — the Clerk path is wired and compiles but is verified only once real keys are added.

---

## 2. Key decision — resolving tenant under RLS (approved)

`tenants`/`memberships`/`subscriptions` are FORCE-RLS by `tenant_id`, but at auth time the tenant isn't known yet, so the app (role `saalr_app`) can't read `memberships` to find it. Resolution: two **`SECURITY DEFINER` Postgres functions** (owner = migration admin role), `EXECUTE`-granted to `saalr_app`, confining RLS bypass to a tiny identity surface. The app keeps least privilege (no admin DB creds in the API).

```sql
-- resolve existing principal (returns 0 or 1 row)
CREATE FUNCTION auth_resolve_principal(p_clerk_user_id text, p_email citext)
RETURNS TABLE (user_id uuid, tenant_id uuid, tier text)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $func$
  SELECT u.user_id, m.tenant_id, COALESCE(s.tier, 'free')
  FROM users u
  JOIN memberships m ON m.user_id = u.user_id
  LEFT JOIN subscriptions s ON s.tenant_id = m.tenant_id AND s.status = 'active'
  WHERE (p_clerk_user_id IS NOT NULL AND u.clerk_user_id = p_clerk_user_id)
     OR (p_clerk_user_id IS NULL AND u.email = p_email)
  LIMIT 1;
$func$;

-- bootstrap user+tenant+membership+free sub; ids generated app-side (UUIDv7)
CREATE FUNCTION auth_bootstrap(p_user_id uuid, p_tenant_id uuid, p_sub_id uuid,
                               p_clerk_user_id text, p_email citext)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $func$
BEGIN
  -- Scope the GUC to the new tenant so the RLS WITH CHECK passes even if the
  -- function owner is subject to FORCE RLS (defense-in-depth for the writes).
  PERFORM set_config('app.current_tenant', p_tenant_id::text, true);
  INSERT INTO users (user_id, email, clerk_user_id) VALUES (p_user_id, p_email, p_clerk_user_id);
  INSERT INTO tenants (tenant_id, display_name, country_code)
    VALUES (p_tenant_id, split_part(p_email, '@', 1), 'US');
  INSERT INTO memberships (user_id, tenant_id, role) VALUES (p_user_id, p_tenant_id, 'owner');
  INSERT INTO subscriptions (subscription_id, tenant_id, tier, status, provider,
                             current_period_start, current_period_end)
    VALUES (p_sub_id, p_tenant_id, 'free', 'active', 'manual', now(), now() + interval '100 years');
END;
$func$;

GRANT EXECUTE ON FUNCTION auth_resolve_principal(text, citext) TO saalr_app;
GRANT EXECUTE ON FUNCTION auth_bootstrap(uuid, uuid, uuid, text, citext) TO saalr_app;
```

**Race handling:** on concurrent first-login the `users.email` unique constraint makes the 2nd `auth_bootstrap` raise; the dependency catches the integrity error and re-runs `auth_resolve_principal`.

---

## 3. Backend (`apps/api` + `packages/core`)

### 3.1 Adapter
- `AuthClaims` (frozen): `clerk_user_id: str | None`, `email: str`.
- `Principal` (frozen): `user_id: UUID`, `tenant_id: UUID`, `email: str`, `tier: str`.
- `AuthProvider` Protocol: `authenticate(authorization: str | None) -> AuthClaims` (raises `AuthError` → 401).
  - **DevAuthProvider:** accepts `Authorization: Bearer dev:<email>`; validates email shape; returns `AuthClaims(clerk_user_id=None, email=<email>)`.
  - **ClerkAuthProvider:** verifies the Clerk JWT (RS256) against cached Clerk **JWKS** (`CLERK_JWKS_URL`/issuer), checks `exp`/`iss`; returns `AuthClaims(clerk_user_id=<sub>, email=<email claim>)`.
- `get_auth_provider()` returns the impl per `AUTH_PROVIDER` (`dev` default; `clerk`).

### 3.2 Dependency & endpoints
- `get_principal(authorization=Header(None))`:
  1. `claims = provider.authenticate(authorization)` (401 `AUTH_INVALID_TOKEN` on failure/missing).
  2. open `saalr_app` async session/transaction; `row = auth_resolve_principal(claims.clerk_user_id, claims.email)`.
  3. if none → generate UUIDv7 ids, `auth_bootstrap(...)`, then re-`auth_resolve_principal` (also the race fallback).
  4. `set_config('app.current_tenant', tenant_id, true)` on the same transaction.
  5. yield `(session, Principal)`.
- `GET /me` → `{ user: {id, email}, tenant: {id, display_name, country_code}, tier, entitlements }`.
- `POST /auth/dev/login` (only when `AUTH_PROVIDER=dev`; else 404): body `{ "email": "..." }` → `{ "token": "dev:<email>" }`.
- Errors use the structured shape (LLD §5/§10): `{ "error": { "code", "message" } }`; `AUTH_INVALID_TOKEN` → 401.

### 3.3 Entitlements
`packages/core/saalr_core/config/tiers.py`:
```python
@dataclass(frozen=True)
class Entitlements:
    live_chains: bool; vol_surface: bool; ml_forecast: bool; research_agent: bool; brokers: int

TIERS = {
  "free":    Entitlements(False, False, False, False, 0),
  "pro":     Entitlements(True,  True,  True,  False, 2),
  "premium": Entitlements(True,  True,  True,  True,  4),
}
```
`/me` returns `TIERS[tier]` as a dict.

---

## 4. Frontend (`apps/web`)

- **Auth adapter** `src/lib/auth/`: `AuthClient` interface `{ isClerk, getToken(): Promise<string|null>, login(email?), logout() }`.
  - `DevAuthClient`: `login(email)` → `POST /api/auth/dev/login` → store token in `localStorage`; `getToken()` reads it; `logout()` clears.
  - `ClerkAuthClient`: wraps `@clerk/clerk-react` (`getToken()` from Clerk session). Chosen by `VITE_AUTH_PROVIDER`.
- **`AuthProvider` + `useAuth()`** context: `{ status: 'loading'|'authed'|'anon', me, login, logout }`. On mount: if a token exists, `GET /me` → `authed`; else `anon`.
- **API client**: attach `Authorization: Bearer <token>` from the active `AuthClient`; on `401` clear session → redirect to `/login`.
- **Routing**: `/login` public; all shell routes wrapped in `RequireAuth` (redirect to `/login` when `anon`). After login, redirect to `/`.
- **Login page**: dev mode → email field + "Continue"; clerk mode → Clerk `<SignIn />`.
- **Topbar**: tenant chip shows `me.tenant.display_name` + `me.tier` (capitalized); add a user menu (email + **Logout**). Removes the static "Acme Capital · Premium".

---

## 5. Error handling
- Missing/invalid token at a protected endpoint → `401 AUTH_INVALID_TOKEN` (structured JSON).
- Frontend treats any `401` as "session invalid" → logout + redirect to `/login`.
- `auth_bootstrap` unique-violation race → caught, re-resolve (idempotent first-login).

---

## 6. Testing

**Backend (integration, real PG):**
- First dev login bootstraps **exactly one** user + tenant + active free subscription; `auth_resolve_principal` then returns it.
- `GET /me` (with `Bearer dev:a@x.com`) → `tier=free`, entitlements match `TIERS['free']`, tenant `display_name='a'`.
- **Idempotency:** a second `/me` with the same email reuses the same tenant (no duplicate).
- **Isolation:** rows created under user A's principal are invisible to user B's principal (RLS via the per-request GUC).
- Missing/blank/garbage `Authorization` → `401 AUTH_INVALID_TOKEN`.

**Frontend (Vitest + RTL):**
- `useAuth` dev `login()` stores token and transitions to `authed`; `logout()` → `anon`.
- `RequireAuth` redirects an `anon` user to `/login`.
- Topbar renders tenant/tier from a mocked `/me`.

---

## 7. Config
- Backend: `AUTH_PROVIDER=dev|clerk` (default `dev`); Clerk: `CLERK_JWKS_URL`, `CLERK_ISSUER` (read only when `clerk`). Secrets via `.env` (gitignored).
- Frontend: `VITE_AUTH_PROVIDER=dev|clerk` (default `dev`); `VITE_CLERK_PUBLISHABLE_KEY` (clerk only).
- No schema changes to tables — identity reuses `users.clerk_user_id` (clerk) / `users.email` (dev); only the two functions are added by migration.

---

## 8. Success criteria
With `AUTH_PROVIDER=dev`: open the app → **Login** → enter an email → land in the shell with **your tenant + Free tier in the topbar** (from `/me`); refresh persists the session; **Logout** returns to Login. Protected routes redirect when logged out. Backend + web gate suites green. `ClerkAuthProvider`/`ClerkAuthClient` compile and switch on via env (live Clerk verification pending keys).

---

## 9. Future slices
Clerk webhooks (user/sub sync) · API-key auth · MFA gating for live trading · and, now unblocked by real tenant context, **tenant-scoped resource CRUD** (e.g. `strategies` per HLD §7.3).
