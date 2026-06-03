# Billing (Stripe) — runbook

Slice **B1** (backend). A tenant subscribes via Stripe Checkout; an idempotent webhook updates
the tenant's single `subscriptions` row, which `auth_resolve_principal` reads as the tier — so
entitlement gates flip with no gating-code changes. US/Stripe only. Monthly Pro & Premium;
**14-day trial on Pro only**. Cancel/card/plan-change is handled by the Stripe **Billing Portal**.

Spec: `docs/superpowers/specs/2026-06-03-stripe-billing-backend-design.md`.
Frontend (B2 — wires the 402 upgrade nudges to `POST /subscription/upgrade`) is a later slice.

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/subscription` | bearer | `{tier, status, current_period_end, cancel_at_period_end, entitlements}` |
| POST | `/subscription/upgrade` | bearer | body `{tier:'pro'\|'premium'}` → `{checkout_url}`; honours `Idempotency-Key` |
| POST | `/subscription/portal` | bearer | `{portal_url}` (manage card / cancel / switch plan) |
| POST | `/webhooks/stripe` | signature | raw-body + `Stripe-Signature`; idempotent; 400 on bad sig / unknown tenant |

Errors: missing billing config → **503 FEATURE_UNAVAILABLE**; Stripe API error → **502
BILLING_UNAVAILABLE**; bad signature / malformed → **400**; signature-valid but no matching tenant
→ **400 BILLING_UNKNOWN_TENANT** (surfaces as a failed delivery in the Stripe dashboard).

## Configuration (`.env`, gitignored)

```
STRIPE_SECRET_KEY=sk_test_...          # absent -> all billing endpoints return 503
STRIPE_WEBHOOK_SECRET=whsec_...        # from `stripe listen` (dev) or the dashboard endpoint (prod)
STRIPE_PRICE_PRO=price_...             # the Pro monthly price id (Stripe dashboard)
STRIPE_PRICE_PREMIUM=price_...         # the Premium monthly price id
BILLING_SUCCESS_URL=http://localhost:5174/app/billing/success   # checkout success redirect
BILLING_CANCEL_URL=http://localhost:5174/app/billing/cancel     # checkout cancel redirect
BILLING_PORTAL_RETURN_URL=http://localhost:5174/app/billing     # return-from-portal page
```

`stripe` is an **optional extra** (`saalr-api[stripe]`); the default env/test gate stays keyless.
Install it only where billing actually runs / for the live smoke: `uv run --extra stripe ...`.

## Create the products/prices (Stripe dashboard, test mode first)

1. Products → add **Saalr Pro** and **Saalr Premium**, each a **recurring / monthly** price.
2. Copy each price id (`price_...`) into `STRIPE_PRICE_PRO` / `STRIPE_PRICE_PREMIUM`.
3. The **trial is NOT set on the price** — it's applied per Checkout Session (`trial_period_days=14`)
   and only for Pro (`start_upgrade` passes `trial_days=14` when `tier=='pro'`, else `0`).

## Webhooks locally

```
stripe login
stripe listen --forward-to localhost:8000/webhooks/stripe
# copy the printed "whsec_..." into STRIPE_WEBHOOK_SECRET, restart the API
stripe trigger checkout.session.completed   # or drive a real test-mode checkout
```

Configure the production webhook endpoint in the dashboard (Developers → Webhooks) for the events:
`checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`,
`invoice.paid`, `invoice.payment_failed`. Idempotency is keyed on the Stripe `event.id`
(`billing_events.provider_event_id`), so redelivery is safe.

## ⚠ Production: SECURITY DEFINER ownership (must-do)

Two SQL functions are `SECURITY DEFINER` and read `tenants`/`memberships`, which are **FORCE RLS**:
- `auth_resolve_principal(text, citext)` — resolves a principal's tier (existing).
- `billing_tenant_for_customer(text)` — the webhook's customer→tenant lookup (new in `0012`).

Their owner **must be a role that BYPASSRLS** (a superuser in local dev; a dedicated BYPASSRLS role
in prod). `CREATE OR REPLACE FUNCTION` preserves the existing owner, but the brand-new
`billing_tenant_for_customer` is owned by whoever ran the migration. If migrations run as a
non-BYPASSRLS role, the lookup silently returns nothing → every customer-keyed webhook
(`invoice.*`, `subscription.*` lacking metadata) becomes a `400 BILLING_UNKNOWN_TENANT`.

After deploy, pin ownership explicitly:
```sql
ALTER FUNCTION auth_resolve_principal(text, citext)  OWNER TO <bypassrls_role>;
ALTER FUNCTION billing_tenant_for_customer(text)     OWNER TO <bypassrls_role>;
```

## Stripe object-shape note (API version)

The reducer reads the subscription period from `current_period_start/end`, falling back to
`items.data[0].current_period_*` (newer Stripe API versions moved these onto the line item). If you
pin a specific Stripe API version on the account, confirm the period fields are populated by running
the live smoke against test mode and checking `GET /subscription` reports a sane `current_period_end`.

## Data model

- One **entitled** `subscriptions` row per tenant (status `active`/`trialing`/`past_due`); the unique
  partial index keeps it to one. `auth_bootstrap` seeds it as free/active/manual on signup.
- `tenants.stripe_customer_id` — the per-tenant Stripe customer (set lazily at first upgrade).
- `billing_events` — every received event (audit + idempotency via `provider_event_id`). B1 records
  the raw event; `subscription_id`/`amount`/`currency` columns are intentionally left for later.

## Tests

- Pure unit (no keys/DB): `uv run pytest packages/core/tests/test_billing_reducer.py`.
- Integration (DB on 55432 + Redis 6379):
  `ADMIN_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:55432/saalr \
   APP_DATABASE_URL=postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr \
   uv run pytest tests/integration/test_billing.py tests/integration/test_billing_resolver.py`.
- Live test-mode smoke (env-gated): set `STRIPE_TEST_SECRET_KEY` + `STRIPE_TEST_PRICE_PRO`, then
  `uv run --extra stripe pytest tests/integration/test_billing_stripe_live.py`. Skipped otherwise.
