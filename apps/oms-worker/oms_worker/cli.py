from __future__ import annotations

import argparse
import asyncio

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="oms_worker", description="Saalr OMS reconciliation worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reconcile", help="poll Alpaca and reconcile open orders")
    r.add_argument("--interval", type=float, default=5.0)
    r.add_argument("--once", action="store_true")
    return p


async def _cmd_reconcile(args) -> None:
    from .reconcile import run_reconcile  # lazy: keeps build_parser import-light

    settings = get_settings()
    app_engine = create_engine(settings.app_database_url)
    admin_engine = create_engine(settings.admin_database_url)
    app_sm = create_sessionmaker(app_engine)
    try:
        await run_reconcile(app_sm, admin_engine, once=args.once, interval=args.interval)
    finally:
        await app_engine.dispose()
        await admin_engine.dispose()


_DISPATCH = {"reconcile": _cmd_reconcile}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
