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

    Runs in ONE tenant transaction. On a backtest-logic failure we persist
    status='failed' and return — we do NOT re-raise, because tenant_session would
    otherwise roll back the very failure row we just wrote."""
    async with tenant_session(sessionmaker, tenant_id) as session:
        bt = await repo.get_backtest(session, backtest_id)
        if bt is None:
            raise ValueError(f"backtest {backtest_id} not found")
        await repo.mark_running(session, backtest_id)
        try:
            strat = await repo.get_strategy(session, bt.strategy_id)
            if strat is None:
                raise ValueError("strategy not found")
            config = config_from_json(strat.config_json)
            params = _params_from(bt.config_snapshot.get("params", {}), bt.start_date, bt.end_date)
            closes = await repo.load_underlying_closes(
                session, config.underlying, strat.market, bt.start_date, bt.end_date, params.vol_lookback
            )
            sim_dates = sorted(d for d in closes if bt.start_date <= d <= bt.end_date)
            if len(sim_dates) < 2:
                raise ValueError(f"insufficient bars for {config.underlying} in [{bt.start_date}, {bt.end_date}]")
            ref_date = sim_dates[0]
            template = RelativeTemplate.from_config(config, ref_spot=closes[ref_date], ref_date=ref_date)
            result = run_backtest_engine(closes, template, params)
            await repo.save_result(session, backtest_id, result, "succeeded")
            return {"status": "succeeded", "result": result}
        except Exception as exc:  # noqa: BLE001 - persisted as a failed run, then returned
            await repo.save_result(session, backtest_id, None, "failed", str(exc))
            return {"status": "failed", "error": str(exc)}


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
