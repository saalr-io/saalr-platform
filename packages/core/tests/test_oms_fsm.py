import pytest

from saalr_core.oms.fsm import IllegalOrderTransition, transition
from saalr_core.oms.types import OrderStatus as S


def test_legal_transitions():
    assert transition(S.PENDING, S.SUBMITTED) == S.SUBMITTED
    assert transition(S.SUBMITTED, S.PARTIAL) == S.PARTIAL
    assert transition(S.SUBMITTED, S.FILLED) == S.FILLED
    assert transition(S.PARTIAL, S.FILLED) == S.FILLED
    assert transition(S.PENDING, S.REJECTED) == S.REJECTED
    assert transition(S.SUBMITTED, S.CANCELLED) == S.CANCELLED


@pytest.mark.parametrize("a,b", [
    (S.PENDING, S.FILLED),       # must go through submitted
    (S.FILLED, S.SUBMITTED),     # terminal
    (S.CANCELLED, S.SUBMITTED),  # terminal
    (S.REJECTED, S.FILLED),      # terminal
    (S.PARTIAL, S.SUBMITTED),    # cannot go back
])
def test_illegal_transitions_raise(a, b):
    with pytest.raises(IllegalOrderTransition):
        transition(a, b)
