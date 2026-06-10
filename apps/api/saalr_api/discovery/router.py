from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.db.session import tenant_session
from saalr_core.discovery import repo
from saalr_core.queue.discovery_queue import enqueue

from ..auth import Principal
from ..forecast.gating import require_ml_forecast
from .schemas import ESTIMATED_DURATION_SECONDS, DiscoveryRequest

router = APIRouter(tags=["discovery"])


def _idem_key(tenant_id, key: str) -> str:
    return f"saalr:idem:disc:{tenant_id}:{key}"


def _accepted(discovery_id, status: str) -> dict:
    return {
        "discovery_id": str(discovery_id),
        "status": status,
        "estimated_duration_seconds": ESTIMATED_DURATION_SECONDS,
        "poll_url": f"/v1/discovery/{discovery_id}",
    }


@router.post("/v1/discovery", status_code=202)
async def create_discovery_run(
    body: DiscoveryRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    session, principal = ctx
    redis = request.app.state.redis
    sm = request.app.state.sessionmaker

    if idempotency_key:
        existing = await redis.get(_idem_key(principal.tenant_id, idempotency_key))
        if existing:
            row = await repo.get_discovery(session, UUID(existing))
            if row is not None:
                return _accepted(row.discovery_id, row.status)

    async with tenant_session(sm, principal.tenant_id) as create_session:
        discovery_id = await repo.create_discovery(
            create_session,
            principal.tenant_id,
            body.underlying.upper(),
            body.market,
            body.model_dump(),
        )

    if idempotency_key:
        await redis.set(
            _idem_key(principal.tenant_id, idempotency_key),
            str(discovery_id),
            nx=True,
            ex=86400,
        )

    try:
        await enqueue(redis, principal.tenant_id, discovery_id)
    except Exception as exc:  # noqa: BLE001
        if idempotency_key:
            try:
                await redis.delete(_idem_key(principal.tenant_id, idempotency_key))
            except Exception:  # noqa: BLE001
                pass
        raise HTTPException(
            503,
            {"error": {"code": "DISCOVERY_ENQUEUE_FAILED", "message": "could not enqueue job"}},
        ) from exc

    return _accepted(discovery_id, "queued")


@router.get("/v1/discovery/{discovery_id}")
async def get_discovery_run(
    discovery_id: UUID,
    ctx: tuple[AsyncSession, Principal] = Depends(require_ml_forecast),
) -> dict:
    session, _ = ctx
    row = await repo.get_discovery(session, discovery_id)
    if row is None:
        raise HTTPException(
            404,
            {"error": {"code": "RESOURCE_NOT_FOUND", "message": "discovery not found"}},
        )
    out: dict = {"discovery_id": str(row.discovery_id), "status": row.status}
    if row.status == "succeeded" and row.result_json:
        out["as_of"] = row.as_of.isoformat() if row.as_of else None
        out.update(
            {
                k: row.result_json.get(k)
                for k in (
                    "scoring_profile",
                    "regime",
                    "results",
                    "baseline",
                    "data_quality_report",
                    "disclosure_block_id",
                )
            }
        )
    elif row.status == "failed":
        out["error"] = {"code": "DISCOVERY_FAILED", "message": row.error_message}
    return out
