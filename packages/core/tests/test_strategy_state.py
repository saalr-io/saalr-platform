import pytest

from saalr_core.strategies.state import (
    IllegalTransition,
    StrategyState,
    transition,
)


def test_valid_draft_to_backtested():
    assert transition(StrategyState.DRAFT, StrategyState.BACKTESTED) is StrategyState.BACKTESTED


def test_draft_to_archived_ok():
    assert transition(StrategyState.DRAFT, StrategyState.ARCHIVED) is StrategyState.ARCHIVED


def test_illegal_draft_to_live_raises():
    with pytest.raises(IllegalTransition):
        transition(StrategyState.DRAFT, StrategyState.LIVE)


def test_archived_is_terminal():
    with pytest.raises(IllegalTransition):
        transition(StrategyState.ARCHIVED, StrategyState.DRAFT)


def test_paper_to_live_is_defined():
    assert transition(StrategyState.PAPER, StrategyState.LIVE) is StrategyState.LIVE
