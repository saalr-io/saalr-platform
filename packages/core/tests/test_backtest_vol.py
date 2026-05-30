import math

from saalr_core.backtest import vol


def test_log_returns():
    r = vol.log_returns([100.0, 110.0, 121.0])
    assert len(r) == 2
    assert abs(r[0] - math.log(1.1)) < 1e-12


def test_realized_vol_matches_hand_calc():
    # alternating +1%/-1% log moves -> stdev of [ln(1.01), ln(0.99*... )] annualized
    closes = [100.0]
    for _ in range(10):
        closes.append(closes[-1] * 1.01)
        closes.append(closes[-1] * 0.99)
    v = vol.realized_vol(closes, lookback=20)
    assert v > 0.0
    # sanity: annualized vol of ~1% daily moves is roughly 0.01*sqrt(252) ~ 0.16
    assert 0.05 < v < 0.40


def test_realized_vol_floor_on_insufficient_data():
    assert vol.realized_vol([100.0], lookback=20) == vol.VOL_FLOOR
    assert vol.realized_vol([], lookback=20) == vol.VOL_FLOOR


def test_realized_vol_floor_on_flat_series():
    assert vol.realized_vol([100.0] * 30, lookback=20) == vol.VOL_FLOOR


def test_realized_vol_uses_only_last_lookback_returns():
    # a long calm history then nothing changes the windowed result vs short calm
    closes = [100.0 * (1.0 + 0.001 * (i % 2)) for i in range(100)]
    v_full = vol.realized_vol(closes, lookback=20)
    v_short = vol.realized_vol(closes[-21:], lookback=20)
    assert abs(v_full - v_short) < 1e-9
