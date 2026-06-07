import pytest

from content_worker.cli import build_parser


def test_parser_reindex():
    args = build_parser().parse_args(["reindex"])
    assert args.cmd == "reindex"


def test_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
