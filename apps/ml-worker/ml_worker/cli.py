from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker
from saalr_core.marketdata.news_factory import build_news_provider
from saalr_core.marketdata.provider import ProviderError
from saalr_core.sentiment import pipeline, repo


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ml_worker", description="Saalr ML worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sentiment", help="refresh news sentiment for active instruments")
    s.add_argument("--market", default=None)
    s.add_argument("--lookback-hours", type=int, default=168, dest="lookback_hours")
    return p


async def _cmd_sentiment(args) -> None:
    from .finbert import FinBertScorer  # lazy: torch/transformers load only here

    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    sm = create_sessionmaker(engine)
    provider = build_news_provider(settings)
    scorer = FinBertScorer()
    now = datetime.now(timezone.utc)
    try:
        async with sm() as s:
            instruments = await repo.list_active_instruments(s, args.market)
        for symbol, market in instruments:
            try:
                async with sm() as s, s.begin():
                    agg = await pipeline.refresh_symbol(
                        s, provider, scorer, symbol, market, now, args.lookback_hours
                    )
                print(f"{symbol}: {agg['label']} {agg['score']:.3f}")
            except ProviderError as exc:
                print(f"{symbol}: FAILED {exc}")
    finally:
        await engine.dispose()


_DISPATCH = {"sentiment": _cmd_sentiment}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
