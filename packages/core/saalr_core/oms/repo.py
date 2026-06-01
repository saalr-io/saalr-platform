from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from saalr_core.db.models.audit import AuditLog
from saalr_core.db.models.trading import BrokerAccount, Execution, Order, Position
from saalr_core.ids import new_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_broker_account(session, broker_account_id) -> BrokerAccount | None:
    return await session.get(BrokerAccount, broker_account_id)


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


async def write_audit(session, *, tenant_id, user_id, action, target_type, target_id,
                      before, after, request_id) -> None:
    session.add(AuditLog(
        audit_id=new_id(), tenant_id=tenant_id, user_id=user_id, action=action,
        target_type=target_type, target_id=target_id, before_state=before, after_state=after,
        request_id=request_id,
    ))
    await session.flush()


# --- reconciliation queries (new) ---
async def sum_executed_qty(session, order_id) -> int:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(Execution.qty), 0)).where(Execution.order_id == order_id)
        )
    ).scalar_one()
    return int(total)


async def list_open_orders_for_account(session, broker_account_id) -> list[Order]:
    return list((await session.execute(
        select(Order).where(
            Order.broker_account_id == broker_account_id,
            Order.status.in_(("submitted", "partial")),
        )
    )).scalars().all())


async def list_active_alpaca_accounts(session) -> list[BrokerAccount]:
    """All active alpaca broker accounts. Run on an ADMIN (RLS-bypassing) session for
    cross-tenant discovery; the per-account reconcile then runs inside a tenant_session."""
    return list((await session.execute(
        select(BrokerAccount).where(BrokerAccount.broker == "alpaca", BrokerAccount.status == "active")
    )).scalars().all())
