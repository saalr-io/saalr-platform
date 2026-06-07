from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.ids import new_id

from ..auth import Principal, get_principal
from . import repo, service
from .schemas import BrokerAccountCreate, OrderCreate, StrategyOrderCreate

router = APIRouter(tags=["oms"])


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or str(new_id())


def _adapter_factories(request: Request):
    """Merge the per-broker registry with the legacy alpaca factory (back-compat)."""
    s = request.app.state
    reg = dict(getattr(s, "adapter_factories", {}) or {})
    legacy = getattr(s, "alpaca_adapter_factory", None)
    if legacy is not None:
        reg["alpaca"] = legacy  # an explicitly-set legacy factory wins (tests stub it post-lifespan)
    return reg or None


def _acct_out(a) -> dict:
    return {"broker_account_id": str(a.broker_account_id), "broker": a.broker,
            "account_label": a.account_label, "is_paper": a.is_paper, "status": a.status}


def _pos_out(p) -> dict:
    return {"broker_account_id": str(p.broker_account_id), "symbol": p.symbol,
            "option_type": p.option_type, "strike": str(p.strike) if p.strike is not None else None,
            "expiry": p.expiry.isoformat() if p.expiry else None, "qty": p.qty,
            "avg_entry_price": str(p.avg_entry_price)}


def _order_out(o) -> dict:
    return {"order_id": str(o.order_id), "symbol": o.symbol, "side": o.side, "qty": o.qty,
            "order_type": o.order_type, "status": o.status, "broker_order_id": o.broker_order_id,
            "reject_reason_code": o.reject_reason_code, "created_at": o.created_at.isoformat()}


@router.post("/v1/broker-accounts")
async def create_account(body: BrokerAccountCreate,
                         ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    if body.broker not in ("paper", "alpaca", "tradier"):
        raise HTTPException(400, {"error": {"code": "BROKER_NOT_SUPPORTED",
                                            "message": "broker not supported"}})
    if body.broker == "alpaca":
        if not body.credential_ref:
            raise HTTPException(422, {"error": {"code": "VALIDATION_MISSING_CREDENTIAL_REF",
                                                "message": "credential_ref is required for alpaca"}})
        a = await repo.create_broker_account(session, principal.tenant_id, principal.user_id,
                                             "alpaca", body.account_label, body.is_paper,
                                             body.credential_ref)
    elif body.broker == "tradier":
        a = await repo.create_broker_account(session, principal.tenant_id, principal.user_id,
                                             "tradier", body.account_label, True, "env:TRADIER_SANDBOX")
    else:
        a = await repo.create_broker_account(session, principal.tenant_id, principal.user_id,
                                             "paper", body.account_label, True)
    return _acct_out(a)


@router.get("/v1/broker-accounts")
async def list_accounts(ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    return {"broker_accounts": [_acct_out(a) for a in await repo.list_broker_accounts(session)]}


@router.post("/v1/orders")
async def place(body: OrderCreate, request: Request,
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    factories = _adapter_factories(request)
    return await service.place_order(session, principal, body, idempotency_key,
                                     _request_id(request), factories)


@router.post("/v1/orders/strategy")
async def place_strategy(body: StrategyOrderCreate, request: Request,
                         idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                         ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    factories = _adapter_factories(request)
    idem = idempotency_key or str(new_id())
    return await service.place_strategy(session, principal, body, idem, _request_id(request), factories)


@router.get("/v1/orders")
async def list_orders(limit: int = Query(20, le=100), cursor: str | None = None,
                      ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    decoded = None
    if cursor:
        try:
            ts, oid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            decoded = (datetime.fromisoformat(ts), UUID(oid))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": "bad cursor"}}) from exc
    rows = await repo.list_orders(session, limit, decoded)
    nxt = None
    if len(rows) == limit:
        last = rows[-1]
        nxt = base64.urlsafe_b64encode(f"{last.created_at.isoformat()}|{last.order_id}".encode()).decode()
    return {"orders": [_order_out(r) for r in rows], "next_cursor": nxt}


@router.get("/v1/orders/{order_id}")
async def get_one(order_id: UUID, ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    o = await repo.get_order(session, order_id)
    if o is None:
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "order not found"}})
    return _order_out(o)


@router.post("/v1/orders/{order_id}/cancel")
async def cancel(order_id: UUID, request: Request,
                 ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    factories = _adapter_factories(request)
    return await service.cancel_order(session, principal, str(order_id), _request_id(request), factories)


@router.get("/v1/positions")
async def list_positions(broker_account_id: UUID | None = Query(None),
                         ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    return {"positions": [_pos_out(p) for p in await repo.list_positions(session, broker_account_id)]}
