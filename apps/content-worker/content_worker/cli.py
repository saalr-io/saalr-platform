from __future__ import annotations

import argparse
import asyncio


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="content_worker", description="Saalr content index worker")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reindex", help="rebuild the OptionsAcademy embeddings index")
    return p


async def _cmd_reindex(args) -> None:
    from saalr_content.loader import load_catalog
    from saalr_core.config import get_settings
    from saalr_core.db.session import create_engine, create_sessionmaker
    from saalr_core.rag.embeddings import make_embedding_provider

    from .reindex import run_reindex

    settings = get_settings()
    provider = make_embedding_provider(settings)
    if provider is None:
        raise SystemExit("no embedding provider configured (set OPENAI_API_KEY)")
    engine = create_engine(settings.app_database_url)
    sm = create_sessionmaker(engine)
    try:
        n = await run_reindex(sm, provider, load_catalog(), model=provider.model_name)
        print(f"reindexed {n} chunks with model {provider.model_name}")
    finally:
        await engine.dispose()


_DISPATCH = {"reindex": _cmd_reindex}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    asyncio.run(_DISPATCH[args.cmd](args))
