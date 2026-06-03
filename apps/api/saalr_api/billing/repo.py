from __future__ import annotations

import json
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
             "FROM subscriptions WHERE tenant_id = :t AND status IN ('active','trialing','past_due') "
             "ORDER BY updated_at DESC LIMIT 1"),
        {"t": str(tenant_id)})).first()


async def upsert_subscription(session: AsyncSession, tenant_id: UUID,
                              state: SubscriptionState) -> None:
    """Update the tenant's single entitled subscription row in place."""
    await session.execute(
        text("UPDATE subscriptions SET tier=:tier, status=:status, provider=:provider, "
             "provider_subscription_id=:psid, current_period_start=:cps, "
             "current_period_end=:cpe, cancel_at_period_end=:cape, updated_at=now() "
             "WHERE tenant_id=:t AND status IN ('active','trialing','past_due')"),
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
    await session.execute(
        text("INSERT INTO billing_events (event_id, tenant_id, event_type, "
             "provider_event_id, raw_event) VALUES (:eid, :t, :etype, :pid, :raw)"),
        {"eid": new_id(), "t": str(tenant_id), "etype": event.get("type", "unknown"),
         "pid": event.get("id"), "raw": json.dumps(event, default=str)})
    return True
