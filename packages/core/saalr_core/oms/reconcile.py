from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from saalr_core.oms.fsm import IllegalOrderTransition, OrderStatus, transition
from saalr_core.oms.positions import net_position

from . import repo


async def reconcile_account(session, adapter, account, *, lookback_buffer_seconds: int = 300,
                            now: datetime) -> dict:
    """Poll Alpaca for the account's open orders, persist fill deltas + positions, advance status.

    Drives off LOCAL open orders (status submitted/partial) + a covering lookback window, matched
    by broker_order_id, so Alpaca's after-filters-by-submit-time never hides a late fill. Stamps
    account.last_reconciled_at. Returns a per-status summary for logging/tests.

    Incremental fill price is the broker's cumulative ``filled_avg_price`` (a VWAP approximation):
    Alpaca's orders endpoint exposes no per-fill price, so a delta execution is priced at the
    running average rather than the true marginal fill. Per-fill accuracy would need the
    trade-update websocket (deferred).

    Idempotency relies on ``broker_execution_id = recon:{order_id}:{cumulative_filled}``: a re-poll
    at the same fill level computes ``delta == 0`` and skips the insert. This assumes a SINGLE
    reconcile worker (the OMS-3b deployment runs one sequential-pass loop). Running two workers
    concurrently could let both compute the same delta before either flushes; the unique index on
    that key would then raise IntegrityError. Multi-worker reconciliation (a savepoint around the
    insert, or claim-based partitioning) is deferred with worker scaling.
    """
    summary = {"matched": 0, "filled": 0, "partial": 0, "cancelled": 0, "rejected": 0}

    open_orders = await repo.list_open_orders_for_account(session, account.broker_account_id)
    if not open_orders:
        account.last_reconciled_at = now
        await session.flush()
        return summary

    submitted_times = [o.submitted_at for o in open_orders if o.submitted_at]
    since = (min(submitted_times) - timedelta(seconds=lookback_buffer_seconds)) if submitted_times else None
    rows = await adapter.get_orders(since)
    by_id = {r["broker_order_id"]: r for r in rows}

    for o in open_orders:
        row = by_id.get(o.broker_order_id)
        if row is None:
            continue
        summary["matched"] += 1

        observed = int(row["filled_qty"])
        recorded = await repo.sum_executed_qty(session, o.order_id)
        delta = observed - recorded
        avg = row.get("filled_avg_price")
        if delta > 0 and avg is not None:
            await repo.insert_execution(
                session, tenant_id=o.tenant_id, order_id=o.order_id,
                broker_account_id=o.broker_account_id, qty=delta, price=avg, commission=Decimal(0),
                broker_execution_id=f"recon:{o.order_id}:{observed}",
            )
            signed = delta if o.side == "buy" else -delta
            current = await repo.get_position(session, o.broker_account_id, o.symbol,
                                              o.option_type, o.strike, o.expiry)
            new_qty, new_avg = net_position(
                current.qty if current else 0,
                current.avg_entry_price if current else Decimal(0), signed, avg,
            )
            await repo.upsert_position(
                session, tenant_id=o.tenant_id, broker_account_id=o.broker_account_id,
                symbol=o.symbol, option_type=o.option_type, strike=o.strike, expiry=o.expiry,
                new_qty=new_qty, new_avg=new_avg,
            )

        new_status = row["status"]
        if new_status != o.status:
            try:
                transition(OrderStatus(o.status), OrderStatus(new_status))
            except IllegalOrderTransition:
                continue  # e.g. a status that doesn't advance our FSM; leave as-is
            fields = {"status": new_status}
            if new_status == "filled":
                fields["filled_at"] = now
            before = {"status": o.status}
            await repo.update_order(session, o, **fields)
            await repo.write_audit(
                session, tenant_id=o.tenant_id, user_id=account.user_id,
                action=f"order.{new_status}", target_type="order", target_id=o.order_id,
                before=before, after={"status": new_status},
                request_id=f"recon:{account.broker_account_id}",
            )
            if new_status in summary:
                summary[new_status] += 1

    account.last_reconciled_at = now
    await session.flush()
    return summary
