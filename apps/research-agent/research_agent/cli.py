from __future__ import annotations

import argparse
import asyncio
import socket

import redis.asyncio as aioredis

from saalr_core.config import get_settings
from saalr_core.db.session import create_engine, create_sessionmaker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="research_agent", description="Saalr research-agent worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    cn = sub.add_parser("consume", help="run the Redis-Streams research consume loop")
    cn.add_argument("--block-ms", type=int, default=5000, dest="block_ms")
    cn.add_argument("--count", type=int, default=10)
    cn.add_argument("--once", action="store_true")
    cn.add_argument("--consumer", default=None)
    return p


async def _cmd_consume(args) -> None:
    # lazy imports keep build_parser light
    from saalr_content.loader import load_catalog
    from saalr_core.llm.cost import monthly_cap
    from saalr_core.llm.gateway import make_chat_gateway
    from saalr_core.rag.embeddings import make_embedding_provider

    from .consumer import run_consumer

    settings = get_settings()
    engine = create_engine(settings.app_database_url)
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    consumer = args.consumer or f"research-{socket.gethostname()}"
    try:
        await run_consumer(
            redis, create_sessionmaker(engine), consumer,
            chat_provider=make_chat_gateway(settings),
            embedding_provider=make_embedding_provider(settings),
            catalog=load_catalog(),
            cap=monthly_cap(settings),
            block_ms=args.block_ms, count=args.count, once=args.once,
        )
    finally:
        await redis.aclose()
        await engine.dispose()


_DISPATCH = {"consume": _cmd_consume}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
