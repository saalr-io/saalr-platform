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
                                          principal.tenant_id, principal.email,
                                          body.tier, body.interval)
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
    # Only bad-webhook / unknown-tenant are client 400s. Infra errors (DB down, bugs)
    # propagate as 5xx so Stripe retries and the idempotency gate replays cleanly —
    # collapsing them into a 400 would make Stripe drop the event permanently.
    try:
        return await service.handle_webhook(sm, provider, price_to_tier, payload,
                                            stripe_signature or "")
    except service.UnknownTenantError as exc:
        raise HTTPException(400, {"error": {"code": "BILLING_UNKNOWN_TENANT",
                                            "message": "no tenant for this event"}}) from exc
    except service.WebhookVerificationError as exc:
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "invalid webhook"}}) from exc
