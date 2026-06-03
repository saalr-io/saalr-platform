from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import Principal
from . import repo, service
from .gating import require_research_agent
from .schemas import RunRequest

router = APIRouter(prefix="/research", tags=["research"])

_ERROR_MESSAGES = {
    "RESEARCH_NO_PRICE_DATA": "no price data for ticker",
    "RESEARCH_LLM_UNAVAILABLE": "the research assistant is temporarily unavailable",
    "RESEARCH_GENERATION_FAILED": "research generation failed",
    "RESEARCH_BUDGET_EXCEEDED": "monthly research budget reached",
}


def _note_row(note) -> dict:
    return {"note_id": str(note.note_id), "ticker": note.ticker, "market": note.market,
            "model": note.model,
            "cost_usd": str(note.cost_usd) if note.cost_usd is not None else None,
            "created_at": note.created_at.isoformat()}


@router.post("/run")
async def run(body: RunRequest, request: Request, response: Response,
              ctx: tuple[AsyncSession, Principal] = Depends(require_research_agent)) -> dict:
    session, principal = ctx
    ticker = body.ticker.strip().upper()
    if not ticker or not ticker.isalpha():
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "invalid ticker"}})
    if body.market not in ("US",):
        raise HTTPException(400, {"error": {"code": "VALIDATION_INVALID_PARAMETER",
                                            "message": "unsupported market"}})
    result = await service.run_research(
        session, principal, request.app.state.redis, request.app.state.sessionmaker,
        request.app.state.llm_budget_cap, ticker, body.market, body.refresh)
    response.status_code = result["http_status"]
    return result["body"]


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
    rows = await repo.list_succeeded_notes(session, limit, decoded)
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
    if note.status in ("queued", "running"):
        return {"note_id": str(note.note_id), "status": note.status}
    if note.status == "failed":
        code = note.error_message or "RESEARCH_GENERATION_FAILED"
        return {"note_id": str(note.note_id), "status": "failed",
                "error": {"code": code, "message": _ERROR_MESSAGES.get(code, "research generation failed")}}
    return {**_note_row(note), "status": "succeeded", "summary": note.summary,
            "signals": note.signals_json, "sources": note.sources_json,
            "usage": {"prompt_tokens": note.prompt_tokens,
                      "completion_tokens": note.completion_tokens}}
