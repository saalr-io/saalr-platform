# Onboarding & Account/Settings — Design

**Date:** 2026-06-07
**Status:** Approved (brainstorming; lean defaults locked)
**Slice:** Two net-new, independent slices built in sequence:
- **Slice 1 — Beginner onboarding & activation** (Dashboard checklist + guided `/app/start` flow, server-side step state).
- **Slice 2 — Account / Settings page** (marketing opt-in, profile edit, manage-subscription, request-deletion).

Context: pre-launch, local dev, ≤50 users expected → build lean. The SEO/GEO public surface already
exists (Vike SSG: `/`, `/learn`, `/glossary`, `/academy` + sitemap/llms.txt) and is OUT of scope.

## Locked decisions

- Onboarding mechanism = **checklist + guided flow**; step-completion = **server-side step state**.
- Settings = **fuller account page**, but with two lean treatments:
  - **Delete-account → "Request deletion"**: a `users.deletion_requested_at` flag set via an
    endpoint; the founder actions it manually. No live destructive cascade now.
  - **Notifications** folded into the **marketing opt-in** (Email preferences). No standalone
    notifications panel (there is no notifications system to back it yet).

## Context (existing pieces)

- Web app = **Vike** (`apps/web/pages/app/*` is the client-routed authed SPA under `/app`, via
  `apps/web/src/app/Router.tsx` with react-router `basename="/app"`). Dashboard = `src/pages/Dashboard.tsx`.
- Auth: `/me` (`apps/api/saalr_api/main.py`) returns `user{id,email}`, `tenant`, `tier`,
  `entitlements`. `users` columns include `email`, `preferred_tz`, `preferred_locale`, and (from the
  billing slice) `marketing_opt_in`, `unsubscribe_token`. Public `GET /unsubscribe?token=` already
  sets opt-in false.
- Tenant-per-user model; tenant-scoped tables are FORCE RLS with a `tenant_isolation` policy keyed on
  `current_setting('app.current_tenant')`. `get_principal` sets that GUC and yields `(session, principal)`.
- Billing: `POST /subscription/portal` (Stripe portal) + `pages/Billing.tsx`.
- Trade Ideas / regime: `pages/Ideas.tsx` + regime/recommendation hooks; paper-trade via
  `features/portfolio/usePaperTrade.ts` (`usePaperTradeStrategy`). Academy lesson progress lives in
  `user_progress` (content router).

---

# Slice 1 — Onboarding & activation

## Canonical steps
A shared constant (backend + frontend kept in sync): `build_strategy`, `see_regime`, `paper_trade`,
`read_lesson`. All four complete ⇒ activated.

## Migration `0014_onboarding` (`infra/migrations/versions/0014_onboarding.py`, rev 0014 / down 0013)
- `CREATE TABLE onboarding_progress (tenant_id uuid NOT NULL REFERENCES tenants, step text NOT NULL,
  completed_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (tenant_id, step));`
- Add to the FORCE-RLS set with the standard `tenant_isolation` USING/WITH CHECK policy + grants to
  `saalr_app` (mirror the baseline pattern).
- Also (Slice 2): `ALTER TABLE users ADD COLUMN deletion_requested_at timestamptz;` (no default).
- `downgrade()` drops the table/policy and the column.

## API (`apps/api/saalr_api/onboarding/`)
- `repo.py`: `list_steps(session, tenant_id) -> set[str]`; `mark_step(session, tenant_id, step)`
  (idempotent `INSERT ... ON CONFLICT DO NOTHING`). RLS GUC is already set by `get_principal`.
- `router.py`:
  - `GET /onboarding` → `{ "steps": [...completed...], "all_done": bool }` (all_done = the 4 canonical
    steps are all present).
  - `POST /onboarding/complete` body `{ "step": str }` → 400 `VALIDATION_INVALID_PARAMETER` if step ∉
    canonical set; else `mark_step`; returns the updated `{steps, all_done}`.
  - Both `Depends(get_principal)`.
- The canonical step list is a module constant `ONBOARDING_STEPS` (also exposed for the test).

## Frontend
- `lib/onboarding.ts` — `getOnboarding()`, `completeStep(step)` types/fetch.
- `features/onboarding/hooks.ts` — `useOnboarding()` (query), `useCompleteStep()` (mutation that
  invalidates `['onboarding']`).
- `features/onboarding/GettingStarted.tsx` — a Dashboard card: the 4 steps with ✓/○, each a
  `<Link>` to where it's done (Strategies / Ideas / Start / Education), a progress count, and a
  **Dismiss** (persisted in `localStorage: saalr.onboarding.dismissed`). Renders nothing when
  `all_done` or dismissed. `data-testid="getting-started"`.
- `pages/Start.tsx` (`/app/start`) — a **linear guided flow** (local step index):
  1. enter a ticker → 2. show its regime + top recommendation (reuse the Ideas regime/reco hooks) →
  3. "Paper-trade this" (reuse `usePaperTradeStrategy`) → 4. done panel linking to `/portfolio`.
  Each milestone calls `completeStep('see_regime' | 'paper_trade')`. Has `data-testid` anchors per step.
- **completeStep wiring at real action sites** (so credit is earned even outside the guided flow):
  - Strategies save success → `completeStep('build_strategy')`.
  - paper-trade success (RecoCard / Strategies / Start) → `completeStep('paper_trade')`.
  - Education lesson opened → `completeStep('read_lesson')`.
  - Ideas page regime loaded → `completeStep('see_regime')`.
  Use a tiny `useCompleteStep()` call guarded so it only fires once per session per step (the backend
  is idempotent regardless).
- Router/nav: add `/app/start` route; Dashboard renders `<GettingStarted/>` at top; the app nav shows
  a "Start here" entry while `!all_done` (optional—at minimum the checklist links to it).

## Slice 1 testing
- API: `GET /onboarding` empty → `{steps:[],all_done:false}`; `POST complete` marks + idempotent;
  bad step → 400; two tenants are isolated (RLS) — tenant B never sees tenant A's steps.
- Web: `GettingStarted` renders 4 items, reflects completed state, hides on dismiss/all_done;
  `useCompleteStep` invalidates; `/app/start` renders step 1 and advances on a stubbed regime/reco.

---

# Slice 2 — Account / Settings

## API (`apps/api/saalr_api/`)
- **Extend `/me`** (in `main.py`) to also return `marketing_opt_in`, `preferred_tz`,
  `preferred_locale`, and `deletion_requested` (bool) — read from the `users` row for the principal.
  (Add a small `users`-row fetch in the `/me` handler alongside the tenant fetch.)
- New `account/router.py`:
  - `POST /me/marketing/opt-in` `{opt_in: bool}` → set `users.marketing_opt_in` for `principal.user_id`.
  - `PATCH /me/profile` `{preferred_tz?: str, preferred_locale?: str}` → update provided columns
    (validate: non-empty, length ≤ 64; reject unknown keys via the pydantic model).
  - `POST /me/request-deletion` → set `users.deletion_requested_at = now()` (idempotent); returns
    `{requested: true}`. (Founder processes manually; no cascade.)
  - All `Depends(get_principal)`; write keyed on `principal.user_id` (`users` is not tenant-RLS-scoped,
    so a direct keyed UPDATE works — same pattern as the public `/unsubscribe`).

## Frontend `pages/Settings.tsx` (`/app/settings`)
- `lib/account.ts` + `features/account/hooks.ts` (`useOptIn`, `useUpdateProfile`, `useRequestDeletion`;
  current values come from the `useAuth().me` which now carries the new fields, refetched after mutate).
- Sections:
  - **Account** — email + tier (read-only); "Manage subscription" → triggers the existing portal
    (`usePortal`) or links to `/billing`.
  - **Profile** — timezone + locale inputs (save → `PATCH /me/profile`).
  - **Email preferences** — a single marketing opt-in toggle (reflects `me.marketing_opt_in`; toggling
    calls `POST /me/marketing/opt-in`). Copy notes this controls product/marketing emails.
  - **Danger zone** — "Request account deletion": a typed-"DELETE" confirm → `POST /me/request-deletion`;
    afterwards shows "Deletion requested — we'll process it shortly." (No destructive action client-side.)
- `AuthContext.me` type/refresh: after opt-in/profile mutations, invalidate/refetch `me` so the UI
  reflects server state. Nav + `/app/settings` route added (e.g., under a user menu or nav footer).

## Slice 2 testing
- API: `/me` includes the three new fields; `POST /me/marketing/opt-in` flips the column (true→false→true)
  and `/me` reflects it; `PATCH /me/profile` updates tz/locale and rejects an unknown field (422);
  `POST /me/request-deletion` sets `deletion_requested_at` and is idempotent.
- Web: Settings renders all four sections; the opt-in toggle reflects `me` and calls the mutation;
  the delete-request requires the typed confirmation before enabling the button.

---

## Cross-cutting / sequencing
- Build order: Slice 1 (migration 0014 → onboarding API → onboarding web) → Slice 2 (account API →
  Settings web). The migration carries BOTH the onboarding table and the `deletion_requested_at`
  column (one migration, since both are this slice's schema).
- `/me` shape grows (additive) — the frontend entitlements/me type is a loose object, so additive
  fields don't break existing consumers; the API needs a restart to serve the new `/me` (founder note).

## Out of scope (YAGNI / lean)
- Live destructive account deletion (request-flag only); a standalone notifications system/panel;
  funnel analytics dashboards; SEO-polish (separate, already-mostly-built surface); double opt-in.
