from __future__ import annotations

from .cli import build_parser


def main() -> None:
    args = build_parser().parse_args()
    # Provider wiring (redis, sessionmaker, MarketService, rate_for) mirrors
    # backtest-worker.__main__ + apps/api/saalr_api/main.py; construct from env and dispatch
    # to consumer.run_consumer / service.run_discovery_job. Kept thin; not unit-tested.
    raise SystemExit(f"cmd={args.cmd}: wire providers in deployment (see backtest-worker.__main__)")


if __name__ == "__main__":
    main()
