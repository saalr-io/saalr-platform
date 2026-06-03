# Billing frontend (B2) — design

**Status:** approved design, 2026-06-03. Slice **B2** (frontend) of billing; builds on **B1**
(backend, `docs/superpowers/specs/2026-06-03-stripe-billing-backend-design.md`).

## Goal

Close the conversion loop: give `apps/web` a pricing/upgrade surface that turns the existing 402
upgrade nudges into real Stripe Checkout flows, shows the current plan, and lets a subscriber manage
billing — all over the B1 endpoints, with **no gating changes**.

## B1 endpoints consumed (all bearer-authed; base `import.meta.env.VITE_API_BASE_URL ?? '/api'`)

- `GET /subscription` → `{ tier, status, current_period_end, cancel_at_period_end, entitlements }`
  (`tier` ∈ free|pro|premium; `status` ∈ active|trialing|past_due|...).
- `POST /subscription/upgrade` body `{ tier: 'pro'|'premium' }` → `{ checkout_url }`. Honors
  `Idempotency-Key`. 503 `FEATURE_UNAVAILABLE` (billing unconfigured); 502 `BILLING_UNAVAILABLE`.
- `POST /subscription/portal` → `{ portal_url }`. 409 `BILLING_NO_CUSTOMER` (no Stripe customer yet).
- Backend redirect targets (env-configurable): success `/app/billing/success`, cancel
  `/app/billing/cancel`, portal return `/app/billing`.

## Decisions (locked)

- **Nudges route to `/app/billing`** (not straight to checkout) — one canonical upgrade surface; the
  relevant plan is pre-highlighted via `?plan=pro|premium`.
- **Success page polls** `GET /subscription` until the tier flips (the `checkout.session.completed`
  webhook may lag the redirect), then refreshes the session; times out to a "processing" message.
- **No prices on the cards** — Stripe Checkout is the price source of truth (no frontend drift,
  consistent with the pre-revenue "no fabricated numbers" stance).
- Full-page redirect to Stripe (`window.location.assign`) via a mockable `redirectTo` helper.
- Entry points: a "Billing" sidebar item + the Topbar tier chip becomes a link to `/app/billing`.

## Components / files

- **`src/lib/billing.ts`** — typed client over the existing `request()` wrapper (401→logout,
  402→`EntitlementError`, else `Error(code)`):
  - `getSubscription(): Promise<Subscription>` where `Subscription = { tier, status,
    current_period_end: string|null, cancel_at_period_end: boolean, entitlements: Record<...> }`.
  - `startUpgrade(tier: 'pro'|'premium'): Promise<{ checkout_url: string }>`.
  - `openPortal(): Promise<{ portal_url: string }>`.
  - `redirectTo(url: string): void` — defaults to `window.location.assign(url)`; isolated so tests
    can spy on it without a real navigation.
- **`src/lib/tiers.ts`** *(refactor — DRY)* — move the marketing `TIERS` data here, each entry gaining
  a lowercase **`key: TierName`** (`'free'|'pro'|'premium'`) alongside the existing display
  `name`/`tagline`/`features[]`/`highlight?` (so billing can compare a card against the current
  `tier`). Also export `TIER_RANK: Record<TierName, number>` (free<pro<premium) for "is this an
  upgrade?" checks. `src/features/marketing/Tiers.tsx` and billing both import from here; the marketing
  `copy.ts` re-exports `TIERS` so the landing is unchanged visually.
- **`src/features/billing/hooks.ts`** — `useSubscription()` (TanStack Query, key `['subscription']`),
  `useUpgrade()` (mutation → on success `redirectTo(checkout_url)`), `usePortal()` (mutation → on
  success `redirectTo(portal_url)`).
- **`src/features/billing/PlanCards.tsx`** — three cards from `TIERS`. For each: if it's the current
  tier → a "Current plan" disabled pill; if higher than current → an "Upgrade" button calling
  `useUpgrade().mutate(tier)`; free card never upgradeable. `?plan` query → accent-highlight that
  card. While a mutation is pending → button shows "Starting…" and is disabled. On `EntitlementError`
  or a 503-coded error → inline "Billing isn't available right now."; on other error → "Couldn't
  start checkout — try again."
- **`src/pages/Billing.tsx`** — the `/app/billing` page (rendered in `AppShell` outlet): a
  `// Billing` mono kicker + `h2`, a current-plan summary line from `useSubscription` (tier + status;
  if `cancel_at_period_end` show "cancels on {date}", else for paid show "renews {date}"), the
  `PlanCards`, and a **"Manage billing"** button (calls `usePortal`) shown when the current tier is
  not free (a Stripe customer exists). 409 `BILLING_NO_CUSTOMER` from portal → hide/disable with a
  hint. Reads `?plan` from the URL to pass the highlight to PlanCards.
- **`src/pages/BillingSuccess.tsx`** — `/app/billing/success`. Captures the tier at mount; polls
  `useSubscription` with `refetchInterval` ~2000ms while not yet flipped and elapsed < ~20s. When the
  returned `tier` differs from the mount tier (or is non-free) → stop polling, show "You're on
  {Tier} 🎉" + a "Go to the app" link, and call `auth.refresh()` so the whole app sees the new tier.
  On timeout → "Payment received — your plan will update shortly." + a "Refresh" button (refetch) +
  a link to `/app/billing`.
- **`src/pages/BillingCancel.tsx`** — `/app/billing/cancel`. "Checkout canceled — no charge was
  made." + a link back to `/app/billing`.
- **`src/auth/AuthContext.tsx`** — add `refresh: () => Promise<void>` to `AuthContextValue` and expose
  the existing internal `refresh` (re-runs `getMe`, updating `me.tier`). No behavior change elsewhere.
- **Nudge wiring** (each currently a static panel; add an Upgrade link via react-router `<Link>`):
  - `src/features/academy/ModuleReader.tsx` `UpgradeNudge` → `<Link to="/billing?plan=pro">Upgrade to Pro</Link>`.
  - `src/features/academy/AskAssistant.tsx` entitlement nudge → `<Link to="/billing?plan=pro">`.
  - `src/features/research/PremiumGate.tsx` → `<Link to="/billing?plan=premium">Upgrade to Premium</Link>`
    (replace the "contact your account team" line).
- **`src/app/Router.tsx`** — add `<Route path="billing" element={<Billing/>} />`,
  `billing/success` → `<BillingSuccess/>`, `billing/cancel` → `<BillingCancel/>`.
- **`src/components/Sidebar.tsx`** — add `['/billing','Billing']` (e.g. in a "System"/account section).
- **`src/components/Topbar.tsx`** — wrap the existing tier chip in `<Link to="/billing">`.

## Data flow

1. Nudge "Upgrade" → `/app/billing?plan=…`. 2. PlanCards "Upgrade" → `startUpgrade(tier)` →
`redirectTo(checkout_url)` (leaves the SPA for Stripe). 3. Stripe → `/app/billing/success` (or
`/cancel`). 4. Success polls `/subscription` until the tier flips → `auth.refresh()` → confirmation.
Manage billing → `openPortal()` → `redirectTo(portal_url)` → Stripe portal → returns to `/app/billing`.

## Error handling

- 503 `FEATURE_UNAVAILABLE` → upgrade/manage actions render a disabled "Billing isn't available"
  state, never a crash. Nudges still render (informational + the link).
- 502 `BILLING_UNAVAILABLE` → "Couldn't start checkout — try again."
- 409 `BILLING_NO_CUSTOMER` on portal → manage-billing hidden/disabled (no customer yet).
- 401 → the shared wrapper logs out (existing behavior).

## Testing (vitest + @testing-library/react; mock `fetch`, spy on `redirectTo`)

- `src/lib/billing.test.ts` — each method's URL/method; a 402 throws `EntitlementError`; a 503-coded
  error surfaces its code.
- `PlanCards.test.tsx` — current tier shows "Current plan" (disabled); a higher tier's "Upgrade"
  calls the client and then `redirectTo(checkout_url)`; `?plan` highlights the right card.
- `Billing.test.tsx` — renders the current plan from a mocked `/subscription`; "Manage billing" calls
  the portal client → `redirectTo(portal_url)`; manage hidden when tier is free.
- `BillingSuccess.test.tsx` — `/subscription` returns `free` then `pro` across polls → shows the
  confirmation and calls `auth.refresh()`; a never-flipping mock → the timeout/"processing" branch.
- Nudge tests (extend the existing academy/research tests) — each nudge renders an upgrade link to
  `/billing?plan=…`.
- Gate: `npm run typecheck && npm run lint && npm run test:run` (all green); `npm run build` still
  prerenders the public pages (these are all client-only `/app` routes — no SSG impact).

## Out of scope (later)

Annual plans; in-app price display; proration UI; a `past_due` "update your card" banner on the
billing page (nice follow-up); Razorpay; a Clerk frontend bridge.
