from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from saalr_core.backtest.engine import ENGINE_VERSION, BacktestParams, run_backtest_engine
from saalr_core.backtest.template import RelativeTemplate
from saalr_core.db.session import tenant_session
from saalr_core.strategies.serde import config_from_json

from . import repo


def _params_from(bt_params: dict, start: date, end: date) -> BacktestParams:
    return BacktestParams(
        start=start,
        end=end,
        initial_capital=float(bt_params.get("initial_capital", 100_000.0)),
        rate=float(bt_params.get("rate", 0.04)),
        vol_lookback=int(bt_params.get("vol_lookback", 20)),
        include_costs=bool(bt_params.get("include_costs", True)),
        commission_per_contract=float(bt_params.get("commission_per_contract", 0.65)),
        slippage_per_contract=float(bt_params.get("slippage_per_contract", 0.50)),
        strike_increment=float(bt_params.get("strike_increment", 1.0)),
    )


async def run_backtest(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: UUID, backtest_id: UUID
) -> dict:
    """Run an existing (queued) backtest by id, persisting status + metrics.

    Three phases, each isolating its failure mode:
      1. Load inputs (one tenant tx): mark running, read strategy + bars.
      2. Pure compute (no DB): build the template, run the engine.
      3. Persist the outcome (its own tenant tx): succeeded or failed.

    The phases are deliberately separate so the failure write in phase 3 runs in a
    FRESH transaction — a DB error while reading inputs (phase 1) cannot poison the
    transaction we use to record `status='failed'`. We never re-raise a
    backtest-logic failure; it is persisted and returned as `status='failed'`."""
    # Phase 1 — load inputs.
    try:
        async with tenant_session(sessionmaker, tenant_id) as session:
            bt = await repo.get_backtest(session, backtest_id)
            if bt is None:
                raise ValueError(f"backtest {backtest_id} not found")
            await repo.mark_running(session, backtest_id)
            strat = await repo.get_strategy(session, bt.strategy_id)
            if strat is None:
                raise ValueError("strategy not found")
            start_date, end_date = bt.start_date, bt.end_date
            config = config_from_json(strat.config_json)
            params = _params_from(bt.config_snapshot.get("params", {}), start_date, end_date)
            closes = await repo.load_underlying_closes(
                session, config.underlying, strat.market, start_date, end_date, params.vol_lookback
            )
    except Exception as exc:  # noqa: BLE001 - persisted as a failed run in a fresh tx, then returned
        return await _persist_failed(sessionmaker, tenant_id, backtest_id, str(exc))

    # Phase 2 — pure compute (no DB; cannot poison a transaction).
    try:
        sim_dates = sorted(d for d in closes if start_date <= d <= end_date)
        if len(sim_dates) < 2:
            raise ValueError(f"insufficient bars for {config.underlying} in [{start_date}, {end_date}]")
        ref_date = sim_dates[0]
        template = RelativeTemplate.from_config(config, ref_spot=closes[ref_date], ref_date=ref_date)
        result = run_backtest_engine(closes, template, params)
    except Exception as exc:  # noqa: BLE001 - persisted as a failed run, then returned
        return await _persist_failed(sessionmaker, tenant_id, backtest_id, str(exc))

    # Phase 3 — persist success.
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_result(session, backtest_id, result, "succeeded")
    return {"status": "succeeded", "result": result}


async def _persist_failed(
    sessionmaker: async_sessionmaker[AsyncSession], tenant_id: UUID, backtest_id: UUID, error: str
) -> dict:
    """Record a failed backtest in its own fresh transaction (best-effort)."""
    async with tenant_session(sessionmaker, tenant_id) as session:
        await repo.save_result(session, backtest_id, None, "failed", error)
    return {"status": "failed", "error": error}


async def create_and_run(
    sessionmaker: async_sessionmaker[AsyncSession],
    tenant_id: UUID,
    strategy_id: UUID,
    params: dict,
) -> tuple[UUID, dict]:
    """Create a queued backtest row (its own transaction), then run it. Mirrors how
    8b's API will create the row and the queue worker will run it later."""
    start = date.fromisoformat(params["start"])
    end = date.fromisoformat(params["end"])
    async with tenant_session(sessionmaker, tenant_id) as session:
        strat = await repo.get_strategy(session, strategy_id)
        if strat is None:
            raise ValueError("strategy not found")
        snapshot = {"config": strat.config_json, "params": params, "engine_version": ENGINE_VERSION}
        backtest_id = await repo.create_backtest(session, tenant_id, strategy_id, start, end, snapshot)
    outcome = await run_backtest(sessionmaker, tenant_id, backtest_id)
    return backtest_id, outcome
