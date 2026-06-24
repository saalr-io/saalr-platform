from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="discovery-worker")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="create + run one discovery synchronously")
    d.add_argument("--underlying", required=True)
    d.add_argument("--market", default="US")
    d.add_argument("--tenant", required=True)
    d.add_argument("--profile", default="ev_to_risk")
    d.add_argument("--top-n", type=int, default=10, dest="top_n")

    c = sub.add_parser("consume", help="run the queue consumer loop")
    c.add_argument("--consumer", required=True)
    c.add_argument("--once", action="store_true")
    return p
