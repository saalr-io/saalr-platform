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


class WebhookVerificationError(Exception):
    """The webhook signature/payload could not be verified or parsed."""


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
        "has_customer": await repo.get_customer_id(session, tenant_id) is not None,
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
        customer_id=customer_id, return_url=settings.billing_portal_return_url)
    return {"portal_url": url}


async def _resolve_tenant(session: AsyncSession, obj: dict) -> UUID | None:
    meta_tid = (obj.get("metadata") or {}).get("tenant_id")
    if meta_tid:
        try:
            return UUID(meta_tid)
        except ValueError:
            pass  # malformed metadata -> fall back to the authoritative customer lookup
    customer = obj.get("customer")
    if not customer:
        return None
    tid = (await session.execute(
        text("SELECT billing_tenant_for_customer(:c)"), {"c": customer})).scalar()
    return tid


async def handle_webhook(sm: async_sessionmaker[AsyncSession], provider: PaymentProvider,
                         price_to_tier: dict[str, str], payload: bytes, sig_header: str) -> dict:
    # Verification/parse failures are client errors (400). Anything raised AFTER this
    # (DB/infra) must propagate as 5xx so Stripe retries — and the idempotency gate makes
    # the retry safe. Don't collapse infra faults into a 400 (Stripe would not retry).
    try:
        event = provider.verify_webhook(payload=payload, sig_header=sig_header)
    except Exception as exc:  # noqa: BLE001 - any verify/parse failure is a bad webhook
        raise WebhookVerificationError(str(exc)) from exc
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
        if current is None:
            # Invariant: auth_bootstrap seeds one entitled row per tenant. If it's somehow
            # absent we can't apply state; the event is already recorded for audit.
            return {"received": True}
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
