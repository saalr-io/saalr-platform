# Billing & Growth Update — Design

**Date:** 2026-06-06
**Status:** Approved (brainstorming)
**Slice:** One cohesive monetization-&-growth slice in three parts:
- **A — New entitlements + plan copy** for the recently shipped features.
- **B — Monthly/Annual billing toggle** with a reasonable annual discount.
- **C — Marketing audience**: opt-in/unsubscribe schema, a `marketing_audience` view, and a
  one-command CSV export for surveys/email marketing.

Build order: A → B → C. Each part is independently testable.

## Goal

Advertise and gate the new capabilities correctly, let users choose monthly vs. discounted annual
billing, and give the founder a compliant, one-command way to pull a user/engagement email list for
a survey and focused email marketing.

## Context (existing pieces)

- **Entitlements** live in `packages/core/saalr_core/tiers.py`:
  `Entitlements(live_chains, vol_surface, ml_forecast, research_agent, brokers)`; `TIERS` maps
  free/pro/premium; `entitlements_for(tier)` returns a dict (used by `/me`, `/subscription`, gating).
- **Gating**: `apps/api/saalr_api/forecast/gating.py::require_ml_forecast` is the single Pro+ gate
  used by the vol-forecast endpoint, the **price-forecast** endpoint (`forecast/router.py`), the
  Monte-Carlo endpoint, and a content/assistant endpoint. The sentiment endpoint
  (`apps/api/saalr_api/sentiment/router.py`) is gated equivalently (Pro+).
- **Checkout**: `apps/api/saalr_api/billing/service.py::start_upgrade(...tier)` picks
  `settings.stripe_price_pro`/`stripe_price_premium` and creates a Stripe Checkout session
  (`trial_days=14` for pro). `_price_map(settings)` maps price-id → tier for the webhook reducer.
  Frontend: `lib/billing.ts::startUpgrade(tier)` → `POST /subscription/upgrade {tier}`;
  `features/billing/hooks.ts::useUpgrade`; `features/billing/PlanCards.tsx` renders the cards.
- **Plan copy**: `apps/web/src/lib/tiers.ts` (`TIERS`) is the single source for both the marketing
  landing and in-app `PlanCards`. The app shows **no dollar prices** — Stripe Checkout is the price
  source of truth.
- **User/engagement data**: `users(email, email_verified_at, created_at, …)`,
  `memberships → tenants → subscriptions(tier, status)`, and engagement tables `strategies`,
  `orders`, `backtests`, `user_progress` (all tenant-scoped, FORCE RLS — admin/superuser bypasses).

**Decisions locked (Q&A):** `price_forecast` = **Premium-only**; `news_sentiment` = **Pro+**; annual
discount = **2 months free (~17%)**, shown as a badge (no hardcoded dollars); marketing work folded
in; ≤50 paid users expected in 2026 → keep everything simple.

---

# Part A — New entitlements + plan copy

## Entitlements (`packages/core/saalr_core/tiers.py`)
Append two fields to `Entitlements` **with `= False` defaults** (so existing positional
constructions like `Entitlements(False, False, False, False, 0)` keep working):
`price_forecast: bool = False`, `news_sentiment: bool = False`. Map across tiers:

| tier | live_chains | vol_surface | ml_forecast | price_forecast | news_sentiment | research_agent | brokers |
|---|---|---|---|---|---|---|---|
| free | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 0 |
| pro | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | 2 |
| premium | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 4 |

`ml_forecast` (vol forecast + HAR + Monte-Carlo) stays Pro+ — unchanged.

## Gating (`apps/api/saalr_api/forecast/gating.py` + endpoints)
- Add `require_price_forecast` (checks `entitlements_for(tier)["price_forecast"]`) → 402
  `ENTITLEMENT_PRICE_FORECAST_REQUIRES_PREMIUM` ("AI price forecasts require a Premium plan").
- Add `require_news_sentiment` (checks `news_sentiment`) → 402
  `ENTITLEMENT_NEWS_SENTIMENT_REQUIRES_PRO`.
- **Price-forecast endpoint** (`forecast/router.py` `price_forecast_endpoint`): swap
  `require_ml_forecast` → `require_price_forecast` (now Premium-only).
- **Sentiment endpoint** (`sentiment/router.py`): swap its current Pro+ gate →
  `require_news_sentiment` (access-neutral; both Pro+).
- Vol-forecast, Monte-Carlo, assistant endpoints keep `require_ml_forecast`.

## Frontend gating (`apps/web/src/pages/Models.tsx` + entitlements type)
- Extend the frontend `Entitlements` shape (wherever `me.entitlements` is typed) with
  `price_forecast: boolean`, `news_sentiment: boolean`.
- The Models page still **opens at Pro+** (`ml_forecast`). Make the **Price forecast panel
  per-panel gated**:
  - `priceEntitled = me.entitlements.price_forecast`; call `usePriceForecast(priceEntitled ? ticker : '', horizon, priceEntitled)`.
  - When `priceEntitled` is false, render a small upsell card in the price-panel slot:
    "📈 AI price forecasts (ARIMA & LSTM) are a Premium feature — Upgrade" linking to `/billing`.
  - **Remove `priceQ.error` from the page-level `EntitlementError → ModelsGate` guard** so a Pro
    user is never whole-page-gated by a price-forecast 402 (it can't 402 now since the query is
    disabled client-side, but the guard must not reference it).
- Sentiment query gated on `news_sentiment` (Pro+); since the page already requires `ml_forecast`
  (Pro+) and `news_sentiment` is also Pro+, behaviour is unchanged, but gate on the explicit flag.

## Plan copy (`apps/web/src/lib/tiers.ts`)
- **Free** `features`: keep "Strategy builder & payoff analysis", "OptionsAcademy lessons",
  add "In-app help on every model & strategy".
- **Pro** `features`: "Live options chains & IV surface", "GARCH & HAR vol forecasts · Monte-Carlo POP",
  "News sentiment", "Grounded Q&A assistant", "Everything in Free".
- **Premium** `features`: "AI price forecasts (ARIMA & LSTM)" (headline differentiator),
  "Multi-agent Research Agent notes", "Higher run & rate limits", "Everything in Pro".

## Part A tests
- `tiers`/billing-reducer test: `premium.price_forecast` is True, `pro.price_forecast` False;
  `pro`/`premium` `news_sentiment` True; `free` both False.
- Price-forecast integration: **pro → 402** `ENTITLEMENT_PRICE_FORECAST_REQUIRES_PREMIUM`,
  **premium → 200**, free → 402. (Flip the existing pro=200 test to premium.)
- Sentiment integration: free → 402, pro → 200 (news_sentiment).
- Update entitlement fixtures across web + api tests for the two new fields.
- Frontend: tiers-copy test; Models price-panel test — premium renders the panel, pro renders the
  upsell card (NOT a blocked page).

**Breaking change (intended):** Pro users lose the price-forecast panel — the deliberate Premium
upsell.

---

# Part B — Monthly/Annual billing toggle

## Config (`packages/core/saalr_core/config.py`)
Keep `stripe_price_pro` / `stripe_price_premium` as the **monthly** price IDs; add
`stripe_price_pro_annual: str | None = None` and `stripe_price_premium_annual: str | None = None`.

## Backend (`apps/api/saalr_api/billing/`)
- `start_upgrade(session, provider, settings, tenant_id, email, tier, interval="monthly")`:
  resolve the price by `(tier, interval)`:
  - pro/monthly → `stripe_price_pro`; pro/annual → `stripe_price_pro_annual`
  - premium/monthly → `stripe_price_premium`; premium/annual → `stripe_price_premium_annual`
  - If the requested annual price ID is unset, fall back to the monthly one (so annual is a no-op
    until the founder sets the Stripe IDs) — keeps dev/local working. Trial logic unchanged.
- `_price_map(settings)`: include **all four** price IDs → tier, so the webhook reducer maps annual
  subscriptions to the correct tier (interval doesn't affect entitlements).
- `billing/router.py` upgrade endpoint: accept `interval: "monthly" | "annual"` in the request body
  (default `"monthly"`; reject other values with 422); pass through to `start_upgrade`.

## Frontend (`apps/web/src/features/billing/`, `lib/billing.ts`)
- `lib/billing.ts::startUpgrade(tier, interval)` → `POST /subscription/upgrade {tier, interval}`.
- `hooks.ts::useUpgrade`: mutation variable becomes `{ tier, interval }`.
- `PlanCards.tsx`: add a **Monthly / Annual segmented toggle** above the grid (local state, default
  Monthly). When **Annual** is selected, the Pro & Premium cards show a badge
  "Save 17% · 2 months free", and `Upgrade to …` calls `upgrade.mutate({ tier, interval: 'annual' })`.
  Free card unaffected.

## Part B tests
- Service: `start_upgrade` picks the correct price ID for all four `(tier, interval)` combos;
  unset annual ID falls back to monthly; `_price_map` contains all four IDs.
- Router: `interval` defaults to monthly; invalid interval → 422; annual passes through.
- Frontend: toggle switches interval (default monthly); Annual shows the badge and
  `useUpgrade` is invoked with `interval: 'annual'`; Monthly invokes with `'monthly'`.

---

# Part C — Marketing audience (opt-in, view, export, unsubscribe)

## Migration (`infra/migrations/versions/0013_marketing_audience.py`, `revision = "0013"`, `down_revision = "0012"`)
- `ALTER TABLE users ADD COLUMN marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE;`
- `ALTER TABLE users ADD COLUMN unsubscribe_token UUID NOT NULL DEFAULT gen_random_uuid();`
  + `CREATE UNIQUE INDEX idx_users_unsubscribe_token ON users(unsubscribe_token);`
- `CREATE VIEW marketing_audience AS` selecting per user:
  `email, email_verified_at, created_at, marketing_opt_in, unsubscribe_token,
   COALESCE(s.tier,'free') AS tier`, plus engagement booleans via `EXISTS`:
  `has_strategy`, `has_traded` (orders), `has_backtest`, `has_progress` (user_progress).
  Joined `users → memberships → tenants`, LEFT JOIN active/trialing `subscriptions`.
  (The view is for admin/superuser export use; it inherits RLS, so it returns rows only under the
  bypassing admin role — which is how exports run.)
- `downgrade()` drops the view, index, and columns.

## One-command CSV export (`scripts/export_audience.py`)
- Reads `ADMIN_DATABASE_URL` (superuser, RLS-bypassing). Selects from `marketing_audience`.
- Flags: `--segment {all,verified,engaged,opted-in}` (default `verified` →
  `email_verified_at IS NOT NULL`); `engaged` → any engagement bool true; `opted-in` →
  `marketing_opt_in`. `--out audience.csv` (default stdout).
- Writes CSV with a header row (`email,tier,verified,opted_in,has_strategy,has_traded,has_backtest,has_progress`).
- Pure-ish: factor the segment→SQL/WHERE mapping into a tested helper; the I/O wrapper runs the query.

## Unsubscribe endpoint (`apps/api/saalr_api/marketing/router.py`, public)
- `GET /unsubscribe?token=<uuid>` — **no auth**. Sets `marketing_opt_in = FALSE` where
  `unsubscribe_token = :token` (admin/definer write, since `users` is not tenant-scoped by the
  caller's GUC). Returns a small confirmation (`200` JSON `{"unsubscribed": true}` or a tiny HTML
  page). Unknown/ malformed token → the SAME neutral `200` confirmation (no user enumeration).
  Idempotent. Mounted in `main.py`.
- Email links use `{web_base_url or billing_*_url host}/api/unsubscribe?token=…` — exact base URL is
  an ops detail; the endpoint path is `/unsubscribe`.

## Out of scope (Part C, YAGNI)
- In-app opt-in toggle / signup consent checkbox (easy follow-up once sending starts).
- Double opt-in, ESP integration, sending infrastructure (use an external ESP with the CSV).

## Part C tests
- Migration: `alembic upgrade` then `downgrade` round-trips; `marketing_audience` returns the
  expected columns and correct engagement flags for a seeded user with/without a strategy/order.
- Export helper: each `--segment` maps to the right WHERE clause; CSV writer emits a header + rows.
- Unsubscribe integration: a known token flips `marketing_opt_in` to false and is idempotent;
  an unknown token returns the same neutral `200`; the endpoint requires no auth.

---

## Cross-cutting / sequencing
- Build A → B → C. A touches entitlements + gating + frontend; B touches billing service/UI; C is a
  migration + script + one public endpoint. They share no files except `config.py` (A adds nothing
  there; B adds price IDs; C adds nothing) and the test fixtures (A).
- `/me` and `/subscription` payloads gain `price_forecast`/`news_sentiment` automatically via
  `entitlements_for` — the API needs a restart to serve the new shape (note for the founder).

## Out of scope (whole slice)
- Changing actual dollar prices (Stripe-managed); proration UI; multi-currency; per-seat billing.
- Razorpay/other providers (Stripe path only).
