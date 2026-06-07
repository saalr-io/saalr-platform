import pytest

from oms_worker.cli import build_parser


def test_parser_reconcile_defaults():
    args = build_parser().parse_args(["reconcile"])
    assert args.cmd == "reconcile" and args.once is False and args.interval == 5.0


def test_parser_once_flag():
    args = build_parser().parse_args(["reconcile", "--once"])
    assert args.once is True


def test_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
