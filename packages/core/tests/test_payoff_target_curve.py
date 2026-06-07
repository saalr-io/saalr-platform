from __future__ import annotations

from datetime import date

from saalr_core.strategies.payoff import spot_grid, target_date_curve
from saalr_core.strategies.types import OptionLeg, OptionType, Side


def test_target_curve_handles_zero_spot_grid_point():
    """The target-date (BSM-priced) curve evaluates over a spot grid whose first point is 0.0.
    With a valid IV, BSM at spot=0 would hit log(0/strike) -> ValueError; the curve must instead
    fall back to intrinsic at non-positive spots (a long call is worthless at spot 0)."""
    leg = OptionLeg(OptionType.CALL, Side.BUY, 100.0, "2026-12-18", 1, 6.0)
    grid = spot_grid([leg], 100.0)
    assert 0.0 in grid  # the grid genuinely contains the s=0 point that broke BSM

    curve = target_date_curve([leg], grid, date(2026, 9, 18), 0.04, 0.0, {0: 0.55})

    s0_pnl = next(p for s, p in curve if s == 0.0)
    # long call at spot 0 -> intrinsic 0, so pnl is just the paid premium: (0 - 6.0) * 100 * 1
    assert s0_pnl == (0.0 - 6.0) * 100 * 1


def test_target_curve_put_intrinsic_at_zero_spot():
    leg = OptionLeg(OptionType.PUT, Side.BUY, 100.0, "2026-12-18", 1, 4.0)
    grid = spot_grid([leg], 100.0)
    curve = target_date_curve([leg], grid, date(2026, 9, 18), 0.04, 0.0, {0: 0.55})
    s0_pnl = next(p for s, p in curve if s == 0.0)
    # long put at spot 0 -> intrinsic = strike (100), pnl = (100 - 4.0) * 100 * 1
    assert s0_pnl == (100.0 - 4.0) * 100 * 1
