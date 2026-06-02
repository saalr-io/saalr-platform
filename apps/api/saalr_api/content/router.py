from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal, get_principal
from . import repo

router = APIRouter(prefix="/content", tags=["content"])

_TIER_RANK = {"free": 0, "pro": 1, "premium": 2}


def _locked(tier: str, module) -> bool:
    return _TIER_RANK.get(tier, 0) < _TIER_RANK.get(module.min_tier, 0)


def _meta(module, locked: bool, status: str) -> dict:
    return {"slug": module.slug, "title": module.title, "summary": module.summary,
            "order": module.order, "min_tier": module.min_tier, "est_minutes": module.est_minutes,
            "locked": locked, "status": status}


def _not_found() -> HTTPException:
    return HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "module not found"}})


def _locked_error() -> HTTPException:
    return HTTPException(402, {"error": {"code": "ENTITLEMENT_CONTENT_REQUIRES_PRO",
                                         "message": "this module requires a Pro plan"}})


@router.get("/modules")
async def list_modules(request: Request,
                       ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    catalog = request.app.state.catalog
    status_by = {r.module_slug: r.status for r in await repo.list_progress(session, principal.user_id)}
    mods = [_meta(m, _locked(principal.tier, m), status_by.get(m.slug, "not_started"))
            for m in catalog.modules]
    return {
        "modules": mods,
        "completed": sum(1 for m in mods if m["status"] == "completed"),
        "in_progress": sum(1 for m in mods if m["status"] == "in_progress"),
        "total": len(mods),
    }


@router.get("/search")
async def search(request: Request, q: str = Query(default=""),
                 ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    _, principal = ctx
    if not q.strip():
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "q is required"}})
    catalog = request.app.state.catalog
    return {"results": [
        {"slug": h.module.slug, "title": h.module.title, "snippet": h.snippet, "score": h.score,
         "locked": _locked(principal.tier, h.module)}
        for h in catalog.search(q)
    ]}


@router.get("/progress")
async def my_progress(request: Request,
                      ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    rows = await repo.list_progress(session, principal.user_id)
    return {
        "completed": sum(1 for r in rows if r.status == "completed"),
        "in_progress": sum(1 for r in rows if r.status == "in_progress"),
        "total": len(request.app.state.catalog.modules),
        "modules": [{"slug": r.module_slug, "status": r.status,
                     "completed_at": r.completed_at.isoformat() if r.completed_at else None}
                    for r in rows],
    }


@router.get("/modules/{slug}")
async def get_module(slug: str, request: Request,
                     ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    module = request.app.state.catalog.by_slug(slug)
    if module is None:
        raise _not_found()
    if _locked(principal.tier, module):
        raise _locked_error()
    existing = await repo.get_progress(session, principal.user_id, slug)
    status = existing.status if existing else "not_started"
    if status != "completed":
        row = await repo.upsert_progress(session, tenant_id=principal.tenant_id,
                                         user_id=principal.user_id, module_slug=slug,
                                         status="in_progress", now=datetime.now(timezone.utc),
                                         existing=existing)
        status = row.status
    out = _meta(module, False, status)
    out["body"] = module.body
    return out


@router.post("/modules/{slug}/complete")
async def complete_module(slug: str, request: Request,
                          ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    module = request.app.state.catalog.by_slug(slug)
    if module is None:
        raise _not_found()
    if _locked(principal.tier, module):
        raise _locked_error()
    row = await repo.upsert_progress(session, tenant_id=principal.tenant_id,
                                     user_id=principal.user_id, module_slug=slug,
                                     status="completed", now=datetime.now(timezone.utc))
    return {"slug": slug, "status": row.status,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None}
