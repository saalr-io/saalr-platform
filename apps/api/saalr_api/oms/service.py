from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_brokers.paper import PaperBrokerAdapter
from saalr_brokers.types import BrokerOrder
from saalr_core.config import get_settings
from saalr_core.oms.fsm import OrderStatus, transition
from saalr_core.oms.positions import net_position
from saalr_core.oms.risk import estimate_cost, run_gates
from saalr_core.oms.types import OrderRequest, RiskContext

from ..strategies import repo as strat_repo
from . import repo
from .marks import NoMarketData, model_mark
from .schemas import OrderCreate

_MULT = 100


def _err(code: str, msg: str, status: int = 422, details: dict | None = None) -> HTTPException:
    body = {"error": {"code": code, "message": msg}}
    if details:
        body["error"]["details"] = details
    return HTTPException(status, body)


def _to_request(body: OrderCreate) -> OrderRequest:
    return OrderRequest(
        side=body.side, qty=body.qty, order_type=body.order_type, symbol=body.symbol.upper(),
        limit_price=body.limit_price, stop_price=body.stop_price, time_in_force=body.time_in_force,
        option_type=body.option_type, strike=body.strike, expiry=body.expiry,
    )


def _to_broker_order(body: OrderCreate) -> BrokerOrder:
    return BrokerOrder(
        symbol=body.symbol.upper(), side=body.side, qty=body.qty, order_type=body.order_type,
        limit_price=body.limit_price, stop_price=body.stop_price, time_in_force=body.time_in_force,
        option_type=body.option_type, strike=body.strike, expiry=body.expiry,
    )


def _out(order) -> dict:
    return {
        "order_id": str(order.order_id), "broker_order_id": order.broker_order_id,
        "status": order.status,
        "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
    }


async def place_order(session: AsyncSession, principal, body: OrderCreate, idempotency_key, request_id) -> dict:
    tenant_id, user_id = principal.tenant_id, principal.user_id
    settings = get_settings()

    existing = await repo.find_order_by_idempotency(session, tenant_id, idempotency_key)
    if existing is not None:
        return _out(existing)

    account = await repo.get_broker_account(session, UUID(body.broker_account_id))
    if account is None:
        raise _err("RESOURCE_NOT_FOUND", "broker account not found", 404)
    if account.status != "active":
        raise _err("BROKER_ACCOUNT_INACTIVE", "broker account is not active", 409)

    today = datetime.now(timezone.utc).date()
    try:
        mark = await model_mark(session, symbol=body.symbol.upper(), market="US",
                                option_type=body.option_type, strike=body.strike,
                                expiry=body.expiry, today=today)
    except NoMarketData as exc:
        order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                        status="rejected", reject_reason_code="RISK_NO_MARKET_DATA",
                                        idempotency_key=idempotency_key)
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.rejected",
                               target_type="order", target_id=order.order_id, before=None,
                               after={"status": "rejected", "code": "RISK_NO_MARKET_DATA"},
                               request_id=request_id)
        raise _err("RISK_NO_MARKET_DATA", str(exc)) from exc

    req = _to_request(body)
    est_cost = estimate_cost(req, mark)
    balance = await repo.account_balance(session, account.broker_account_id, Decimal(str(settings.paper_starting_cash)))
    strategy_state = None
    if body.strategy_id:
        strat = await strat_repo.get_strategy(session, UUID(body.strategy_id))
        strategy_state = strat.state if strat else "draft"  # missing -> not executable
    ctx = RiskContext(account_active=True, strategy_state=strategy_state, available_balance=balance,
                      estimated_cost=est_cost, recent_order_count=0, rate_limit=None)

    decision = run_gates(req, ctx)
    if not decision.ok:
        order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                        status="rejected", reject_reason_code=decision.code,
                                        idempotency_key=idempotency_key)
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.rejected",
                               target_type="order", target_id=order.order_id, before=None,
                               after={"status": "rejected", "code": decision.code}, request_id=request_id)
        raise _err(decision.code, decision.message or decision.code)

    order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                    status="pending", idempotency_key=idempotency_key)

    if account.broker != "paper":
        raise _err("BROKER_NOT_SUPPORTED", f"broker {account.broker} not yet supported", 400)
    adapter = PaperBrokerAdapter(balance, lambda o: mark)
    result = await adapter.submit_order(_to_broker_order(body), idempotency_key or str(order.order_id))
    book = (await adapter.get_orders())[0]
    now = datetime.now(timezone.utc)

    transition(OrderStatus(order.status), OrderStatus.SUBMITTED)
    await repo.update_order(session, order, status="submitted", broker_order_id=result.broker_order_id, submitted_at=now)
    await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.submitted",
                           target_type="order", target_id=order.order_id, before=None,
                           after={"status": "submitted"}, request_id=request_id)

    if book["status"] == "filled":
        fill_price = book["fill_price"]
        await repo.insert_execution(session, tenant_id=tenant_id, order_id=order.order_id,
                                    broker_account_id=account.broker_account_id, qty=body.qty,
                                    price=fill_price, commission=Decimal(0),
                                    broker_execution_id=f"pe-{order.order_id}")
        signed = body.qty if body.side == "buy" else -body.qty
        current = await repo.get_position(session, account.broker_account_id, body.symbol.upper(),
                                          body.option_type, body.strike, body.expiry)
        new_qty, new_avg = net_position(current.qty if current else 0,
                                        current.avg_entry_price if current else Decimal(0),
                                        signed, fill_price)
        await repo.upsert_position(session, tenant_id=tenant_id, broker_account_id=account.broker_account_id,
                                   symbol=body.symbol.upper(), option_type=body.option_type,
                                   strike=body.strike, expiry=body.expiry, new_qty=new_qty, new_avg=new_avg)
        transition(OrderStatus.SUBMITTED, OrderStatus.FILLED)
        await repo.update_order(session, order, status="filled", filled_at=now)
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.filled",
                               target_type="order", target_id=order.order_id, before={"status": "submitted"},
                               after={"status": "filled", "price": str(fill_price)}, request_id=request_id)
    elif book["status"] == "cancelled":
        transition(OrderStatus.SUBMITTED, OrderStatus.CANCELLED)
        await repo.update_order(session, order, status="cancelled")
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.cancelled",
                               target_type="order", target_id=order.order_id, before={"status": "submitted"},
                               after={"status": "cancelled"}, request_id=request_id)
    # else: rests as "submitted"

    return _out(order)


async def cancel_order(session, principal, order_id, request_id) -> dict:
    order = await repo.get_order(session, UUID(order_id))
    if order is None:
        raise _err("RESOURCE_NOT_FOUND", "order not found", 404)
    if order.status not in ("pending", "submitted"):
        raise _err("ORDER_NOT_CANCELLABLE", f"cannot cancel a {order.status} order", 409)
    transition(OrderStatus(order.status), OrderStatus.CANCELLED)
    await repo.update_order(session, order, status="cancelled")
    await repo.write_audit(session, tenant_id=principal.tenant_id, user_id=principal.user_id,
                           action="order.cancelled", target_type="order", target_id=order.order_id,
                           before={"status": order.status}, after={"status": "cancelled"}, request_id=request_id)
    return _out(order)
