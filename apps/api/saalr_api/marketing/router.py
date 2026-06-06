from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import text

router = APIRouter(tags=["marketing"])


@router.get("/unsubscribe")
async def unsubscribe(request: Request, token: str = Query(...)) -> dict:
    # Neutral response regardless of token validity (no user enumeration).
    try:
        tok = str(UUID(token))
    except ValueError:
        return {"unsubscribed": True}
    sm = request.app.state.sessionmaker
    async with sm() as s, s.begin():
        await s.execute(
            text("UPDATE users SET marketing_opt_in = FALSE WHERE unsubscribe_token = :t"),
            {"t": tok},
        )
    return {"unsubscribed": True}
