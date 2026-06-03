# Stripe billing backend (B1) — design

**Status:** approved design, 2026-06-03. Slice **B1** of the billing feature (backend only;
B2 = frontend pricing/upgrade UI is a separate slice).

## Goal

Make the existing tier/entitlement system *convert*: let a tenant subscribe to **Pro** or
**Premium** via Stripe so the `subscriptions` row that already drives `auth_resolve_principal`
gets updated — flipping the tenant's entitlements with **zero changes to gating code**.

## Why this is clean (existing foundation)

- **Tier source of truth already routes through billing.** `auth_resolve_principal()`
  (`infra/migrations/versions/0002_auth_functions.py`) computes a principal's tier as
  `COALESCE(s.tier, 'free')` from the tenant's **active** `subscriptions` row.
- `auth_bootstrap()` already seeds one `free` / `active` / `manual` subscription per tenant on
  signup (period = now → +100y), and a unique partial index enforces **one active sub per tenant**.
- The `subscriptions` + `billing_events` tables already exist as SQLAlchemy models
  (`packages/core/saalr_core/db/models/billing.py`), matching LLD §3.2.
- HLD §4 already specs the endpoints (`/subscription`, `/subscription/upgrade`,
  `/subscription/cancel`, `/webhooks/stripe`) and the **idempotent-webhook** requirement. (B1
  consolidates the HLD's `/subscription/cancel` into the Stripe-hosted Billing Portal — see Endpoints.)

So B1's job is: drive that one subscription row from Stripe, idempotently.

## Decisions (locked)

- **Scope:** backend first (this slice). Frontend = B2.
- **Provider:** Stripe only, behind a thin `PaymentProvider` seam (Razorpay slots in later).
- **Plans:** monthly **Pro** and **Premium**. **14-day trial on Pro only**; Premium has no trial.
- **Tests:** deterministic unit + integration tests using a Stub/mocked provider (default gate,
  no keys); plus an **env-gated live Stripe test-mode smoke**.

## Approach: webhook-driven single-row model

Keep exactly **one entitled subscription row per tenant** (the one `auth_bootstrap` seeds). Stripe
is the system of record; the webhook reduces Stripe events into that row's
`tier/status/provider/provider_subscription_id/current_period_*/cancel_at_period_end`. Upgrade
transitions the existing row (free→pro/premium), cancel flips `cancel_at_period_end`, and
`customer.subscription.deleted` reverts it to free/manual. `billing_events` holds the full history.

*Alternative considered:* a separate `billing_customers` table + multi-row subscription history.
More faithful to Stripe but more moving parts and a schema departure; rejected in favour of the
single-row model that the existing resolver + unique index already assume. History lives in
`billing_events`.

## Trial ⇒ resolver change (essential)

Stripe trials carry `status = 'trialing'`, but `auth_resolve_principal` joins on `status =
'active'` only — so without a change, a trialing Pro user would resolve to **free**. B1 must, in a
migration:

- `CREATE OR REPLACE FUNCTION auth_resolve_principal` → join on `s.status IN ('active','trialing')`.
- Recreate the unique partial index `idx_subscriptions_tenant_active` as
  `WHERE status IN ('active','trialing')` so a tenant still can't hold two entitled rows.

`entitlements_for(tier)` is unchanged — a trialing Pro row has `tier='pro'`, so it grants Pro
entitlements for the trial window, then `invoice.paid`/`subscription.updated` moves it to `active`.

## Components — `apps/api/saalr_api/billing/`

- **`provider.py`** — `PaymentProvider` protocol:
  - `ensure_customer(tenant_id, email, existing_id) -> customer_id`
  - `create_checkout_session(customer_id, price_id, *, tenant_id, trial_days, success_url, cancel_url) -> url`
  - `create_portal_session(customer_id, return_url) -> url`
  - `verify_webhook(payload: bytes, sig_header: str) -> dict` (raises on bad signature)

  (No explicit cancel method — cancellation is handled inside the Stripe-hosted Billing Portal.)

  `StripeProvider` wraps the **sync** `stripe` SDK via `asyncio.to_thread` (same pattern as the
  sync-boto3 AWS adapters). `stripe` is **lazy-imported** inside the methods so importing the
  module is dependency-free. A `StubProvider` returns deterministic fake URLs/ids and verifies a
  fake signature for tests.

- **`reducer.py`** — the pure heart of the slice:
  `apply_subscription_event(current: SubscriptionState | None, event: dict) -> SubscriptionState`.
  Maps each Stripe event to the new row state. No I/O, no Stripe import — fully unit-testable.
  Price→tier comes from an injected `{price_id: tier}` map (built from config). Handled events:
  - `checkout.session.completed` → set `provider_subscription_id`, `tier` (from the line-item
    price), `status` (`trialing` if a trial is present else `active`), periods. (The Stripe customer
    id lives on `tenants`, not the subscription row — persisted at upgrade time, below.)
  - `customer.subscription.updated` → refresh `status`, `current_period_*`, `cancel_at_period_end`,
    and `tier` (in case of plan change).
  - `customer.subscription.deleted` → revert to `tier='free'`, `status='active'`,
    `provider='manual'`, clear `provider_subscription_id` (the tenant's `stripe_customer_id` stays).
  - `invoice.payment_failed` → `status='past_due'`.
  - `invoice.paid` → `status='active'`.
  - any other type → returns `current` unchanged (caller will still record the event + 200).

- **`repo.py`** —
  - `get_subscription(session, tenant_id)` (the single row).
  - `upsert_subscription(session, tenant_id, state)` (updates the existing entitled row in place).
  - `get/set_customer_id(session, tenant_id)` — reads/writes `tenants.stripe_customer_id`.
  - `record_billing_event(session, tenant_id, subscription_id, event) -> bool` — inserts with the
    unique `provider_event_id`; returns `False` (no-op) if the event was already recorded.

- **`service.py`** —
  - `get_subscription(...)` → `{tier, status, current_period_end, cancel_at_period_end,
    entitlements: entitlements_for(tier)}`.
  - `start_upgrade(session, principal, tier)` → ensure customer (lazy create + persist id) →
    `create_checkout_session` with the tier's price, `trial_days=14` **iff tier=='pro'**,
    success/cancel URLs, and `tenant_id` stamped as **both** the checkout-session `metadata` **and**
    `subscription_data.metadata` (so every later subscription/invoice event also carries it) →
    `{checkout_url}`.
  - `portal(...)` → `{portal_url}` (the tenant's customer id → a Billing Portal session; this is
    where the user changes card, cancels, or switches plan).
  - `handle_webhook(payload, sig_header)` → verify → resolve tenant (`metadata.tenant_id`, else the
    `tenants.stripe_customer_id` lookup) → open a `tenant_session` → **one transaction**:
    `record_billing_event` (idempotency gate) **and** `upsert_subscription(reduce(...))`. Duplicate
    event ⇒ commit nothing, return 200. **Unknown tenant ⇒ 400** (see Error handling).

- **`router.py`** — the 4 endpoints. `/subscription*` use `get_principal` (any authed tenant may
  read/upgrade/open the portal). `/webhooks/stripe` is **unauthenticated** and signature-verified;
  it reads the raw request body (not parsed JSON) for signature validation.

## Endpoints

| Method | Path | Auth | Returns |
|---|---|---|---|
| GET | `/subscription` | principal | `{tier, status, current_period_end, cancel_at_period_end, entitlements}` |
| POST | `/subscription/upgrade` | principal | `{checkout_url}` (body `{tier: 'pro'\|'premium'}`); honours `Idempotency-Key` |
| POST | `/subscription/portal` | principal | `{portal_url}` (manage card / cancel / switch plan — Stripe-hosted) |
| POST | `/webhooks/stripe` | signature | `{received: true}` (always 200 on a valid sig, even for ignored/duplicate events) |

## Config / secrets

Add to `config.py` (read from `.env`, gitignored): `stripe_secret_key`, `stripe_webhook_secret`,
`stripe_price_pro`, `stripe_price_premium`, `billing_success_url`, `billing_cancel_url`.
`stripe` is an **optional extra** (`saalr-api[stripe]`). The app builds a `StripeProvider` only when
`stripe_secret_key` is set; otherwise billing endpoints return **503 FEATURE_UNAVAILABLE**.

## Error handling

- Missing billing config → **503** `FEATURE_UNAVAILABLE`.
- Stripe API error (network/declined-at-API) → **502** `BILLING_UNAVAILABLE` (never a 500).
- Bad/absent webhook signature → **400** `VALIDATION_INVALID_PARAMETER` (no state change).
- Webhook for an unknown tenant (no matching `metadata.tenant_id` and no `tenants.stripe_customer_id`
  match) → **400** `BILLING_UNKNOWN_TENANT` + log a warning. We deliberately surface this as a 4xx so
  it shows up as a failed delivery in the Stripe dashboard (Stripe will retry per its schedule);
  silently swallowing it would hide a real misconfiguration. (A valid signature is still required
  first, so this only fires for genuinely unresolvable-but-authentic events.)
- Unhandled event type → **200**, event still recorded for audit, row unchanged.
- The event-record + state-update happen in **one transaction**, so a mid-write failure leaves the
  event *not* recorded; Stripe retries → reprocessed idempotently.

## Testing

- **Pure unit (default `uv run pytest`, no keys, no DB):** `reducer.apply_subscription_event` for
  every handled event type (incl. the `trialing` status on a Pro checkout with a trial, and revert
  on delete); price→tier mapping; the trial-only-Pro rule in `start_upgrade` (Stub provider asserts
  `trial_days=14` for pro, `0`/absent for premium, and `metadata.tenant_id` set).
- **Integration (DB at 55432, StubProvider):** `GET /subscription` shape; `upgrade` returns a URL +
  persists `stripe_customer_id`; a constructed signed webhook (`checkout.session.completed` for
  Pro-with-trial) flips the row, and a subsequent `auth_resolve_principal(...)` returns `pro` (the
  end-to-end tier flip); a duplicate `provider_event_id` is a 200 no-op; `subscription.deleted`
  reverts the tenant to `free`.
- **Migration test:** a `trialing` Pro subscription resolves to tier `pro` (the resolver change).
- **Live test-mode smoke (env-gated by `STRIPE_TEST_SECRET_KEY`):** real Stripe test-mode customer +
  checkout session creation returns a URL; skipped when the key is absent.

## Migration

`infra/migrations/versions/<next>_billing_stripe.py` (the next sequential number after the current
head — confirm during planning, `0011` is the latest known):
1. `ALTER TABLE tenants ADD COLUMN stripe_customer_id TEXT;` + a (unique) index on it for the
   webhook customer→tenant lookup. (On `tenants`, not `subscriptions`: the Stripe customer is a
   per-tenant identity that outlives any single subscription row.)
2. `CREATE OR REPLACE FUNCTION auth_resolve_principal(...)` with `status IN ('active','trialing')`.
3. Drop + recreate `idx_subscriptions_tenant_active` as `WHERE status IN ('active','trialing')`.
Downgrade reverses all three (restore the `= 'active'` function/index, drop the column).
Note: `tenants` is non-RLS-readable by the `auth_*` SECURITY DEFINER functions; the webhook writes
`stripe_customer_id` under a `tenant_session`, and the `saalr_app` role needs UPDATE on the new
column (covered by the existing table grant — verify during planning).

## Out of scope (later)

B2 frontend (pricing page + wiring the 402 upgrade nudges to `/subscription/upgrade` → Checkout, and
a billing-management entry to the portal); Razorpay; dunning automation; annual plans; proration UI;
tax/Stripe Tax.
