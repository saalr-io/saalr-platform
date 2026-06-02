from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from saalr_core.rag.chat import ChatError
from saalr_core.rag.qa import retrieve_context
from saalr_core.research.note import ResearchInputs, build_research_prompt, estimate_cost
from saalr_core.sentiment.repo import latest_sentiment
from saalr_ml.forecast import vol_forecast

from ..forecast.repo import load_closes
from . import repo

_logger = logging.getLogger("saalr.research")
_CACHE_TTL = timedelta(hours=6)


def _out(note, *, cached: bool) -> dict:
    return {
        "note_id": str(note.note_id), "ticker": note.ticker, "market": note.market,
        "summary": note.summary, "signals": note.signals_json, "sources": note.sources_json,
        "model": note.model,
        "usage": {"prompt_tokens": note.prompt_tokens, "completion_tokens": note.completion_tokens},
        "cost_usd": str(note.cost_usd), "cached": cached, "created_at": note.created_at.isoformat(),
    }


async def gather_inputs(session, state, ticker: str, market: str) -> ResearchInputs:
    closes = await load_closes(session, ticker, market)
    if not closes:
        raise HTTPException(404, {"error": {"code": "RESOURCE_NOT_FOUND",
                                            "message": "no price data for ticker"}})
    spot = closes[-1]

    # GARCH vol forecast is a best-effort enrichment: never let it fail the note.
    vol = None
    if len(closes) >= 250:
        try:
            f = vol_forecast(closes, horizon=10)
            pf = f["primary_forecast"]
            vol = {
                "horizon_days": f["horizon_days"],
                "primary_model": f["primary_model"],
                "forecast_mean": round(sum(pf) / len(pf), 4) if pf else None,
                "status": f["alternative_models"][0]["status"] if f.get("alternative_models") else None,
            }
        except Exception as exc:  # noqa: BLE001 - best-effort signal; degrade, never 500
            _logger.warning("garch forecast unavailable for %s: %s", ticker, exc)
            vol = None

    sent = await latest_sentiment(session, ticker, market)
    sentiment = None
    if sent is not None:
        sentiment = {
            "score": round(float(sent["score"]), 4), "label": sent["label"],
            "confident": sent["confident"],
            "as_of": sent["as_of"].isoformat() if sent.get("as_of") else None,
        }

    excerpts: list[tuple[str, str, str]] = []
    embed = getattr(state, "embedding_provider", None)
    if embed is not None:
        try:
            vectors = await embed.embed([f"options {ticker} implied volatility sentiment risk"])
            if len(vectors) == 1:
                hits = await retrieve_context(session, vectors[0], model=embed.model_name, k=3)
                catalog = getattr(state, "catalog", None)
                for hit in hits:
                    title = hit.module_slug
                    module = catalog.by_slug(hit.module_slug) if catalog is not None else None
                    if module is not None:
                        title = module.title
                    excerpts.append((hit.module_slug, title, hit.content))
        except Exception as exc:  # noqa: BLE001 - best-effort enrichment; degrade, never 500
            _logger.warning("content retrieval unavailable for %s: %s", ticker, exc)
            excerpts = []

    return ResearchInputs(ticker, market, spot, vol, sentiment, excerpts)


async def run_research(session, principal, state, ticker: str, market: str, refresh: bool) -> dict:
    if not refresh:
        cached = await repo.recent_note(session, ticker, market,
                                        datetime.now(timezone.utc) - _CACHE_TTL)
        if cached is not None:
            return _out(cached, cached=True)
    inputs = await gather_inputs(session, state, ticker, market)
    chat = getattr(state, "chat_provider", None)
    if chat is None:
        raise HTTPException(503, {"error": {"code": "FEATURE_UNAVAILABLE",
                                            "message": "the research assistant is not configured"}})
    system, user = build_research_prompt(inputs)
    try:
        result = await chat.complete(system, user)
    except ChatError as exc:
        _logger.warning("research chat failed for %s: %s", ticker, exc)
        raise HTTPException(502, {"error": {"code": "LLM_UNAVAILABLE",
                                            "message": "the research assistant is temporarily unavailable"}}) from exc
    signals = {"spot": inputs.spot, "vol_forecast": inputs.vol_forecast, "sentiment": inputs.sentiment}
    sources = [{"slug": slug, "title": title} for slug, title, _content in inputs.content_excerpts]
    cost = estimate_cost(chat.model_name, result.prompt_tokens, result.completion_tokens)
    note = await repo.insert_note(
        session, tenant_id=principal.tenant_id, user_id=principal.user_id, ticker=ticker,
        market=market, summary=result.text, signals=signals, sources=sources, model=chat.model_name,
        prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens, cost_usd=cost,
    )
    return _out(note, cached=False)
