from __future__ import annotations

from enum import Enum


class StrategyState(str, Enum):
    DRAFT = "draft"
    BACKTESTED = "backtested"
    PAPER = "paper"
    LIVE = "live"
    PAUSED = "paused"
    ARCHIVED = "archived"


VALID_TRANSITIONS: dict[StrategyState, set[StrategyState]] = {
    StrategyState.DRAFT: {StrategyState.BACKTESTED, StrategyState.ARCHIVED},
    StrategyState.BACKTESTED: {StrategyState.DRAFT, StrategyState.PAPER, StrategyState.ARCHIVED},
    StrategyState.PAPER: {StrategyState.LIVE, StrategyState.DRAFT, StrategyState.ARCHIVED},
    StrategyState.LIVE: {StrategyState.PAUSED, StrategyState.ARCHIVED},
    StrategyState.PAUSED: {StrategyState.LIVE, StrategyState.ARCHIVED},
    StrategyState.ARCHIVED: set(),
}


class IllegalTransition(Exception):
    """Raised when a strategy state transition is not permitted by the FSM."""


def transition(current: StrategyState, target: StrategyState) -> StrategyState:
    if target not in VALID_TRANSITIONS[current]:
        raise IllegalTransition(f"{current.value} -> {target.value} is not allowed")
    return target
