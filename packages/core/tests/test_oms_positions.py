from decimal import Decimal

from saalr_core.oms.positions import net_position


def test_open_and_add_weighted_average():
    assert net_position(0, Decimal(0), 10, Decimal("50")) == (10, Decimal("50"))
    assert net_position(10, Decimal("50"), 10, Decimal("60")) == (20, Decimal("55"))


def test_partial_close_keeps_average():
    assert net_position(10, Decimal("50"), -4, Decimal("60")) == (6, Decimal("50"))


def test_close_to_zero_is_flat():
    assert net_position(10, Decimal("50"), -10, Decimal("60")) == (0, Decimal(0))


def test_flip_through_zero_resets_basis_to_fill():
    assert net_position(5, Decimal("50"), -8, Decimal("60")) == (-3, Decimal("60"))


def test_short_then_add_short():
    assert net_position(-5, Decimal("50"), -5, Decimal("60")) == (-10, Decimal("55"))
