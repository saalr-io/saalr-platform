from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text

from saalr_core.db.models.audit import AuditLog
from saalr_core.db.models.trading import BrokerAccount, Execution, Order, Position
from saalr_core.ids import new_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- broker accounts ---
async def create_broker_account(session, tenant_id, user_id, broker, label, is_paper) -> BrokerAccount:
    row = BrokerAccount(
        broker_account_id=new_id(), tenant_id=tenant_id, user_id=user_id, broker=broker,
        account_label=label, credential_ref="paper:local", is_paper=is_paper, status="active",
    )
    session.add(row)
    await session.flush()
    return row


async def get_broker_account(session, broker_account_id) -> BrokerAccount | None:
    return await session.get(BrokerAccount, broker_account_id)


async def list_broker_accounts(session) -> list[BrokerAccount]:
    return list((await session.execute(select(BrokerAccount).order_by(BrokerAccount.created_at.desc()))).scalars().all())


# --- orders ---
async def find_order_by_idempotency(session, tenant_id, key) -> Order | None:
    if not key:
        return None
    return (
        await session.execute(
            select(Order).where(Order.tenant_id == tenant_id, Order.idempotency_key == key)
        )
    ).scalar_one_or_none()


async def insert_order(session, *, tenant_id, user_id, body, status, reject_reason_code=None,
                       idempotency_key=None) -> Order:
    row = Order(
        order_id=new_id(), tenant_id=tenant_id,
        strategy_id=UUID(body.strategy_id) if body.strategy_id else None,
        broker_account_id=UUID(body.broker_account_id), symbol=body.symbol.upper(),
        option_type=body.option_type, strike=body.strike, expiry=body.expiry,
        side=body.side, qty=body.qty, order_type=body.order_type,
        limit_price=body.limit_price, stop_price=body.stop_price, time_in_force=body.time_in_force,
        status=status, reject_reason_code=reject_reason_code, idempotency_key=idempotency_key,
    )
    session.add(row)
    await session.flush()
    return row


async def update_order(session, order: Order, **fields) -> Order:
    for k, v in fields.items():
        setattr(order, k, v)
    await session.flush()
    return order


async def insert_execution(session, *, tenant_id, order_id, broker_account_id, qty, price,
                           commission, broker_execution_id) -> None:
    session.add(Execution(
        execution_id=new_id(), tenant_id=tenant_id, order_id=order_id,
        broker_account_id=broker_account_id, qty=qty, price=price, commission=commission,
        broker_execution_id=broker_execution_id, executed_at=_utcnow(),
    ))
    await session.flush()


async def account_balance(session, broker_account_id, starting_cash: Decimal, tenant_id) -> Decimal:
    total = (
        await session.execute(
            text("""
                SELECT COALESCE(SUM(
                    (CASE WHEN o.side='buy' THEN -1 ELSE 1 END)
                    * e.price * e.qty * (CASE WHEN o.option_type IS NOT NULL THEN 100 ELSE 1 END)
                    - e.commission
                ), 0)
                FROM executions e JOIN orders o ON o.order_id = e.order_id
                WHERE e.broker_account_id = :acct AND e.tenant_id = :tenant
            """),
            {"acct": str(broker_account_id), "tenant": str(tenant_id)},
        )
    ).scalar_one()
    return starting_cash + Decimal(str(total))


# --- positions ---
async def get_position(session, broker_account_id, symbol, option_type, strike, expiry) -> Position | None:
    stmt = select(Position).where(
        Position.broker_account_id == broker_account_id, Position.symbol == symbol,
        Position.option_type.is_(option_type) if option_type is None else Position.option_type == option_type,
    )
    stmt = stmt.where(Position.strike.is_(None) if strike is None else Position.strike == strike)
    stmt = stmt.where(Position.expiry.is_(None) if expiry is None else Position.expiry == expiry)
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_position(session, *, tenant_id, broker_account_id, symbol, option_type, strike,
                          expiry, new_qty: int, new_avg: Decimal) -> None:
    existing = await get_position(session, broker_account_id, symbol, option_type, strike, expiry)
    if new_qty == 0:
        if existing is not None:
            await session.delete(existing)
            await session.flush()
        return
    if existing is None:
        session.add(Position(
            position_id=new_id(), tenant_id=tenant_id, broker_account_id=broker_account_id,
            symbol=symbol, option_type=option_type, strike=strike, expiry=expiry,
            qty=new_qty, avg_entry_price=new_avg, opened_at=_utcnow(), last_updated_at=_utcnow(),
        ))
    else:
        existing.qty = new_qty
        existing.avg_entry_price = new_avg
        existing.last_updated_at = _utcnow()
    await session.flush()


async def list_positions(session, broker_account_id=None) -> list[Position]:
    stmt = select(Position).order_by(Position.last_updated_at.desc())
    if broker_account_id is not None:
        stmt = stmt.where(Position.broker_account_id == broker_account_id)
    return list((await session.execute(stmt)).scalars().all())


async def get_order(session, order_id) -> Order | None:
    return await session.get(Order, order_id)


async def list_orders(session, limit, cursor) -> list[Order]:
    stmt = select(Order).order_by(Order.created_at.desc(), Order.order_id.desc())
    if cursor is not None:
        created_at, oid = cursor
        stmt = stmt.where(
            (Order.created_at < created_at) | ((Order.created_at == created_at) & (Order.order_id < oid))
        )
    return list((await session.execute(stmt.limit(limit))).scalars().all())


# --- audit ---
async def write_audit(session, *, tenant_id, user_id, action, target_type, target_id,
                      before, after, request_id) -> None:
    session.add(AuditLog(
        audit_id=new_id(), tenant_id=tenant_id, user_id=user_id, action=action,
        target_type=target_type, target_id=target_id, before_state=before, after_state=after,
        request_id=request_id,
    ))
    await session.flush()
