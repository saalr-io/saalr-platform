from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal


async def require_research_agent(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    _session, principal = ctx
    if not entitlements_for(principal.tier)["research_agent"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": {
                    "code": "ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM",
                    "message": "research notes require a Premium plan",
                }
            },
        )
    yield ctx
