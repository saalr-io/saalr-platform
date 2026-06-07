from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timezone

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker
from saalr_core.marketdata.aggregates import MassiveAggregatesProvider
from saalr_core.marketdata.provider import ProviderError

from . import repo, service


async def _run(fn) -> None:
    """Build an engine + sessionmaker, hand them to the command, then dispose.

    Commands own their own transaction boundaries — each symbol is committed in
    its own short transaction, so a failure on one symbol never rolls back the
    work already persisted for earlier symbols (long backfills are resumable).
    """
    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    try:
        await fn(create_sessionmaker(engine), settings)
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


async def _cmd_add(args, sm, settings) -> None:
    async with sm() as session:
        async with session.begin():
            await repo.add_instrument(session, args.symbol.upper(), args.market, args.name)
    print(f"added {args.symbol.upper()} ({args.market})")


async def _cmd_list(args, sm, settings) -> None:
    async with sm() as session:
        rows = await repo.list_active_instruments(session, args.market)
    for i in rows:
        print(f"{i.symbol}\t{i.market}\t{i.name or ''}")
    print(f"{len(rows)} active")


async def _cmd_backfill(args, sm, settings) -> None:
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    provider = _provider(settings)
    if args.symbol:
        symbols = [(args.symbol.upper(), args.market)]
    else:
        async with sm() as session:
            symbols = [(i.symbol, i.market) for i in await repo.list_active_instruments(session)]
    for sym, mkt in symbols:
        try:
            async with sm() as session, session.begin():
                n = await service.backfill_symbol(session, provider, sym, mkt, start, end)
            print(f"{sym}: {n} bars")
        except ProviderError as exc:
            print(f"{sym}: FAILED {exc}")


async def _cmd_run(args, sm, settings) -> None:
    provider = _provider(settings)
    today = datetime.now(timezone.utc).date()
    async with sm() as session:
        instruments = await repo.list_active_instruments(session)
    for inst in instruments:
        try:
            async with sm() as session, session.begin():
                n = await service.incremental_symbol(
                    session, provider, inst.symbol, inst.market, settings.bars_backfill_default_days, today
                )
            print(f"{inst.symbol}: +{n} bars")
        except ProviderError as exc:
            print(f"{inst.symbol}: FAILED {exc}")


_DISPATCH = {
    "add-instrument": _cmd_add,
    "list-instruments": _cmd_list,
    "backfill": _cmd_backfill,
    "run": _cmd_run,
}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    handler = _DISPATCH[args.cmd]
    asyncio.run(_run(lambda sm, settings: handler(args, sm, settings)))
