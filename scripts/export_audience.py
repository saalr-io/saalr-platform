"""Export the marketing audience to CSV (admin/superuser DB connection).

Usage: ADMIN_DATABASE_URL=... python -m scripts.export_audience --segment verified --out audience.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_FIELDS = ["email", "tier", "verified", "opted_in",
           "has_strategy", "has_traded", "has_backtest", "has_progress"]


def segment_where(segment: str) -> str:
    if segment == "verified":
        return "WHERE email_verified_at IS NOT NULL"
    if segment == "opted-in":
        return "WHERE marketing_opt_in"
    if segment == "engaged":
        return "WHERE has_strategy OR has_traded OR has_backtest OR has_progress"
    return ""  # all


def write_csv(buf, rows: list[dict]) -> None:
    w = csv.DictWriter(buf, fieldnames=_FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)


async def _fetch(url: str, segment: str) -> list[dict]:
    engine = create_async_engine(url)
    try:
        sql = (
            "SELECT email, tier, (email_verified_at IS NOT NULL) AS verified, "
            "marketing_opt_in AS opted_in, has_strategy, has_traded, has_backtest, has_progress "
            f"FROM marketing_audience {segment_where(segment)} ORDER BY created_at DESC"
        )
        async with engine.connect() as conn:
            rows = (await conn.execute(text(sql))).mappings().all()
        return [dict(r) for r in rows]
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="export_audience")
    p.add_argument("--segment", choices=["all", "verified", "engaged", "opted-in"], default="verified")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url:
        raise SystemExit("ADMIN_DATABASE_URL is required")
    rows = asyncio.run(_fetch(url, args.segment))
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            write_csv(f, rows)
        print(f"wrote {len(rows)} rows to {args.out}")
    else:
        write_csv(sys.stdout, rows)


if __name__ == "__main__":
    main()
