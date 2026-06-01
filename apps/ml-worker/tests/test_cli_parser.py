from __future__ import annotations


def test_sentiment_subcommand_parses():
    from ml_worker.cli import build_parser

    args = build_parser().parse_args(["sentiment", "--market", "US", "--lookback-hours", "72"])
    assert args.cmd == "sentiment" and args.market == "US" and args.lookback_hours == 72
