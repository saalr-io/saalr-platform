from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from saalr_core.db.session import tenant_session
from saalr_core.llm import repo as llm_repo
from saalr_core.llm.cost import BudgetExceeded, budget_exceeded, month_start
from saalr_core.marketdata.bars import load_closes
from saalr_core.rag.chat import ChatError
from saalr_core.rag.embeddings import EmbeddingError
from saalr_core.rag.qa import retrieve_context
from saalr_core.research import repo
from saalr_core.research.graph import run_agent_graph
from saalr_core.research.note import ResearchInputs
from saalr_core.sentiment.repo import latest_sentiment
from saalr_ml.forecast import vol_forecast

log = logging.getLogger("saalr.research.worker")


class NoPriceData(Exception):
    pass


async def gather_inputs(session, *, embedding_provider, catalog, ticker: str, market: str) -> ResearchInputs:
    closes = await load_closes(session, ticker, market)
    if not closes:
        raise NoPriceData(ticker)
    spot = closes[-1]

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
        except Exception as exc:  # noqa: BLE001 - best-effort signal; degrade, never fail the note
            log.warning("garch forecast unavailable for %s: %s", ticker, exc)
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
    if embedding_provider is not None:
        try:
            vectors = await embedding_provider.embed(
                [f"options {ticker} implied volatility sentiment risk"])
            if len(vectors) == 1:
                hits = await retrieve_context(
                    session, vectors[0], model=embedding_provider.model_name, k=3)
                for hit in hits:
                    title = hit.module_slug
                    module = catalog.by_slug(hit.module_slug) if catalog is not None else None
                    if module is not None:
                        title = module.title
                    excerpts.append((hit.module_slug, title, hit.content))
        except Exception as exc:  # noqa: BLE001 - best-effort enrichment; degrade, never fail the note
            log.warning("content retrieval unavailable for %s: %s", ticker, exc)
            excerpts = []

    return ResearchInputs(ticker, market, spot, vol, sentiment, excerpts)


async def run_research_job(sessionmaker, tenant_id: UUID, note_id: UUID, *,
                           chat_provider, embedding_provider, catalog, cap: Decimal) -> dict:
    """Generate the note for a queued run. 3 phases, each isolating its failure mode.

    A re-delivered job whose row is already succeeded/failed is a no-op (idempotent)."""
    # Phase 1 — load + budget check + mark running.
    try:
        async with tenant_session(sessionmaker, tenant_id) as session:
            note = await repo.get_note(session, note_id)
            if note is None:
                return {"status": "missing"}
            if note.status in ("succeeded", "failed"):
                return {"status": note.status}
            spent = await llm_repo.month_to_date_cost(
                session, tenant_id, month_start(datetime.now(timezone.utc)))
            if budget_exceeded(spent, cap):
                raise BudgetExceeded(f"month-to-date {spent} >= cap {cap}")
            ticker, market, user_id = note.ticker, note.market, note.user_id
            await repo.mark_running(session, note_id)
    except BudgetExceeded as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_BUDGET_EXCEEDED", exc)
    except Exception as exc:  # noqa: BLE001 - persisted as failed in a fresh tx
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_GENERATION_FAILED", exc)

    # Phase 2 — compute: gather signals, then run the multi-agent graph (each call metered).
    try:
        async with tenant_session(sessionmaker, tenant_id) as session:
            inputs = await gather_inputs(
                session, embedding_provider=embedding_provider, catalog=catalog,
                ticker=ticker, market=market)
        if chat_provider is None:
            raise ChatError("no chat provider configured")
        graph = await run_agent_graph(
            sessionmaker, tenant_id, user_id, inputs=inputs, gateway=chat_provider,
            cap=cap, note_id=note_id)
    except NoPriceData as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_NO_PRICE_DATA", exc)
    except BudgetExceeded as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_BUDGET_EXCEEDED", exc)
    except (ChatError, EmbeddingError) as exc:
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_LLM_UNAVAILABLE", exc)
    except Exception as exc:  # noqa: BLE001
        return await _fail(sessionmaker, tenant_id, note_id, "RESEARCH_GENERATION_FAILED", exc)

    # Phase 3 — persist the synthesis with summed usage (the graph already recorded each call).
    signals = {"spot": inputs.spot, "vol_forecast": inputs.vol_forecast, "sentiment": inputs.sentiment}
    sources = [{"slug": slug, "title": title} for slug, title, _c in inputs.content_excerpts]
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_succeeded(
            session, note_id, summary=graph.note_markdown, signals=signals, sources=sources,
            model=graph.model, prompt_tokens=graph.prompt_tokens,
            completion_tokens=graph.completion_tokens, cost_usd=graph.cost_usd)
    return {"status": "succeeded"}


async def _fail(sessionmaker, tenant_id, note_id, code: str, exc: Exception) -> dict:
    log.warning("research job %s failed: %s (%s)", note_id, code, exc)
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_failed(session, note_id, code)
    return {"status": "failed", "code": code}
