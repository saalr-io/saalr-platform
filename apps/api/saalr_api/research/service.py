from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from saalr_core.db.session import tenant_session
from saalr_core.queue.research_queue import enqueue

from . import repo

_logger = logging.getLogger("saalr.research")
_CACHE_TTL = timedelta(hours=6)
_DAILY_LIMIT = 10


def _out(note, *, cached: bool) -> dict:
    return {
        "note_id": str(note.note_id), "ticker": note.ticker, "market": note.market,
        "summary": note.summary, "signals": note.signals_json, "sources": note.sources_json,
        "model": note.model,
        "usage": {"prompt_tokens": note.prompt_tokens, "completion_tokens": note.completion_tokens},
        "cost_usd": str(note.cost_usd) if note.cost_usd is not None else None,
        "status": note.status, "cached": cached, "created_at": note.created_at.isoformat(),
    }


def _accepted(note_id, status: str) -> dict:
    return {"note_id": str(note_id), "status": status, "poll_url": f"/research/notes/{note_id}"}


def _utc_midnight() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


async def run_research(session, principal, redis, sessionmaker, ticker: str, market: str,
                       refresh: bool) -> dict:
    """Enqueue (or short-circuit) a research run. Returns {http_status, body}."""
    if not refresh:
        cached = await repo.recent_succeeded_note(
            session, ticker, market, datetime.now(timezone.utc) - _CACHE_TTL)
        if cached is not None:
            return {"http_status": 200, "body": _out(cached, cached=True)}

    inflight = await repo.in_flight_run(session, ticker, market)
    if inflight is not None:
        return {"http_status": 202, "body": _accepted(inflight.note_id, inflight.status)}

    if await repo.count_runs_today(session, principal.tenant_id, _utc_midnight()) >= _DAILY_LIMIT:
        raise HTTPException(429, {"error": {"code": "RATE_LIMIT_RESEARCH_DAILY_EXCEEDED",
                                            "message": f"daily research limit of {_DAILY_LIMIT} reached"}})

    # Create the row in its OWN committed transaction BEFORE enqueuing, so the worker
    # cannot read a row that does not yet exist (get_principal's session commits only
    # after the handler returns).
    async with tenant_session(sessionmaker, principal.tenant_id) as cs:
        note_id = await repo.create_queued_run(
            cs, tenant_id=principal.tenant_id, user_id=principal.user_id,
            ticker=ticker, market=market)

    try:
        await enqueue(redis, principal.tenant_id, note_id)
    except Exception as exc:  # noqa: BLE001 - row stays 'queued' + reclaimable; surface 503
        _logger.warning("research enqueue failed for %s: %s", note_id, exc)
        raise HTTPException(503, {"error": {"code": "RESEARCH_ENQUEUE_FAILED",
                                            "message": "could not enqueue research run"}}) from exc

    return {"http_status": 202, "body": _accepted(note_id, "queued")}
