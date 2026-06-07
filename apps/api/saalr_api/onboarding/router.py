from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from ..auth.dependency import get_principal
from . import repo

router = APIRouter(tags=["onboarding"])


class CompleteRequest(BaseModel):
    step: str


def _payload(steps: list[str]) -> dict:
    return {"steps": steps, "all_done": all(s in steps for s in repo.ONBOARDING_STEPS)}


@router.get("/onboarding")
async def get_onboarding(ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    return _payload(await repo.list_steps(session, principal.tenant_id))


@router.post("/onboarding/complete")
async def complete(body: CompleteRequest,
                   ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    if body.step not in repo.ONBOARDING_STEPS:
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "unknown onboarding step"}})
    await repo.mark_step(session, principal.tenant_id, body.step)
    return _payload(await repo.list_steps(session, principal.tenant_id))
