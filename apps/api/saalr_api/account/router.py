from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from ..auth.dependency import get_principal

router = APIRouter(tags=["account"])


class OptInRequest(BaseModel):
    opt_in: bool


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown keys -> 422
    preferred_tz: str | None = Field(default=None, min_length=1, max_length=64)
    preferred_locale: str | None = Field(default=None, min_length=1, max_length=64)


@router.post("/me/marketing/opt-in")
async def set_opt_in(body: OptInRequest,
                     ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    await session.execute(
        text("UPDATE users SET marketing_opt_in = :v WHERE user_id = :u"),
        {"v": body.opt_in, "u": str(principal.user_id)},
    )
    return {"marketing_opt_in": body.opt_in}


@router.patch("/me/profile")
async def patch_profile(body: ProfilePatch,
                        ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    fields = body.model_dump(exclude_none=True)
    if fields:
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        await session.execute(
            text(f"UPDATE users SET {sets} WHERE user_id = :u"),
            {**fields, "u": str(principal.user_id)},
        )
    return {"updated": list(fields)}


@router.post("/me/request-deletion")
async def request_deletion(ctx: tuple[AsyncSession, Principal] = Depends(get_principal)) -> dict:
    session, principal = ctx
    await session.execute(
        text("UPDATE users SET deletion_requested_at = now() "
             "WHERE user_id = :u AND deletion_requested_at IS NULL"),
        {"u": str(principal.user_id)},
    )
    return {"requested": True}
