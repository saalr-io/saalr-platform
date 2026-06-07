from __future__ import annotations

from datetime import datetime, timezone

from saalr_api.market.oi_change import WINDOWS, elapsed_label, pick_baseline_ts


def _ts(h, m=0):
    return datetime(2026, 5, 30, h, m, tzinfo=timezone.utc)


def test_windows_order():
    assert WINDOWS == ["day", "1h", "3h", "4h"]


def test_no_earlier_snapshot_returns_none():
    as_of = _ts(14, 30)
    assert pick_baseline_ts([as_of], as_of, "1h") is None
    assert pick_baseline_ts([], as_of, "day") is None


def test_1h_picks_nearest_earlier_to_target():
    as_of = _ts(14, 30)               # target for 1h == 13:30
    snaps = [_ts(10), _ts(13, 25), _ts(14, 30)]
    assert pick_baseline_ts(snaps, as_of, "1h") == _ts(13, 25)


def test_3h_picks_nearest_earlier_to_target():
    as_of = _ts(14, 30)               # target for 3h == 11:30
    snaps = [_ts(10), _ts(12), _ts(14, 30)]
    # 12:00 is 30m from target; 10:00 is 90m — pick 12:00
    assert pick_baseline_ts(snaps, as_of, "3h") == _ts(12)


def test_day_picks_earliest_same_day_before_as_of():
    as_of = _ts(14, 30)
    snaps = [_ts(9, 30), _ts(11), _ts(14, 30)]
    assert pick_baseline_ts(snaps, as_of, "day") == _ts(9, 30)


def test_day_ignores_prior_calendar_day():
    as_of = _ts(14, 30)
    prior_day = datetime(2026, 5, 29, 15, tzinfo=timezone.utc)
    assert pick_baseline_ts([prior_day, as_of], as_of, "day") is None


def test_elapsed_label_formats():
    as_of = _ts(14, 30)
    assert elapsed_label(as_of, _ts(11, 23)) == "~3h7m"
    assert elapsed_label(as_of, _ts(13, 30)) == "~1h"
    assert elapsed_label(as_of, _ts(13, 33)) == "~57m"
