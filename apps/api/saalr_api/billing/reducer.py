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
