from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from . import repo, service
from .gating import require_research_agent
from .schemas import RunRequest

router = APIRouter(prefix="/research", tags=["research"])


def _note_row(note) -> dict:
    return {"note_id": str(note.note_id), "ticker": note.ticker, "market": note.market,
            "model": note.model, "cost_usd": str(note.cost_usd),
            "created_at": note.created_at.isoformat()}


@router.post("/run")
async def run(body: RunRequest, request: Request,
              ctx: tuple[AsyncSession, Principal] = Depends(require_research_agent)) -> dict:
    session, principal = ctx
    ticker = body.ticker.strip().upper()
    if not ticker or not ticker.isalpha():
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "invalid ticker"}})
    if body.market not in ("US",):
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "unsupported market"}})
    return await service.run_research(session, principal, request.app.state, ticker, body.market,
                                      body.refresh)


@router.get("/notes")
async def list_notes(limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
                     ctx: tuple[AsyncSession, Principal] = Depends(require_research_agent)) -> dict:
    session, _ = ctx
    decoded = None
    if cursor:
        try:
            ts, nid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
            decoded = (datetime.fromisoformat(ts), UUID(nid))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                                "message": "bad cursor"}}) from exc
    rows = await repo.list_notes(session, limit, decoded)
    nxt = None
    if len(rows) == limit:
        last = rows[-1]
        nxt = base64.urlsafe_b64encode(f"{last.created_at.isoformat()}|{last.note_id}".encode()).decode()
    return {"notes": [_note_row(r) for r in rows], "next_cursor": nxt}


@router.get("/notes/{note_id}")
async def get_one(note_id: UUID,
                  ctx: tuple[AsyncSession, Principal] = Depends(require_research_agent)) -> dict:
    session, _ = ctx
    note = await repo.get_note(session, note_id)
    if note is None:
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND", "message": "note not found"}})
    return {**_note_row(note), "summary": note.summary, "signals": note.signals_json,
            "sources": note.sources_json,
            "usage": {"prompt_tokens": note.prompt_tokens, "completion_tokens": note.completion_tokens}}
