from __future__ import annotations

from datetime import datetime, timedelta

# Display + computation order. "day" is special-cased (since-start-of-day);
# the rest are fixed look-back deltas.
WINDOWS: list[str] = ["day", "1h", "3h", "4h"]
_DELTAS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "3h": timedelta(hours=3),
    "4h": timedelta(hours=4),
}


def pick_baseline_ts(
    snapshot_ts: list[datetime], as_of: datetime, window: str
) -> datetime | None:
    """Pick the baseline snapshot timestamp for a window, or None if unavailable.

    Only snapshots strictly earlier than `as_of` are eligible. For "day" the
    baseline is the earliest snapshot on the same calendar day as `as_of`; for
    the look-back windows it is the snapshot closest to (as_of - delta)."""
    earlier = [t for t in snapshot_ts if t < as_of]
    if not earlier:
        return None
    if window == "day":
        sod = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        same_day = [t for t in earlier if t >= sod]
        return min(same_day) if same_day else None
    target = as_of - _DELTAS[window]
    return min(earlier, key=lambda t: abs((t - target).total_seconds()))


def elapsed_label(as_of: datetime, baseline_ts: datetime) -> str:
    """Compact human label for how long ago the baseline was, e.g. '~3h7m'."""
    secs = max(0, int((as_of - baseline_ts).total_seconds()))
    minutes = secs // 60
    h, m = divmod(minutes, 60)
    if h and m:
        return f"~{h}h{m}m"
    if h:
        return f"~{h}h"
    return f"~{m}m"
