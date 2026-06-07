# Slice 4 — Passwordless Email Magic Link (hybrid)

**Date:** 2026-05-28
**Status:** Approved design — ready for implementation planning
**Source:** ADR-001 (Clerk for prod auth); builds on Slice 3 (auth adapter + Dev/Clerk providers + RLS)
**Builds on:** `apps/api/saalr_api/auth/`, the Redis container in `infra/docker/docker-compose.yml` (currently unused)

---

## 1. Goal & scope

Make login passwordless via email magic link. **Hybrid:**
- **Dev** — a self-hosted magic link behind the existing auth adapter: request → one-time token in **Redis** → "email" (logged + returned in dev) → click → verify → session.
- **Prod** — Clerk's native email magic link (our backend already verifies Clerk JWTs; production just enables magic link in the Clerk dashboard + the deferred Clerk frontend bridge).

This replaces the instant "type any email, get a token" dev login with a verified flow (you must receive the link). The verify step issues the **existing `dev:<email>` session token**, so the auth adapter, `/me`, and per-request RLS are unchanged.

### In scope
- Redis async client wired into the API; a small magic-link service (`request_link`/`consume_link`).
- `POST /auth/magic/request` + `POST /auth/magic/verify`, **gated to `AUTH_PROVIDER=dev`** (404 under clerk).
- Frontend: Login → "Send magic link" → "check your email" state (+ dev link button); a `/auth/verify` route that exchanges the token for a session.
- Tests (backend against real Redis; frontend with mocked fetch).

### Out of scope (deferred)
- Production email provider — Clerk owns delivery/deliverability/rate-limiting in prod.
- Rate-limiting on `/auth/magic/request` (note as a future Redis-based add).
- The Clerk **frontend** bridge (`@clerk/clerk-react`) — still pending a Clerk account/keys.
- Keeping passwords anywhere — there are none.

---

## 2. Flow (dev)

```
Login (email) ── POST /auth/magic/request {email}
                    → token = secrets.token_urlsafe(32)
                    → SET magiclink:{token} = email  EX 900   (Redis)
                    → verify_url = {WEB_BASE_URL}/auth/verify?token=...
                    → log it; (dev only) also return dev_link
"check your email"  ←
   user clicks link → /auth/verify?token=...  (frontend route)
                    → POST /auth/magic/verify {token}
                    → email = GETDEL magiclink:{token}   (atomic, single-use)
                    → 200 { token: "dev:<email>" }   |   410 if missing/expired/used
   setToken → refresh /me → redirect to /
```

---

## 3. Backend (`apps/api`)

### 3.1 Redis + service
- Add dependency `redis>=5`; create `redis.asyncio.Redis.from_url(settings.redis_url, decode_responses=True)` in the app lifespan as `app.state.redis`; close on shutdown.
- `apps/api/saalr_api/auth/magic.py`:
  - `async def request_link(redis, email: str, ttl: int) -> str`: `token = secrets.token_urlsafe(32)`; `await redis.set(f"magiclink:{token}", email, ex=ttl)`; return `token`.
  - `async def consume_link(redis, token: str) -> str | None`: `return await redis.getdel(f"magiclink:{token}")` (str email or None).

### 3.2 Endpoints (dev-gated; 404 when `AUTH_PROVIDER != "dev"`)
- `POST /auth/magic/request` body `{email}` → validate with the existing email regex; `token = request_link(...)`; `verify_url = f"{settings.web_base_url}/auth/verify?token={token}"`; log it; return `{"sent": true, "dev_link": verify_url}` (the `dev_link` field is included **only** in dev).
- `POST /auth/magic/verify` body `{token}` → `email = consume_link(...)`; if `None` → `410 {"error":{"code":"AUTH_MAGIC_LINK_INVALID","message":"link is invalid or expired"}}`; else `return {"token": f"dev:{email}"}`.
- `POST /auth/dev/login` is kept as a dev/CI test shortcut (still dev-gated).

### 3.3 Config (`saalr_core/config.py`)
- `redis_url: str = "redis://localhost:6379/0"`
- `magic_link_ttl_seconds: int = 900`
- `web_base_url: str = "http://localhost:5174"`

---

## 4. Frontend (`apps/web`)

- `lib/api.ts`: `requestMagicLink(email): Promise<{ sent: boolean; dev_link?: string }>` (POST `/auth/magic/request`); `verifyMagicLink(token): Promise<string>` (POST `/auth/magic/verify` → session token).
- `auth/AuthContext.tsx`: add `requestLink(email)` (returns `{ dev_link? }`) and `completeLink(token)` (verify → `setToken` → refresh `/me`). Keep `logout`. (`login` instant path may remain for tests but the UI uses the link flow.)
- **Login page**: email field → **"Send magic link"** → "Check your email — we sent a sign-in link to {email}" state; in dev render a **"Dev: open magic link"** button using `dev_link`. Error state on request failure.
- **`/auth/verify` route** (public): reads `?token=`, calls `completeLink`, then `navigate('/', { replace })`; on failure shows "link invalid or expired" + link back to `/login`.

---

## 5. Security & quality
- Token: `secrets.token_urlsafe(32)` (opaque, ~256-bit), stored as the Redis key; **single-use** via `GETDEL`; **15-min TTL**.
- `dev_link` is returned **only** when `AUTH_PROVIDER=dev`; in prod the self-hosted endpoints don't exist (Clerk emails the link).
- Email enumeration is not a concern (any email bootstraps a tenant; request always returns `{sent:true}`).
- Rate-limiting on request is a documented future add (Redis token bucket, HLD §10.4).

---

## 6. Testing
- **Backend (real Redis fixture; flush `magiclink:*` between tests):** request stores a token + returns `dev_link`; verify succeeds once and returns `dev:<email>`; a second verify of the same token → 410; a garbage/expired token → 410; both magic endpoints return 404 when `AUTH_PROVIDER=clerk`.
- **Frontend (Vitest, mocked fetch):** Login "Send magic link" shows the check-email state and a dev link; `/auth/verify` with a token exchanges it and transitions to authed.

---

## 7. Success criteria
Dev (`AUTH_PROVIDER=dev`): open the app → enter an email → **Send magic link** → click the **Dev: open magic link** button → land in the shell authenticated with the real tenant + tier. Reusing the link fails (410). Backend (ruff + pytest incl. real-Redis magic tests) and web (typecheck/lint/test/build) gates all green.

---

## 8. Production (Clerk) note
No new backend code for prod: enable **Email magic link** in the Clerk dashboard; the Clerk frontend bridge (deferred) renders Clerk's sign-in; the backend `ClerkAuthProvider` verifies the resulting JWT. The self-hosted endpoints stay dev-only.
