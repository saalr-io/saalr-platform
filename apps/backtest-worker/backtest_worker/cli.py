from __future__ import annotations

import argparse
import asyncio
import json
from uuid import UUID

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker

from . import service


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="backtest_worker", description="Saalr backtest worker")
    sub = p.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", help="create + run a backtest for a strategy")
    bt.add_argument("--strategy", required=True)
    bt.add_argument("--tenant", required=True)
    bt.add_argument("--start", required=True)
    bt.add_argument("--end", required=True)
    bt.add_argument("--capital", type=float, default=100_000.0)
    bt.add_argument("--rate", type=float, default=0.04)
    bt.add_argument("--vol-lookback", type=int, default=20, dest="vol_lookback")
    bt.add_argument("--no-costs", action="store_true", dest="no_costs")

    rn = sub.add_parser("run", help="run an existing (queued) backtest by id")
    rn.add_argument("--tenant", required=True)
    rn.add_argument("backtest_id")
    return p


async def _with_sessionmaker(fn):
    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    try:
        return await fn(create_sessionmaker(engine))
    finally:
        await engine.dispose()


async def _cmd_backtest(args) -> None:
    params = {
        "start": args.start,
        "end": args.end,
        "initial_capital": args.capital,
        "rate": args.rate,
        "vol_lookback": args.vol_lookback,
        "include_costs": not args.no_costs,
    }

    async def go(sm):
        return await service.create_and_run(sm, UUID(args.tenant), UUID(args.strategy), params)

    bt_id, outcome = await _with_sessionmaker(go)
    print(f"backtest {bt_id}: {outcome['status']}")
    if outcome["status"] == "succeeded":
        print(json.dumps(outcome["result"]["metrics"], indent=2))
    else:
        print(outcome.get("error", ""))


async def _cmd_run(args) -> None:
    async def go(sm):
        return await service.run_backtest(sm, UUID(args.tenant), UUID(args.backtest_id))

    outcome = await _with_sessionmaker(go)
    print(f"backtest {args.backtest_id}: {outcome['status']}")


_DISPATCH = {"backtest": _cmd_backtest, "run": _cmd_run}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
