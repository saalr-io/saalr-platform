from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.backtest import repo as bt_repo
from saalr_core.backtest.engine import ENGINE_VERSION
from saalr_core.db.session import tenant_session
from saalr_core.queue.backtest_queue import enqueue

from ..auth import Principal, get_principal
from ..strategies import repo as strat_repo
from .schemas import BacktestRequest, estimated_duration_seconds

router = APIRouter(tags=["backtests"])


def _idem_key(tenant_id, key: str) -> str:
    return f"saalr:idem:bt:{tenant_id}:{key}"


def _accepted(backtest_id, start, end, status: str) -> dict:
    return {
        "backtest_id": str(backtest_id),
        "status": status,
        "estimated_duration_seconds": estimated_duration_seconds(start, end),
        "poll_url": f"/v1/backtests/{backtest_id}",
    }


@router.post("/v1/strategies/{strategy_id}/backtest", status_code=202)
async def create_backtest_run(
    strategy_id: UUID,
    body: BacktestRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> dict:
    session, principal = ctx
    redis = request.app.state.redis
    sm = request.app.state.sessionmaker

    strat = await strat_repo.get_strategy(session, strategy_id)
    if strat is None:
        raise HTTPException(
            404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "strategy not found"}}
        )

    if idempotency_key:
        existing = await redis.get(_idem_key(principal.tenant_id, idempotency_key))
        if existing:
            row = await bt_repo.get_backtest(session, UUID(existing))
            if row is not None:
                return _accepted(row.backtest_id, row.start_date, row.end_date, row.status)

    params = {
        "start": body.start_date.isoformat(),
        "end": body.end_date.isoformat(),
        "initial_capital": body.initial_capital,
        "include_costs": body.include_costs,
    }
    snapshot = {"config": strat.config_json, "params": params, "engine_version": ENGINE_VERSION}

    # Commit the row in its OWN transaction BEFORE enqueuing, so the worker cannot
    # read it before it exists. (get_principal's session commits only after this
    # handler returns.)
    async with tenant_session(sm, principal.tenant_id) as create_session:
        backtest_id = await bt_repo.create_backtest(
            create_session, principal.tenant_id, strategy_id, body.start_date, body.end_date, snapshot
        )

    try:
        await enqueue(redis, principal.tenant_id, backtest_id)
    except Exception as exc:  # noqa: BLE001 - row stays 'queued', reclaimable; surface 503
        raise HTTPException(
            503, {"error": {"code": "BACKTEST_ENQUEUE_FAILED", "message": "could not enqueue job"}}
        ) from exc

    if idempotency_key:
        await redis.set(_idem_key(principal.tenant_id, idempotency_key), str(backtest_id), nx=True, ex=86400)

    return _accepted(backtest_id, body.start_date, body.end_date, "queued")


@router.get("/v1/backtests/{backtest_id}")
async def get_backtest_run(
    backtest_id: UUID,
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> dict:
    session, _ = ctx
    row = await bt_repo.get_backtest(session, backtest_id)
    if row is None:
        raise HTTPException(
            404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "backtest not found"}}
        )
    out: dict = {"backtest_id": str(row.backtest_id), "status": row.status}
    if row.status == "succeeded":
        out["metrics"] = (row.metrics_json or {}).get("metrics", {})
        out["trade_log_url"] = None
    elif row.status == "failed":
        out["error"] = {"code": "BACKTEST_FAILED", "message": row.error_message}
    return out
