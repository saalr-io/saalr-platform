# Stripe Billing Backend (B1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a tenant subscribe to Pro/Premium via Stripe so the `subscriptions` row that already drives `auth_resolve_principal` is updated by an idempotent webhook — flipping entitlements with zero gating-code changes.

**Architecture:** A new `apps/api/saalr_api/billing/` module: a `PaymentProvider` seam (`StripeProvider` lazy-wrapping the sync `stripe` SDK via `asyncio.to_thread`, plus a deterministic `StubProvider` for tests); a **pure** reducer mapping Stripe events → subscription-row state; a repo + service; and 4 routes (`GET /subscription`, `POST /subscription/upgrade`, `POST /subscription/portal`, `POST /webhooks/stripe`). A migration adds `tenants.stripe_customer_id`, a `SECURITY DEFINER` `billing_tenant_for_customer()` (the webhook resolves tenant pre-context), and extends `auth_resolve_principal` + the unique index to treat `trialing` like `active`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Postgres (RLS), Redis, the `stripe` Python SDK (optional extra), pytest + httpx ASGI. DB at `localhost:55432` for integration tests (set `ADMIN_/APP_DATABASE_URL`).

**Spec:** `docs/superpowers/specs/2026-06-03-stripe-billing-backend-design.md`

**Decisions:** Stripe-only behind a seam; monthly Pro/Premium; **14-day trial on Pro only**; Billing-Portal handles cancel (no `/cancel` route); `stripe_customer_id` on `tenants`; **400** on unknown-tenant webhook.

---

## File Structure

| File | Responsibility |
|---|---|
| `packages/core/saalr_core/config.py` (modify) | Add 6 Stripe settings |
| `apps/api/pyproject.toml` (modify) | Add `stripe` optional extra |
| `packages/core/saalr_core/db/models/tenancy.py` (modify) | Add `stripe_customer_id` to `Tenant` |
| `infra/migrations/versions/0012_stripe_billing.py` (create) | Column + definer fn + resolver/index trialing |
| `apps/api/saalr_api/billing/__init__.py` (create) | Export `router` |
| `apps/api/saalr_api/billing/provider.py` (create) | `PaymentProvider` protocol + `StripeProvider` + `StubProvider` + `make_payment_provider` |
| `apps/api/saalr_api/billing/reducer.py` (create) | Pure `SubscriptionState` + `apply_subscription_event` |
| `apps/api/saalr_api/billing/repo.py` (create) | Subscription row + customer id + idempotent billing_events |
| `apps/api/saalr_api/billing/service.py` (create) | `get_subscription` / `start_upgrade` / `portal` / `handle_webhook` |
| `apps/api/saalr_api/billing/schemas.py` (create) | `UpgradeRequest` |
| `apps/api/saalr_api/billing/router.py` (create) | The 4 endpoints |
| `apps/api/saalr_api/main.py` (modify) | Wire `app.state.payment_provider` + `include_router` |
| `packages/core/tests/test_billing_reducer.py` (create) | Pure reducer unit tests |
| `tests/integration/test_billing.py` (create) | Repo/service/router integration tests (Stub provider) |
| `tests/integration/test_billing_resolver.py` (create) | Migration: trialing → tier flip |
| `tests/integration/test_billing_stripe_live.py` (create) | Env-gated live test-mode smoke |

**Test invocation:** pure unit — `uv run pytest packages/core/tests/test_billing_reducer.py`. Integration — `uv run pytest tests/integration/test_billing.py` with `ADMIN_DATABASE_URL`/`APP_DATABASE_URL` pointing at port **55432**. Full gate — `uv run pytest`. Lint — `uv run ruff check`.

---

## Task 1: Config + `stripe` extra

**Files:**
- Modify: `packages/core/saalr_core/config.py`
- Modify: `apps/api/pyproject.toml`

- [ ] **Step 1: Add the Stripe settings.** In `packages/core/saalr_core/config.py`, add these fields to the `Settings` class (after the AWS block, before `get_settings`):

```python
    # Stripe billing (B1). Absent secret_key -> billing endpoints return 503.
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_pro: str | None = None
    stripe_price_premium: str | None = None
    billing_success_url: str = "http://localhost:5174/app/billing/success"
    billing_cancel_url: str = "http://localhost:5174/app/billing/cancel"
```

- [ ] **Step 2: Add the `stripe` extra.** In `apps/api/pyproject.toml`, add (after the `[project]` table):

```toml
[project.optional-dependencies]
stripe = ["stripe>=10.0"]
```

- [ ] **Step 3: Verify import + lock.** Run `uv sync` then `uv run python -c "from saalr_core.config import get_settings; print(get_settings().billing_success_url)"`. Expected: prints the default URL. (Do NOT install the `stripe` extra into the default env — it stays optional; the live-smoke task installs it.)

- [ ] **Step 4: Commit.**
```bash
git add packages/core/saalr_core/config.py apps/api/pyproject.toml
git commit -m "feat(billing): config settings + optional stripe extra"
```

---

## Task 2: The pure reducer

The heart of the slice: a pure function mapping a Stripe event onto the subscription row's next state. No Stripe import, no I/O.

**Files:**
- Create: `apps/api/saalr_api/billing/__init__.py` (empty for now)
- Create: `apps/api/saalr_api/billing/reducer.py`
- Test: `packages/core/tests/test_billing_reducer.py`

- [ ] **Step 1: Write the failing tests.** Create `packages/core/tests/test_billing_reducer.py`:

```python
from datetime import datetime, timezone

from saalr_api.billing.reducer import SubscriptionState, apply_subscription_event

PRICE_TO_TIER = {"price_pro": "pro", "price_premium": "premium"}

FREE = SubscriptionState(
    tier="free", status="active", provider="manual",
    provider_subscription_id=None,
    current_period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    current_period_end=datetime(2126, 1, 1, tzinfo=timezone.utc),
    cancel_at_period_end=False,
)


def _ts(y=2026, m=6, d=3):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


def test_checkout_completed_pro_with_trial_is_trialing_pro():
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "customer": "cus_1", "subscription": "sub_1",
            "metadata": {"tenant_id": "t1"},
            "line_items": None,
        }},
    }
    sub = {
        "id": "sub_1", "status": "trialing",
        "items": {"data": [{"price": {"id": "price_pro"}}]},
        "current_period_start": _ts(), "current_period_end": _ts(m=7),
        "cancel_at_period_end": False,
    }
    out = apply_subscription_event(FREE, event, PRICE_TO_TIER, subscription=sub)
    assert out.tier == "pro"
    assert out.status == "trialing"
    assert out.provider == "stripe"
    assert out.provider_subscription_id == "sub_1"


def test_subscription_updated_refreshes_status_and_tier():
    cur = SubscriptionState(**{**FREE.__dict__, "tier": "pro", "status": "trialing",
                               "provider": "stripe", "provider_subscription_id": "sub_1"})
    event = {"type": "customer.subscription.updated", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "active",
        "items": {"data": [{"price": {"id": "price_premium"}}]},
        "current_period_start": _ts(), "current_period_end": _ts(m=7),
        "cancel_at_period_end": True,
    }}}
    out = apply_subscription_event(cur, event, PRICE_TO_TIER)
    assert out.tier == "premium"
    assert out.status == "active"
    assert out.cancel_at_period_end is True


def test_subscription_deleted_reverts_to_free():
    cur = SubscriptionState(**{**FREE.__dict__, "tier": "pro", "status": "active",
                               "provider": "stripe", "provider_subscription_id": "sub_1"})
    event = {"type": "customer.subscription.deleted", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "canceled"}}}
    out = apply_subscription_event(cur, event, PRICE_TO_TIER)
    assert out.tier == "free"
    assert out.status == "active"
    assert out.provider == "manual"
    assert out.provider_subscription_id is None


def test_invoice_payment_failed_is_past_due():
    cur = SubscriptionState(**{**FREE.__dict__, "tier": "pro", "status": "active"})
    event = {"type": "invoice.payment_failed", "data": {"object": {"customer": "cus_1"}}}
    out = apply_subscription_event(cur, event, PRICE_TO_TIER)
    assert out.status == "past_due"
    assert out.tier == "pro"  # tier unchanged; entitlements only key off active/trialing


def test_invoice_paid_is_active():
    cur = SubscriptionState(**{**FREE.__dict__, "tier": "pro", "status": "past_due"})
    event = {"type": "invoice.paid", "data": {"object": {"customer": "cus_1"}}}
    out = apply_subscription_event(cur, event, PRICE_TO_TIER)
    assert out.status == "active"


def test_unknown_event_is_noop():
    event = {"type": "customer.updated", "data": {"object": {"customer": "cus_1"}}}
    out = apply_subscription_event(FREE, event, PRICE_TO_TIER)
    assert out == FREE
```

- [ ] **Step 2: Run to verify failure.** `uv run pytest packages/core/tests/test_billing_reducer.py -q` → FAIL (`ModuleNotFoundError: saalr_api.billing.reducer`).

- [ ] **Step 3: Implement.** Create `apps/api/saalr_api/billing/__init__.py` (empty). Create `apps/api/saalr_api/billing/reducer.py`:

```python
"""Pure mapping of Stripe events -> the tenant's single subscription-row state.

No Stripe import, no I/O. `checkout.session.completed` needs the expanded Stripe
subscription object (the session alone lacks price/period); the caller passes it
as `subscription`. For subscription.* events the object *is* the subscription.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone


@dataclass(frozen=True)
class SubscriptionState:
    tier: str
    status: str
    provider: str
    provider_subscription_id: str | None
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool


def _dt(epoch: int | None) -> datetime | None:
    return datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch else None


def _tier_of(sub: dict, price_to_tier: dict[str, str]) -> str | None:
    items = (sub.get("items") or {}).get("data") or []
    if not items:
        return None
    price_id = (items[0].get("price") or {}).get("id")
    return price_to_tier.get(price_id)


def _from_subscription(current: SubscriptionState, sub: dict,
                       price_to_tier: dict[str, str]) -> SubscriptionState:
    tier = _tier_of(sub, price_to_tier) or current.tier
    return replace(
        current,
        tier=tier,
        status=sub.get("status", current.status),
        provider="stripe",
        provider_subscription_id=sub.get("id", current.provider_subscription_id),
        current_period_start=_dt(sub.get("current_period_start")) or current.current_period_start,
        current_period_end=_dt(sub.get("current_period_end")) or current.current_period_end,
        cancel_at_period_end=bool(sub.get("cancel_at_period_end", current.cancel_at_period_end)),
    )


def apply_subscription_event(
    current: SubscriptionState,
    event: dict,
    price_to_tier: dict[str, str],
    *,
    subscription: dict | None = None,
) -> SubscriptionState:
    etype = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}

    if etype == "checkout.session.completed":
        if subscription is None:
            return current  # caller must supply the expanded subscription
        return _from_subscription(current, subscription, price_to_tier)

    if etype == "customer.subscription.updated":
        return _from_subscription(current, obj, price_to_tier)

    if etype == "customer.subscription.deleted":
        return replace(current, tier="free", status="active", provider="manual",
                       provider_subscription_id=None, cancel_at_period_end=False)

    if etype == "invoice.payment_failed":
        return replace(current, status="past_due")

    if etype == "invoice.paid":
        return replace(current, status="active")

    return current
```

- [ ] **Step 4: Run to verify pass.** `uv run pytest packages/core/tests/test_billing_reducer.py -q` → 6 passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/api/saalr_api/billing/__init__.py apps/api/saalr_api/billing/reducer.py packages/core/tests/test_billing_reducer.py
git commit -m "feat(billing): pure subscription-event reducer + unit tests"
```

---

## Task 3: Migration — `tenants.stripe_customer_id`, definer lookup, trialing resolver

**Files:**
- Modify: `packages/core/saalr_core/db/models/tenancy.py`
- Create: `infra/migrations/versions/0012_stripe_billing.py`
- Test: `tests/integration/test_billing_resolver.py`

- [ ] **Step 1: Confirm the migration head.** Run `uv run alembic heads`. Expected: `0011 (head)` (the head is `0011_research_transcripts.py`). If it prints a different revision, set `down_revision` in Step 3 to that value and rename the file's number to head+1 (and `revision` to match).

- [ ] **Step 2: Add the model field.** In `packages/core/saalr_core/db/models/tenancy.py`, add to the `Tenant` class (after `status`):

```python
    stripe_customer_id: Mapped[str | None] = mapped_column(Text)
```
(`Text` is already imported in that file.)

- [ ] **Step 3: Write the migration.** Create `infra/migrations/versions/0012_stripe_billing.py`:

```python
"""stripe billing: tenants.stripe_customer_id, customer->tenant lookup, trialing entitlements

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-03
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tenants ADD COLUMN stripe_customer_id text;
        CREATE UNIQUE INDEX idx_tenants_stripe_customer
          ON tenants(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

        -- Webhook resolves tenant from a Stripe customer id BEFORE any tenant context
        -- exists. tenants is FORCE RLS, so this must be SECURITY DEFINER (same posture
        -- as auth_resolve_principal). Owner must BYPASSRLS in prod.
        CREATE OR REPLACE FUNCTION billing_tenant_for_customer(p_customer_id text)
        RETURNS uuid LANGUAGE sql SECURITY DEFINER SET search_path = public AS $func$
          SELECT tenant_id FROM tenants WHERE stripe_customer_id = p_customer_id LIMIT 1;
        $func$;
        GRANT EXECUTE ON FUNCTION billing_tenant_for_customer(text) TO saalr_app;

        -- Trials carry status 'trialing'; the resolver must grant their tier.
        CREATE OR REPLACE FUNCTION auth_resolve_principal(p_clerk_user_id text, p_email citext)
        RETURNS TABLE (user_id uuid, tenant_id uuid, tier text)
        LANGUAGE sql SECURITY DEFINER SET search_path = public AS $func$
          SELECT u.user_id, m.tenant_id, COALESCE(s.tier, 'free')
          FROM users u
          JOIN memberships m ON m.user_id = u.user_id
          LEFT JOIN subscriptions s
            ON s.tenant_id = m.tenant_id AND s.status IN ('active', 'trialing')
          WHERE (p_clerk_user_id IS NOT NULL AND u.clerk_user_id = p_clerk_user_id)
             OR (p_clerk_user_id IS NULL AND u.email = p_email)
          ORDER BY m.created_at
          LIMIT 1;
        $func$;

        -- One entitled row per tenant (active OR trialing).
        DROP INDEX IF EXISTS idx_subscriptions_tenant_active;
        CREATE UNIQUE INDEX idx_subscriptions_tenant_active
          ON subscriptions(tenant_id) WHERE status IN ('active', 'trialing');
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_subscriptions_tenant_active;
        CREATE UNIQUE INDEX idx_subscriptions_tenant_active
          ON subscriptions(tenant_id) WHERE status = 'active';

        CREATE OR REPLACE FUNCTION auth_resolve_principal(p_clerk_user_id text, p_email citext)
        RETURNS TABLE (user_id uuid, tenant_id uuid, tier text)
        LANGUAGE sql SECURITY DEFINER SET search_path = public AS $func$
          SELECT u.user_id, m.tenant_id, COALESCE(s.tier, 'free')
          FROM users u
          JOIN memberships m ON m.user_id = u.user_id
          LEFT JOIN subscriptions s ON s.tenant_id = m.tenant_id AND s.status = 'active'
          WHERE (p_clerk_user_id IS NOT NULL AND u.clerk_user_id = p_clerk_user_id)
             OR (p_clerk_user_id IS NULL AND u.email = p_email)
          ORDER BY m.created_at
          LIMIT 1;
        $func$;

        DROP FUNCTION IF EXISTS billing_tenant_for_customer(text);
        DROP INDEX IF EXISTS idx_tenants_stripe_customer;
        ALTER TABLE tenants DROP COLUMN IF EXISTS stripe_customer_id;
    """)
```

- [ ] **Step 4: Write the resolver test.** Create `tests/integration/test_billing_resolver.py`:

```python
from uuid import uuid4

from sqlalchemy import text

from saalr_core.db.session import tenant_session


async def test_trialing_subscription_resolves_to_its_tier(admin_engine, app_sessionmaker):
    tenant_id, user_id = uuid4(), uuid4()
    # Seed a user + tenant + membership + a TRIALING pro subscription (admin bypasses RLS).
    async with admin_engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO users (user_id, email) VALUES (:u, :e)"),
            {"u": user_id, "e": "trial@acme.com"})
        await conn.execute(text(
            "INSERT INTO tenants (tenant_id, display_name, country_code) VALUES (:t,'acme','US')"),
            {"t": tenant_id})
        await conn.execute(text(
            "INSERT INTO memberships (user_id, tenant_id, role) VALUES (:u,:t,'owner')"),
            {"u": user_id, "t": tenant_id})
        await conn.execute(text(
            "INSERT INTO subscriptions (subscription_id, tenant_id, tier, status, provider, "
            "current_period_start, current_period_end) "
            "VALUES (:s,:t,'pro','trialing','stripe', now(), now()+interval '14 days')"),
            {"s": uuid4(), "t": tenant_id})

    async with app_sessionmaker() as s:
        row = (await s.execute(
            text("SELECT tier FROM auth_resolve_principal(NULL, :e)"),
            {"e": "trial@acme.com"})).first()
    assert row is not None and row.tier == "pro"
```

- [ ] **Step 5: Run.** `uv run alembic upgrade head` (DB on 55432) then `uv run pytest tests/integration/test_billing_resolver.py -q` → 1 passed. Then verify downgrade is clean: `uv run alembic downgrade -1 && uv run alembic upgrade head`.

- [ ] **Step 6: Commit.**
```bash
git add packages/core/saalr_core/db/models/tenancy.py infra/migrations/versions/0012_stripe_billing.py tests/integration/test_billing_resolver.py
git commit -m "feat(billing): migration — customer id on tenants, definer lookup, trialing entitlements"
```

---

## Task 4: Repo

**Files:**
- Create: `apps/api/saalr_api/billing/repo.py`
- Test: add to `tests/integration/test_billing.py`

- [ ] **Step 1: Write the failing tests.** Create `tests/integration/test_billing.py` with the repo tests (more added in later tasks):

```python
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import text

from saalr_api.billing import repo
from saalr_api.billing.reducer import SubscriptionState
from saalr_core.db.session import tenant_session


async def _seed_free_tenant(admin_engine, email="b@acme.com"):
    tenant_id, user_id = uuid4(), uuid4()
    async with admin_engine.begin() as conn:
        await conn.execute(text("INSERT INTO users (user_id, email) VALUES (:u,:e)"),
                           {"u": user_id, "e": email})
        await conn.execute(text(
            "INSERT INTO tenants (tenant_id, display_name, country_code) VALUES (:t,'acme','US')"),
            {"t": tenant_id})
        await conn.execute(text(
            "INSERT INTO memberships (user_id, tenant_id, role) VALUES (:u,:t,'owner')"),
            {"u": user_id, "t": tenant_id})
        await conn.execute(text(
            "INSERT INTO subscriptions (subscription_id, tenant_id, tier, status, provider, "
            "current_period_start, current_period_end) "
            "VALUES (:s,:t,'free','active','manual', now(), now()+interval '100 years')"),
            {"s": uuid4(), "t": tenant_id})
    return tenant_id


async def test_get_and_set_customer_id(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine)
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert await repo.get_customer_id(s, tenant_id) is None
        await repo.set_customer_id(s, tenant_id, "cus_X")
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert await repo.get_customer_id(s, tenant_id) == "cus_X"


async def test_upsert_subscription_updates_in_place(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine)
    state = SubscriptionState(
        tier="pro", status="trialing", provider="stripe", provider_subscription_id="sub_1",
        current_period_start=datetime(2026, 6, 3, tzinfo=timezone.utc),
        current_period_end=datetime(2026, 7, 3, tzinfo=timezone.utc),
        cancel_at_period_end=False)
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        await repo.upsert_subscription(s, tenant_id, state)
        row = await repo.get_subscription(s, tenant_id)
        assert row.tier == "pro" and row.status == "trialing"
    # still exactly one row (the unique partial index is not violated)
    async with admin_engine.begin() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM subscriptions WHERE tenant_id=:t"),
                                {"t": tenant_id})).scalar()
    assert n == 1


async def test_record_billing_event_is_idempotent(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine)
    event = {"id": "evt_1", "type": "invoice.paid", "data": {"object": {"amount_paid": 0}}}
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        first = await repo.record_billing_event(s, tenant_id, event)
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        second = await repo.record_billing_event(s, tenant_id, event)
    assert first is True and second is False
```

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/integration/test_billing.py -q` → FAIL (`ModuleNotFoundError: saalr_api.billing.repo`).

- [ ] **Step 3: Implement.** Create `apps/api/saalr_api/billing/repo.py`:

```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.ids import new_id

from .reducer import SubscriptionState


async def get_customer_id(session: AsyncSession, tenant_id: UUID) -> str | None:
    return (await session.execute(
        text("SELECT stripe_customer_id FROM tenants WHERE tenant_id = :t"),
        {"t": str(tenant_id)})).scalar()


async def set_customer_id(session: AsyncSession, tenant_id: UUID, customer_id: str) -> None:
    await session.execute(
        text("UPDATE tenants SET stripe_customer_id = :c WHERE tenant_id = :t"),
        {"c": customer_id, "t": str(tenant_id)})


async def get_subscription(session: AsyncSession, tenant_id: UUID):
    return (await session.execute(
        text("SELECT subscription_id, tier, status, provider, provider_subscription_id, "
             "current_period_start, current_period_end, cancel_at_period_end "
             "FROM subscriptions WHERE tenant_id = :t AND status IN ('active','trialing') "
             "ORDER BY updated_at DESC LIMIT 1"),
        {"t": str(tenant_id)})).first()


async def upsert_subscription(session: AsyncSession, tenant_id: UUID,
                              state: SubscriptionState) -> None:
    """Update the tenant's single entitled subscription row in place."""
    await session.execute(
        text("UPDATE subscriptions SET tier=:tier, status=:status, provider=:provider, "
             "provider_subscription_id=:psid, current_period_start=:cps, "
             "current_period_end=:cpe, cancel_at_period_end=:cape, updated_at=now() "
             "WHERE tenant_id=:t AND status IN ('active','trialing')"),
        {"tier": state.tier, "status": state.status, "provider": state.provider,
         "psid": state.provider_subscription_id, "cps": state.current_period_start,
         "cpe": state.current_period_end, "cape": state.cancel_at_period_end,
         "t": str(tenant_id)})


async def record_billing_event(session: AsyncSession, tenant_id: UUID, event: dict) -> bool:
    """Insert a billing_events row keyed by the provider event id. Returns False if the
    event was already recorded (idempotent no-op)."""
    existing = (await session.execute(
        text("SELECT 1 FROM billing_events WHERE provider_event_id = :pid"),
        {"pid": event.get("id")})).first()
    if existing:
        return False
    import json
    await session.execute(
        text("INSERT INTO billing_events (event_id, tenant_id, event_type, "
             "provider_event_id, raw_event) VALUES (:eid, :t, :etype, :pid, :raw)"),
        {"eid": new_id(), "t": str(tenant_id), "etype": event.get("type", "unknown"),
         "pid": event.get("id"), "raw": json.dumps(event)})
    return True
```

- [ ] **Step 4: Run to verify pass.** `uv run pytest tests/integration/test_billing.py -q` → 3 passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/api/saalr_api/billing/repo.py tests/integration/test_billing.py
git commit -m "feat(billing): repo — subscription row, customer id, idempotent events"
```

---

## Task 5: Provider seam (`StubProvider` + `StripeProvider` + factory)

**Files:**
- Create: `apps/api/saalr_api/billing/provider.py`
- Test: add to `tests/integration/test_billing.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/integration/test_billing.py`:

```python
from saalr_api.billing.provider import StubProvider, make_payment_provider


async def test_stub_provider_checkout_includes_metadata_and_trial():
    p = StubProvider()
    url = await p.create_checkout_session(customer_id="cus_1", price_id="price_pro",
                                          tenant_id="t1", trial_days=14,
                                          success_url="s", cancel_url="c")
    assert url.startswith("https://stub.stripe/checkout/")
    assert p.last_checkout["metadata"]["tenant_id"] == "t1"
    assert p.last_checkout["trial_days"] == 14


def test_stub_verify_webhook_roundtrips_signed_payload():
    p = StubProvider()
    payload, sig = p.sign({"id": "evt_1", "type": "invoice.paid"})
    event = p.verify_webhook(payload=payload, sig_header=sig)
    assert event["id"] == "evt_1"


def test_make_payment_provider_none_without_key():
    class S:  # minimal settings stand-in
        stripe_secret_key = None
    assert make_payment_provider(S()) is None
```

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/integration/test_billing.py -q` → FAIL (`ImportError`).

- [ ] **Step 3: Implement.** Create `apps/api/saalr_api/billing/provider.py`:

```python
"""Payment provider seam. StripeProvider lazy-wraps the sync `stripe` SDK via
asyncio.to_thread (no module-level import, so the default env needs no `stripe`).
StubProvider is a deterministic in-memory double for tests / no-keys."""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Protocol


class PaymentProvider(Protocol):
    async def ensure_customer(self, *, tenant_id: str, email: str, existing_id: str | None) -> str: ...
    async def create_checkout_session(self, *, customer_id: str, price_id: str, tenant_id: str,
                                       trial_days: int, success_url: str, cancel_url: str) -> str: ...
    async def create_portal_session(self, *, customer_id: str, return_url: str) -> str: ...
    async def retrieve_subscription(self, subscription_id: str) -> dict: ...
    def verify_webhook(self, *, payload: bytes, sig_header: str) -> dict: ...


class StubProvider:
    """Synchronous deterministic double. Methods are async to match the protocol."""

    def __init__(self) -> None:
        self.last_checkout: dict | None = None
        self._subs: dict[str, dict] = {}

    async def ensure_customer(self, *, tenant_id, email, existing_id):
        return existing_id or f"cus_{tenant_id}"

    async def create_checkout_session(self, *, customer_id, price_id, tenant_id,
                                      trial_days, success_url, cancel_url):
        self.last_checkout = {"customer": customer_id, "price": price_id,
                              "metadata": {"tenant_id": tenant_id}, "trial_days": trial_days}
        return f"https://stub.stripe/checkout/{tenant_id}"

    async def create_portal_session(self, *, customer_id, return_url):
        return f"https://stub.stripe/portal/{customer_id}"

    async def retrieve_subscription(self, subscription_id):
        return self._subs.get(subscription_id, {"id": subscription_id})

    # test helpers --------------------------------------------------------
    def sign(self, event: dict) -> tuple[bytes, str]:
        payload = json.dumps(event).encode()
        return payload, hashlib.sha256(payload).hexdigest()

    def verify_webhook(self, *, payload: bytes, sig_header: str) -> dict:
        if sig_header != hashlib.sha256(payload).hexdigest():
            raise ValueError("bad signature")
        return json.loads(payload)


class StripeProvider:
    def __init__(self, secret_key: str, webhook_secret: str) -> None:
        self._key = secret_key
        self._webhook_secret = webhook_secret

    def _stripe(self):
        import stripe  # lazy: keeps `stripe` an optional extra
        stripe.api_key = self._key
        return stripe

    async def ensure_customer(self, *, tenant_id, email, existing_id):
        if existing_id:
            return existing_id
        def _create():
            return self._stripe().Customer.create(
                email=email, metadata={"tenant_id": tenant_id}).id
        return await asyncio.to_thread(_create)

    async def create_checkout_session(self, *, customer_id, price_id, tenant_id,
                                      trial_days, success_url, cancel_url):
        def _create():
            sub_data = {"metadata": {"tenant_id": tenant_id}}
            if trial_days:
                sub_data["trial_period_days"] = trial_days
            return self._stripe().checkout.Session.create(
                mode="subscription", customer=customer_id,
                line_items=[{"price": price_id, "quantity": 1}],
                metadata={"tenant_id": tenant_id}, subscription_data=sub_data,
                success_url=success_url, cancel_url=cancel_url).url
        return await asyncio.to_thread(_create)

    async def create_portal_session(self, *, customer_id, return_url):
        def _create():
            return self._stripe().billing_portal.Session.create(
                customer=customer_id, return_url=return_url).url
        return await asyncio.to_thread(_create)

    async def retrieve_subscription(self, subscription_id):
        def _get():
            return dict(self._stripe().Subscription.retrieve(subscription_id))
        return await asyncio.to_thread(_get)

    def verify_webhook(self, *, payload: bytes, sig_header: str) -> dict:
        # construct_event raises stripe.error.SignatureVerificationError on a bad sig.
        return dict(self._stripe().Webhook.construct_event(
            payload, sig_header, self._webhook_secret))


def make_payment_provider(settings) -> PaymentProvider | None:
    if not settings.stripe_secret_key:
        return None
    return StripeProvider(settings.stripe_secret_key, settings.stripe_webhook_secret or "")
```

- [ ] **Step 4: Run to verify pass.** `uv run pytest tests/integration/test_billing.py -q` → 6 passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/api/saalr_api/billing/provider.py tests/integration/test_billing.py
git commit -m "feat(billing): payment provider seam (Stripe + Stub) + factory"
```

---

## Task 6: Service — upgrade / portal / webhook

**Files:**
- Create: `apps/api/saalr_api/billing/service.py`
- Test: add to `tests/integration/test_billing.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/integration/test_billing.py`:

```python
from saalr_api.billing import service


def _price_map():
    return {"price_pro": "pro", "price_premium": "premium"}


class _Settings:
    stripe_price_pro = "price_pro"
    stripe_price_premium = "price_premium"
    billing_success_url = "http://x/success"
    billing_cancel_url = "http://x/cancel"


async def test_start_upgrade_pro_sets_trial_and_persists_customer(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine, "up@acme.com")
    provider = StubProvider()
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        out = await service.start_upgrade(s, provider, _Settings(), tenant_id, "up@acme.com", "pro")
    assert out["checkout_url"].startswith("https://stub.stripe/checkout/")
    assert provider.last_checkout["trial_days"] == 14            # trial on Pro
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        assert await repo.get_customer_id(s, tenant_id) == f"cus_{tenant_id}"


async def test_start_upgrade_premium_has_no_trial(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine, "pm@acme.com")
    provider = StubProvider()
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        await service.start_upgrade(s, provider, _Settings(), tenant_id, "pm@acme.com", "premium")
    assert provider.last_checkout["trial_days"] == 0


async def test_handle_webhook_flips_tier_and_is_idempotent(admin_engine, app_sessionmaker):
    tenant_id = await _seed_free_tenant(admin_engine, "wh@acme.com")
    provider = StubProvider()
    # link the customer so billing_tenant_for_customer resolves it
    async with tenant_session(app_sessionmaker, tenant_id) as s:
        await repo.set_customer_id(s, tenant_id, "cus_wh")
    provider._subs["sub_1"] = {
        "id": "sub_1", "status": "trialing",
        "items": {"data": [{"price": {"id": "price_pro"}}]},
        "current_period_start": 1, "current_period_end": 2, "cancel_at_period_end": False}
    event = {"id": "evt_42", "type": "checkout.session.completed",
             "data": {"object": {"customer": "cus_wh", "subscription": "sub_1",
                                 "metadata": {"tenant_id": str(tenant_id)}}}}
    payload, sig = provider.sign(event)

    res1 = await service.handle_webhook(app_sessionmaker, provider, _price_map(), payload, sig)
    res2 = await service.handle_webhook(app_sessionmaker, provider, _price_map(), payload, sig)
    assert res1["received"] and res2["received"]
    async with app_sessionmaker() as s:
        tier = (await s.execute(text("SELECT tier FROM auth_resolve_principal(NULL, :e)"),
                                {"e": "wh@acme.com"})).first().tier
    assert tier == "pro"


async def test_handle_webhook_unknown_tenant_raises(app_sessionmaker):
    provider = StubProvider()
    event = {"id": "evt_x", "type": "invoice.paid", "data": {"object": {"customer": "cus_none"}}}
    payload, sig = provider.sign(event)
    try:
        await service.handle_webhook(app_sessionmaker, provider, _price_map(), payload, sig)
        assert False, "expected UnknownTenant"
    except service.UnknownTenantError:
        pass
```

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/integration/test_billing.py -q` → FAIL.

- [ ] **Step 3: Implement.** Create `apps/api/saalr_api/billing/service.py`:

```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from saalr_core.db.session import tenant_session
from saalr_core.tiers import entitlements_for

from . import repo
from .provider import PaymentProvider
from .reducer import SubscriptionState, apply_subscription_event


class UnknownTenantError(Exception):
    """A signature-valid webhook whose customer maps to no tenant."""


def _price_map(settings) -> dict[str, str]:
    out = {}
    if settings.stripe_price_pro:
        out[settings.stripe_price_pro] = "pro"
    if settings.stripe_price_premium:
        out[settings.stripe_price_premium] = "premium"
    return out


async def get_subscription(session: AsyncSession, tenant_id: UUID) -> dict:
    row = await repo.get_subscription(session, tenant_id)
    tier = row.tier if row else "free"
    return {
        "tier": tier,
        "status": row.status if row else "active",
        "current_period_end": row.current_period_end.isoformat() if row else None,
        "cancel_at_period_end": bool(row.cancel_at_period_end) if row else False,
        "entitlements": entitlements_for(tier),
    }


async def start_upgrade(session: AsyncSession, provider: PaymentProvider, settings,
                        tenant_id: UUID, email: str, tier: str) -> dict:
    price_id = settings.stripe_price_pro if tier == "pro" else settings.stripe_price_premium
    existing = await repo.get_customer_id(session, tenant_id)
    customer_id = await provider.ensure_customer(
        tenant_id=str(tenant_id), email=email, existing_id=existing)
    if customer_id != existing:
        await repo.set_customer_id(session, tenant_id, customer_id)
    url = await provider.create_checkout_session(
        customer_id=customer_id, price_id=price_id, tenant_id=str(tenant_id),
        trial_days=14 if tier == "pro" else 0,
        success_url=settings.billing_success_url, cancel_url=settings.billing_cancel_url)
    return {"checkout_url": url}


async def open_portal(session: AsyncSession, provider: PaymentProvider, settings,
                      tenant_id: UUID) -> dict:
    customer_id = await repo.get_customer_id(session, tenant_id)
    if not customer_id:
        # nothing to manage yet; surfaced as 409 by the router
        raise UnknownTenantError("no stripe customer for tenant")
    url = await provider.create_portal_session(
        customer_id=customer_id, return_url=settings.billing_success_url)
    return {"portal_url": url}


async def _resolve_tenant(session: AsyncSession, obj: dict) -> UUID | None:
    meta_tid = (obj.get("metadata") or {}).get("tenant_id")
    if meta_tid:
        return UUID(meta_tid)
    customer = obj.get("customer")
    if not customer:
        return None
    tid = (await session.execute(
        text("SELECT billing_tenant_for_customer(:c)"), {"c": customer})).scalar()
    return tid


async def handle_webhook(sm: async_sessionmaker[AsyncSession], provider: PaymentProvider,
                         price_to_tier: dict[str, str], payload: bytes, sig_header: str) -> dict:
    event = provider.verify_webhook(payload=payload, sig_header=sig_header)  # raises on bad sig
    obj = (event.get("data") or {}).get("object") or {}

    # Resolve the tenant pre-context: metadata, else a definer customer->tenant lookup.
    async with sm() as lookup:
        async with lookup.begin():
            tenant_id = await _resolve_tenant(lookup, obj)
    if tenant_id is None:
        raise UnknownTenantError(f"no tenant for event {event.get('id')}")

    # checkout.session.completed needs the expanded subscription (the session lacks price/period).
    subscription = None
    if event.get("type") == "checkout.session.completed" and obj.get("subscription"):
        subscription = await provider.retrieve_subscription(obj["subscription"])

    async with tenant_session(sm, tenant_id) as session:
        recorded = await repo.record_billing_event(session, tenant_id, event)
        if not recorded:
            return {"received": True}  # idempotent duplicate
        current = await repo.get_subscription(session, tenant_id)
        cur_state = SubscriptionState(
            tier=current.tier, status=current.status, provider=current.provider,
            provider_subscription_id=current.provider_subscription_id,
            current_period_start=current.current_period_start,
            current_period_end=current.current_period_end,
            cancel_at_period_end=current.cancel_at_period_end)
        new_state = apply_subscription_event(cur_state, event, price_to_tier,
                                             subscription=subscription)
        if new_state != cur_state:
            await repo.upsert_subscription(session, tenant_id, new_state)
    return {"received": True}
```

- [ ] **Step 4: Run to verify pass.** `uv run pytest tests/integration/test_billing.py -q` → all passed.

- [ ] **Step 5: Commit.**
```bash
git add apps/api/saalr_api/billing/service.py tests/integration/test_billing.py
git commit -m "feat(billing): service — upgrade, portal, idempotent webhook handler"
```

---

## Task 7: Schemas + router + app wiring

**Files:**
- Create: `apps/api/saalr_api/billing/schemas.py`
- Create: `apps/api/saalr_api/billing/router.py`
- Modify: `apps/api/saalr_api/billing/__init__.py`
- Modify: `apps/api/saalr_api/main.py`
- Test: add to `tests/integration/test_billing.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/integration/test_billing.py` (these hit the app through HTTP; they configure a Stub provider on `app.state`):

```python
from saalr_api.main import create_app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _auth(email):
    return {"Authorization": f"Bearer dev:{email}"}


async def test_get_subscription_defaults_to_free():
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.payment_provider = StubProvider()
        async with _client(app) as c:
            await c.post("/auth/dev/login", json={"email": "free@acme.com"})
            r = await c.get("/subscription", headers=_auth("free@acme.com"))
    assert r.status_code == 200
    assert r.json()["tier"] == "free"
    assert r.json()["entitlements"]["live_chains"] is False


async def test_upgrade_returns_checkout_url():
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.payment_provider = StubProvider()
        async with _client(app) as c:
            await c.post("/auth/dev/login", json={"email": "u2@acme.com"})
            r = await c.post("/subscription/upgrade", json={"tier": "pro"},
                             headers=_auth("u2@acme.com"))
    assert r.status_code == 200
    assert r.json()["checkout_url"].startswith("https://stub.stripe/checkout/")


async def test_upgrade_503_when_billing_unconfigured():
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.payment_provider = None  # not configured
        async with _client(app) as c:
            await c.post("/auth/dev/login", json={"email": "u3@acme.com"})
            r = await c.post("/subscription/upgrade", json={"tier": "pro"},
                             headers=_auth("u3@acme.com"))
    assert r.status_code == 503
    assert r.json()["detail"]["error"]["code"] == "FEATURE_UNAVAILABLE"


async def test_webhook_bad_signature_is_400():
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.payment_provider = StubProvider()
        async with _client(app) as c:
            r = await c.post("/webhooks/stripe", content=b'{"id":"e"}',
                             headers={"Stripe-Signature": "wrong"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/integration/test_billing.py -q` → FAIL.

- [ ] **Step 3: Implement schemas.** Create `apps/api/saalr_api/billing/schemas.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class UpgradeRequest(BaseModel):
    tier: Literal["pro", "premium"]
```

- [ ] **Step 4: Implement the router.** Create `apps/api/saalr_api/billing/router.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from ..auth.dependency import get_principal
from . import service
from .schemas import UpgradeRequest

router = APIRouter(tags=["billing"])


def _provider_or_503(request: Request):
    provider = getattr(request.app.state, "payment_provider", None)
    if provider is None:
        raise HTTPException(503, {"error": {"code": "FEATURE_UNAVAILABLE",
                                            "message": "billing is not configured"}})
    return provider


@router.get("/subscription")
async def get_subscription(ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    return await service.get_subscription(session, principal.tenant_id)


@router.post("/subscription/upgrade")
async def upgrade(body: UpgradeRequest, request: Request,
                  idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                  ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    provider = _provider_or_503(request)
    redis = request.app.state.redis
    settings = request.app.state.settings
    ikey = f"saalr:idem:billing:{principal.tenant_id}:{idempotency_key}" if idempotency_key else None
    if ikey:
        cached = await redis.get(ikey)
        if cached:
            return {"checkout_url": cached}
    try:
        out = await service.start_upgrade(session, provider, settings,
                                          principal.tenant_id, principal.email, body.tier)
    except Exception as exc:  # noqa: BLE001 - Stripe/API failure -> 502, never 500
        raise HTTPException(502, {"error": {"code": "BILLING_UNAVAILABLE",
                                            "message": "billing provider error"}}) from exc
    if ikey:
        await redis.set(ikey, out["checkout_url"], nx=True, ex=86400)
    return out


@router.post("/subscription/portal")
async def portal(request: Request,
                 ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    provider = _provider_or_503(request)
    settings = request.app.state.settings
    try:
        return await service.open_portal(session, provider, settings, principal.tenant_id)
    except service.UnknownTenantError as exc:
        raise HTTPException(409, {"error": {"code": "BILLING_NO_CUSTOMER",
                                            "message": "no billing account yet"}}) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, {"error": {"code": "BILLING_UNAVAILABLE",
                                            "message": "billing provider error"}}) from exc


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request,
                         stripe_signature: str | None = Header(default=None, alias="Stripe-Signature")) -> dict:
    provider = _provider_or_503(request)
    settings = request.app.state.settings
    sm = request.app.state.sessionmaker
    payload = await request.body()  # raw body is required for signature verification
    price_to_tier = service._price_map(settings)
    try:
        return await service.handle_webhook(sm, provider, price_to_tier, payload,
                                            stripe_signature or "")
    except service.UnknownTenantError as exc:
        raise HTTPException(400, {"error": {"code": "BILLING_UNKNOWN_TENANT",
                                            "message": "no tenant for this event"}}) from exc
    except Exception as exc:  # noqa: BLE001 - bad signature / malformed -> 400
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "invalid webhook"}}) from exc
```

- [ ] **Step 5: Export the router + wire the app.** In `apps/api/saalr_api/billing/__init__.py`:
```python
from .router import router  # noqa: F401
```
In `apps/api/saalr_api/main.py`: import at top — `from saalr_api.billing import router as billing_router` and `from saalr_api.billing.provider import make_payment_provider`. Inside the lifespan (before `yield`) add:
```python
        app.state.settings = settings
        app.state.payment_provider = make_payment_provider(settings)
```
After the other `include_router` calls add:
```python
    app.include_router(billing_router)
```
(If `app.state.settings` is already set elsewhere, reuse it — grep first; `settings` is already in scope inside `create_app`.)

- [ ] **Step 6: Run to verify pass.** `uv run pytest tests/integration/test_billing.py -q` → all passed. Then `uv run ruff check apps/api/saalr_api/billing` → clean. Then the regression gate: `uv run pytest tests/integration/test_auth.py -q` (the resolver change must not break existing auth) → passed.

- [ ] **Step 7: Commit.**
```bash
git add apps/api/saalr_api/billing/schemas.py apps/api/saalr_api/billing/router.py apps/api/saalr_api/billing/__init__.py apps/api/saalr_api/main.py tests/integration/test_billing.py
git commit -m "feat(billing): schemas + router + app wiring (4 endpoints)"
```

---

## Task 8: Live Stripe test-mode smoke (env-gated)

**Files:**
- Create: `tests/integration/test_billing_stripe_live.py`

- [ ] **Step 1: Write the env-gated test.** Create `tests/integration/test_billing_stripe_live.py`:

```python
import os

import pytest

from saalr_api.billing.provider import StripeProvider

LIVE = os.environ.get("STRIPE_TEST_SECRET_KEY")

pytestmark = pytest.mark.skipif(not LIVE, reason="set STRIPE_TEST_SECRET_KEY to run the live smoke")


async def test_create_customer_and_checkout_session_test_mode():
    provider = StripeProvider(LIVE, os.environ.get("STRIPE_TEST_WEBHOOK_SECRET", ""))
    customer = await provider.ensure_customer(
        tenant_id="00000000-0000-0000-0000-000000000000", email="smoke@example.com",
        existing_id=None)
    assert customer.startswith("cus_")
    url = await provider.create_checkout_session(
        customer_id=customer, price_id=os.environ["STRIPE_TEST_PRICE_PRO"],
        tenant_id="00000000-0000-0000-0000-000000000000", trial_days=14,
        success_url="https://example.com/s", cancel_url="https://example.com/c")
    assert url.startswith("https://")
```

- [ ] **Step 2: Run (only if you have a test key).** `STRIPE_TEST_SECRET_KEY=sk_test_... STRIPE_TEST_PRICE_PRO=price_... uv run --extra stripe pytest tests/integration/test_billing_stripe_live.py -q`. Without the key: `uv run pytest tests/integration/test_billing_stripe_live.py -q` → 1 skipped.

- [ ] **Step 3: Commit.**
```bash
git add tests/integration/test_billing_stripe_live.py
git commit -m "test(billing): env-gated live Stripe test-mode smoke"
```

---

## Task 9: Final gate + runbook

- [ ] **Step 1: Full gate.** Run `uv run pytest packages/core/tests/test_billing_reducer.py` (pure) and `uv run pytest tests/integration/test_billing.py tests/integration/test_billing_resolver.py tests/integration/test_auth.py` (DB on 55432). All green. `uv run ruff check` clean.

- [ ] **Step 2: Runbook.** Create `docs/runbooks/billing.md` documenting: the 6 `.env` vars; how to create the Pro/Premium monthly prices in the Stripe dashboard (and that Pro's trial is set per-checkout, not on the price); how to run the webhook locally (`stripe listen --forward-to localhost:8000/webhooks/stripe` → copies the signing secret into `STRIPE_WEBHOOK_SECRET`); the `SECURITY DEFINER` ownership requirement (`auth_resolve_principal` + `billing_tenant_for_customer` must be owned by a BYPASSRLS role in prod); and that B2 (frontend) wires the 402 nudges to `POST /subscription/upgrade`.

- [ ] **Step 3: Commit.**
```bash
git add docs/runbooks/billing.md
git commit -m "docs(billing): runbook — env, prices, webhook forwarding, definer ownership"
```

---

## Notes for the executor

- **DB port:** integration tests need Postgres on **55432** with `ADMIN_DATABASE_URL`/`APP_DATABASE_URL` env set (see the slice-1 memory / `tests/integration/conftest.py`).
- **Stripe object shapes:** `current_period_*` are Unix epoch ints; `items.data[0].price.id` is the price; `checkout.session.completed`'s object has `customer` + `subscription` (id) + `metadata`, NOT the price — hence `retrieve_subscription`.
- **Single entitled row invariant:** the unique partial index now covers `active`+`trialing`. `upsert_subscription` only ever UPDATEs the existing row; never INSERT a second entitled row.
- **No gating-code changes:** entitlement gates already read `principal.tier`; once the row flips, the next request resolves the new tier. Nothing else to touch.
```
