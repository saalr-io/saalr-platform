from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from saalr_core.db.session import tenant_session
from saalr_core.discovery.gates import clean_quotes
from saalr_core.discovery.pipeline import DiscoveryRequest, run_discovery
from saalr_core.discovery.types import CleanChain, Quote
from saalr_core.strategies.types import OptionType
from saalr_ml.montecarlo import monte_carlo_pop

from . import repo


def _quotes_from_payload(payload: dict) -> list[Quote]:
    out: list[Quote] = []
    for c in payload["contracts"]:
        kind = OptionType.CALL if c["type"] == "CALL" else OptionType.PUT
        iv = (c.get("ours") or {}).get("iv")
        out.append(Quote(expiry=c["expiry"], strike=float(c["strike"]), kind=kind,
                         bid=c.get("bid"), ask=c.get("ask"), iv=iv,
                         volume=c.get("volume"), open_interest=c.get("open_interest")))
    return out


def _clean_chain(payload: dict) -> tuple[CleanChain, list[dict]]:
    clean, dropped = clean_quotes(_quotes_from_payload(payload))
    return (
        CleanChain(underlying=payload["ticker"], as_of=payload["as_of"], spot=payload["spot"],
                   div_yield=payload.get("div_yield", 0.0), contracts=tuple(clean)),
        dropped,
    )


async def run_discovery_job(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: UUID, discovery_id: UUID,
    market_service, rate_for,
) -> dict:
    """Three phases mirroring backtest service: load inputs / pure+MC compute / persist.
    A read error in phase 1 cannot poison the failure write in phase 3 (fresh session)."""
    # Phase 1 — load inputs.
    try:
        async with tenant_session(sessionmaker, tenant_id) as session:
            row = await repo.get_discovery(session, discovery_id)
            if row is None:
                raise ValueError(f"discovery {discovery_id} not found")
            await repo.mark_running(session, discovery_id)
            underlying, market, request = row.underlying, row.market, dict(row.request_json)
            payload = await market_service._computed_chain(session, underlying, market)
            as_of_date = datetime.fromisoformat(payload["as_of"]).date()
            closes = await repo.load_recent_closes(session, underlying, market, as_of_date)
    except Exception as exc:  # noqa: BLE001
        return await _persist_failed(sessionmaker, tenant_id, discovery_id, str(exc))

    # Phase 2 — pure compute (no DB).
    try:
        clean, dropped = _clean_chain(payload)
        req = DiscoveryRequest(
            dte_min=int(request.get("dte_min", 0)), dte_max=int(request.get("dte_max", 60)),
            strike_window=int(request.get("strike_window", 5)),
            profile=request.get("profile", "ev_to_risk"), top_n=int(request.get("top_n", 10)),
            families=request.get("families"), min_pop=request.get("min_pop"),
            max_loss=request.get("max_loss"), min_open_interest=request.get("min_open_interest"),
            max_bid_ask_pct=request.get("max_bid_ask_pct"),
        )
        result = run_discovery(clean, closes, rate_for, monte_carlo_pop, req, as_of_date)
        result_json = {
            "scoring_profile": result.scoring_profile, "regime": result.regime,
            "results": result.results, "baseline": result.baseline,
            "data_quality_report": [*result.data_quality_report, *dropped],
            "disclosure_block_id": result.disclosure_block_id,
        }
    except Exception as exc:  # noqa: BLE001
        return await _persist_failed(sessionmaker, tenant_id, discovery_id, str(exc))

    # Phase 3 — persist success.
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_result(session, discovery_id, result_json, "succeeded", as_of=payload["as_of"])
    return {"status": "succeeded"}


async def _persist_failed(sessionmaker, tenant_id, discovery_id, error: str) -> dict:
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_result(session, discovery_id, None, "failed", error)
    return {"status": "failed", "error": error}
