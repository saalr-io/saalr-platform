from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.strategies import templates
from saalr_core.strategies.state import IllegalTransition, StrategyState, transition
from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal
from . import repo, service
from .schemas import AnalyzeIn, StrategyCreate, StrategyUpdate, TransitionIn

router = APIRouter(prefix="/v1/strategies", tags=["strategies"])


def _out(row) -> dict:
    return {
        "strategy_id": str(row.strategy_id), "name": row.name, "description": row.description,
        "state": row.state, "market": row.market, "config": row.config_json,
        "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat(),
    }


def _not_found() -> HTTPException:
    return HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "strategy not found"}})


def _legs_to_dicts(cfg) -> list[dict]:
    return [vars(leg) for leg in cfg.legs]


@router.get("/templates")
async def get_templates(ctx: tuple = Depends(get_principal)) -> dict:
    return {"templates": templates.list_templates()}


@router.post("/templates/{key}/build")
async def build_template(key: str, body: dict, ctx: tuple = Depends(get_principal)) -> dict:
    try:
        cfg = templates.build(key, body["underlying"], body["expiry"],
                              float(body["atm_strike"]), float(body.get("width", 5.0)))
    except KeyError:
        raise _not_found()
    return {"underlying": cfg.underlying, "legs": _legs_to_dicts(cfg)}


@router.post("/analyze")
async def analyze(body: AnalyzeIn, request: Request,
                  ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    config = body.config.to_domain()
    if not body.live:
        return service.analyze_pure(config)
    if not entitlements_for(principal.tier)["vol_surface"]:
        raise HTTPException(402, {"error": {
            "code": "ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO",
            "message": "live strategy analysis requires a Pro or Premium plan"}})
    s = request.app.state
    from ..market.service import MarketService
    ms = MarketService(s.market_provider, s.rate_provider, s.redis, s.vol_surface_ttl)
    return await service.analyze_live(config, ms, session, config.underlying, "US", body.target_date)


@router.post("")
async def create_strategy(body: StrategyCreate,
                          ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    cfg = body.config.to_domain()
    config_json = {"underlying": cfg.underlying, "legs": _legs_to_dicts(cfg)}
    row = await repo.insert_strategy(
        session, principal.tenant_id, principal.user_id, body.name, body.description,
        config_json, body.market,
    )
    return _out(row)


@router.get("")
async def list_strategies(limit: int = Query(20, le=100), cursor: str | None = None,
                          ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    decoded = None
    if cursor:
        ts, sid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        decoded = (datetime.fromisoformat(ts), UUID(sid))
    rows = await repo.list_strategies(session, limit, decoded)
    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = base64.urlsafe_b64encode(
            f"{last.created_at.isoformat()}|{last.strategy_id}".encode()).decode()
    return {"strategies": [_out(r) for r in rows], "next_cursor": next_cursor}


@router.get("/{strategy_id}")
async def get_one(strategy_id: UUID,
                  ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    return _out(row)


@router.patch("/{strategy_id}")
async def patch(strategy_id: UUID, body: StrategyUpdate,
                ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    if row.state != "draft":
        raise HTTPException(409, {"error": {
            "code": "STRATEGY_NOT_EDITABLE", "message": "only draft strategies can be edited"}})
    fields: dict = {}
    if body.name is not None:
        fields["name"] = body.name
    if body.description is not None:
        fields["description"] = body.description
    if body.config is not None:
        cfg = body.config.to_domain()
        fields["config_json"] = {"underlying": cfg.underlying, "legs": _legs_to_dicts(cfg)}
    await repo.update_strategy(session, row, **fields)
    return _out(row)


@router.post("/{strategy_id}/transition")
async def do_transition(strategy_id: UUID, body: TransitionIn,
                        ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    try:
        new_state = transition(StrategyState(row.state), StrategyState(body.target_state))
    except IllegalTransition as exc:
        raise HTTPException(409, {"error": {"code": "STRATEGY_ILLEGAL_TRANSITION", "message": str(exc)}})
    except ValueError as exc:
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER", "message": str(exc)}})
    await repo.update_strategy(session, row, state=new_state.value)
    return _out(row)


@router.delete("/{strategy_id}")
async def archive(strategy_id: UUID,
                  ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, _ = ctx
    row = await repo.get_strategy(session, strategy_id)
    if row is None:
        raise _not_found()
    await repo.update_strategy(session, row, state=StrategyState.ARCHIVED.value)
    return _out(row)
