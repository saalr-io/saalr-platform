from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text

from saalr_core.db.models.trading import BrokerAccount, Order, Position
from saalr_core.ids import new_id
from saalr_core.oms.repo import (  # noqa: F401 — re-exported so existing call sites are unchanged
    get_broker_account,
    get_position,
    insert_execution,
    update_order,
    upsert_position,
    write_audit,
)


# --- broker accounts ---
async def create_broker_account(session, tenant_id, user_id, broker, label, is_paper,
                                credential_ref="paper:local") -> BrokerAccount:
    row = BrokerAccount(
        broker_account_id=new_id(), tenant_id=tenant_id, user_id=user_id, broker=broker,
        account_label=label, credential_ref=credential_ref, is_paper=is_paper, status="active",
    )
    session.add(row)
    await session.flush()
    return row


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
