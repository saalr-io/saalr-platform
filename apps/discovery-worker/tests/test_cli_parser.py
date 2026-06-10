from discovery_worker.cli import build_parser


def test_discover_subcommand_parses():
    ns = build_parser().parse_args(["discover", "--underlying", "AAPL", "--market", "US",
                                    "--tenant", "11111111-1111-1111-1111-111111111111"])
    assert ns.cmd == "discover" and ns.underlying == "AAPL"


def test_consume_subcommand_parses():
    ns = build_parser().parse_args(["consume", "--consumer", "w1"])
    assert ns.cmd == "consume" and ns.consumer == "w1"
