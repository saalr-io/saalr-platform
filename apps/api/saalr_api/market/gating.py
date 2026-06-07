from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.tiers import entitlements_for

from ..auth import Principal, get_principal


async def require_vol_surface(
    ctx: tuple[AsyncSession, Principal] = Depends(get_principal),
) -> AsyncIterator[tuple[AsyncSession, Principal]]:
    """Pass through (session, principal) only if the tier has the vol_surface entitlement."""
    _session, principal = ctx
    if not entitlements_for(principal.tier)["vol_surface"]:
        raise HTTPException(
            status_code=402,
            detail={
                "error": {
                    "code": "ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO",
                    "message": "vol surface and Greeks require a Pro or Premium plan",
                }
            },
        )
    yield ctx
