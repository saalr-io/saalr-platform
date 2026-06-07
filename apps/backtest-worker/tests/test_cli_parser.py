from backtest_worker.cli import build_parser


def test_backtest_subcommand_parses():
    p = build_parser()
    args = p.parse_args(
        ["backtest", "--strategy", "s-1", "--tenant", "t-1",
         "--start", "2025-01-01", "--end", "2025-06-01", "--no-costs"]
    )
    assert args.cmd == "backtest"
    assert args.strategy == "s-1" and args.tenant == "t-1"
    assert args.start == "2025-01-01" and args.end == "2025-06-01"
    assert args.no_costs is True


def test_run_subcommand_parses():
    p = build_parser()
    args = p.parse_args(["run", "--tenant", "t-1", "bt-9"])
    assert args.cmd == "run" and args.tenant == "t-1" and args.backtest_id == "bt-9"


def test_consume_subcommand_parses():
    from backtest_worker.cli import build_parser

    args = build_parser().parse_args(["consume", "--once", "--block-ms", "100", "--consumer", "c1"])
    assert args.cmd == "consume"
    assert args.once is True and args.block_ms == 100 and args.consumer == "c1"
