from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_brokers.alpaca import BrokerError
from saalr_brokers.credentials import CredentialError
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
from .schemas import OrderCreate, StrategyOrderCreate  # noqa: F401  (StrategyOrderCreate used by place_strategy)

_MULT = 100
_logger = logging.getLogger("saalr.oms")


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


async def place_order(session: AsyncSession, principal, body: OrderCreate, idempotency_key,
                      request_id, adapter_factory=None) -> dict:
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
    if account.broker not in ("paper", "alpaca"):
        raise _err("BROKER_NOT_SUPPORTED", f"broker {account.broker} not yet supported", 400)
    is_alpaca = account.broker == "alpaca"

    # Resolve the alpaca adapter up front so a credential failure happens before any row insert.
    adapter = None
    if is_alpaca:
        if adapter_factory is None:
            raise _err("BROKER_UNAVAILABLE", "no alpaca adapter configured", 502)
        try:
            adapter = adapter_factory(account)
        except CredentialError as exc:
            raise _err("BROKER_CREDENTIALS_UNAVAILABLE", "broker credentials unavailable", 502) from exc

    today = datetime.now(timezone.utc).date()
    try:
        mark = await model_mark(session, symbol=body.symbol.upper(), market="US",
                                option_type=body.option_type, strike=body.strike,
                                expiry=body.expiry, today=today)
    except NoMarketData as exc:
        if not is_alpaca:
            order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                            status="rejected", reject_reason_code="RISK_NO_MARKET_DATA",
                                            idempotency_key=idempotency_key)
            await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.rejected",
                                   target_type="order", target_id=order.order_id, before=None,
                                   after={"status": "rejected", "code": "RISK_NO_MARKET_DATA"},
                                   request_id=request_id)
            raise _err("RISK_NO_MARKET_DATA", str(exc)) from exc
        mark = None  # alpaca: the broker enforces; a missing model mark must not block submission

    req = _to_request(body)
    est_cost = estimate_cost(req, mark) if mark is not None else Decimal(0)
    if is_alpaca:
        try:
            balance = await adapter.get_account_balance()
        except BrokerError as exc:
            raise _err("BROKER_UNAVAILABLE", "broker unavailable", 502) from exc
    else:
        balance = await repo.account_balance(session, account.broker_account_id,
                                             Decimal(str(settings.paper_starting_cash)), tenant_id)

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

    try:
        order = await repo.insert_order(session, tenant_id=tenant_id, user_id=user_id, body=body,
                                        status="pending", idempotency_key=idempotency_key)
    except IntegrityError as exc:  # a concurrent request with the same Idempotency-Key won the race
        raise _err("ORDER_DUPLICATE_IN_FLIGHT",
                   "a duplicate order is in flight; retry to read the result", 409) from exc

    now = datetime.now(timezone.utc)
    if is_alpaca:
        return await _submit_alpaca(session, order, body, adapter, idempotency_key,
                                    tenant_id, user_id, request_id, now)

    adapter = PaperBrokerAdapter(balance, lambda o: mark)
    result = await adapter.submit_order(_to_broker_order(body), idempotency_key or str(order.order_id))
    book = (await adapter.get_orders())[0]

    transition(OrderStatus(order.status), OrderStatus.SUBMITTED)
    await repo.update_order(session, order, status="submitted", broker_order_id=result.broker_order_id, submitted_at=now)
    await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.submitted",
                           target_type="order", target_id=order.order_id, before=None,
                           after={"status": "submitted"}, request_id=request_id)

    if book["status"] == "filled":
        fill_price = book["fill_price"]
        if fill_price is None:  # invariant: a filled order always has a fill price
            raise _err("INTERNAL", "adapter returned filled with no fill price", 500)
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


async def place_strategy(session: AsyncSession, principal, body, idem, request_id,
                         adapter_factory=None) -> dict:
    """Place each option/equity leg of a strategy as a standalone paper order (no strategy_id —
    the risk gate rejects a strategy_id whose strategy isn't in paper/live state). Cash legs are
    skipped. place_order raises HTTPException on a reject, so each leg is wrapped; a leg placed
    before a later reject stays placed — the per-leg result is the honest record."""
    results: list[dict] = []
    for i, leg in enumerate(body.legs):
        if leg.kind == "cash":
            results.append({"leg_index": i, "kind": "cash", "status": "skipped"})
            continue
        order = OrderCreate(
            broker_account_id=body.broker_account_id,
            symbol=body.underlying.upper(),
            side=(leg.side or "BUY").lower(),  # OMS risk gate expects lowercase buy/sell
            qty=leg.qty or 0,
            order_type="market",
            option_type=leg.option_type if leg.kind == "option" else None,
            strike=leg.strike if leg.kind == "option" else None,
            expiry=leg.expiry if leg.kind == "option" else None,
            time_in_force="day",
        )
        try:
            res = await place_order(session, principal, order, f"{idem}:{i}", request_id, adapter_factory)
            results.append({"leg_index": i, "kind": leg.kind, "status": res["status"],
                            "order_id": res["order_id"]})
        except HTTPException as exc:
            code = (exc.detail["error"]["code"]
                    if isinstance(exc.detail, dict) and "error" in exc.detail else str(exc.detail))
            results.append({"leg_index": i, "kind": leg.kind, "status": "rejected", "reject_code": code})
    placed = sum(1 for r in results if r["status"] not in ("rejected", "skipped"))
    rejected = sum(1 for r in results if r["status"] == "rejected")
    return {"broker_account_id": str(body.broker_account_id), "results": results,
            "placed": placed, "rejected": rejected}


async def _submit_alpaca(session, order, body, adapter, idempotency_key, tenant_id, user_id,
                         request_id, now) -> dict:
    """Alpaca submit: the order rests 'submitted' (async fills come via reconciliation)."""
    try:
        result = await adapter.submit_order(_to_broker_order(body), idempotency_key or str(order.order_id))
    except BrokerError as exc:
        raise _err("BROKER_UNAVAILABLE", "broker unavailable", 502) from exc

    if result.status == "rejected":
        transition(OrderStatus(order.status), OrderStatus.REJECTED)
        await repo.update_order(session, order, status="rejected", reject_reason_code="BROKER_REJECTED")
        await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.rejected",
                               target_type="order", target_id=order.order_id, before={"status": "pending"},
                               after={"status": "rejected", "code": "BROKER_REJECTED"}, request_id=request_id)
        raise _err("BROKER_REJECTED", result.rejected_reason or "broker rejected the order")

    transition(OrderStatus(order.status), OrderStatus.SUBMITTED)
    await repo.update_order(session, order, status="submitted",
                            broker_order_id=result.broker_order_id, submitted_at=now)
    await repo.write_audit(session, tenant_id=tenant_id, user_id=user_id, action="order.submitted",
                           target_type="order", target_id=order.order_id, before={"status": "pending"},
                           after={"status": "submitted"}, request_id=request_id)
    return _out(order)


async def cancel_order(session, principal, order_id, request_id, adapter_factory=None) -> dict:
    order = await repo.get_order(session, UUID(order_id))
    if order is None:
        raise _err("RESOURCE_NOT_FOUND", "order not found", 404)
    if order.status not in ("pending", "submitted"):
        raise _err("ORDER_NOT_CANCELLABLE", f"cannot cancel a {order.status} order", 409)

    account = await repo.get_broker_account(session, order.broker_account_id)
    if (account is not None and account.broker == "alpaca" and order.broker_order_id
            and adapter_factory is not None):
        try:
            await adapter_factory(account).cancel_order(order.broker_order_id)
        except (CredentialError, BrokerError) as exc:  # best-effort; reconciliation confirms terminal state
            _logger.warning("alpaca cancel failed for order %s: %s", order_id, exc)

    transition(OrderStatus(order.status), OrderStatus.CANCELLED)
    await repo.update_order(session, order, status="cancelled")
    await repo.write_audit(session, tenant_id=principal.tenant_id, user_id=principal.user_id,
                           action="order.cancelled", target_type="order", target_id=order.order_id,
                           before={"status": order.status}, after={"status": "cancelled"}, request_id=request_id)
    return _out(order)
