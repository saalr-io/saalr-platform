from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker
from saalr_core.marketdata.aggregates import MassiveAggregatesProvider
from saalr_core.marketdata.provider import ProviderError

from . import repo, service


async def _with_session(fn: Callable[[AsyncSession, object], Awaitable[None]]) -> None:
    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    try:
        sm = create_sessionmaker(engine)
        async with sm() as session:
            async with session.begin():
                await fn(session, settings)
    finally:
        await engine.dispose()


def _provider(settings) -> MassiveAggregatesProvider:
    return MassiveAggregatesProvider(settings.massive_api_key)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ingest_worker", description="Saalr market-data ingestion")
    sub = p.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add-instrument", help="add or re-activate a symbol")
    add.add_argument("symbol")
    add.add_argument("--market", default="US")
    add.add_argument("--name", default=None)

    lst = sub.add_parser("list-instruments", help="list active instruments")
    lst.add_argument("--market", default=None)

    bf = sub.add_parser("backfill", help="backfill daily bars for a date range")
    bf.add_argument("--start", required=True)
    bf.add_argument("--end", required=True)
    bf.add_argument("--symbol", default=None)
    bf.add_argument("--market", default="US")

    sub.add_parser("run", help="incremental: append new daily bars for all active instruments")
    return p


async def _cmd_add(args, session, settings) -> None:
    await repo.add_instrument(session, args.symbol.upper(), args.market, args.name)
    print(f"added {args.symbol.upper()} ({args.market})")


async def _cmd_list(args, session, settings) -> None:
    rows = await repo.list_active_instruments(session, args.market)
    for i in rows:
        print(f"{i.symbol}\t{i.market}\t{i.name or ''}")
    print(f"{len(rows)} active")


async def _cmd_backfill(args, session, settings) -> None:
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    provider = _provider(settings)
    symbols = (
        [(args.symbol.upper(), args.market)]
        if args.symbol
        else [(i.symbol, i.market) for i in await repo.list_active_instruments(session)]
    )
    for sym, mkt in symbols:
        try:
            n = await service.backfill_symbol(session, provider, sym, mkt, start, end)
            print(f"{sym}: {n} bars")
        except ProviderError as exc:
            print(f"{sym}: FAILED {exc}")


async def _cmd_run(args, session, settings) -> None:
    provider = _provider(settings)
    counts = await service.run_incremental(session, provider, settings.bars_backfill_default_days)
    for sym, n in counts.items():
        print(f"{sym}: +{n} bars")


_DISPATCH = {
    "add-instrument": _cmd_add,
    "list-instruments": _cmd_list,
    "backfill": _cmd_backfill,
    "run": _cmd_run,
}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handler = _DISPATCH[args.cmd]
    asyncio.run(_with_session(lambda session, settings: handler(args, session, settings)))
