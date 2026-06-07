import json
import pathlib

from saalr_core.marketdata.rates import latest_observation, build_curve

FIX = pathlib.Path(__file__).parent / "fixtures"


def test_latest_observation_skips_placeholders():
    data = json.loads((FIX / "fred_dgs3mo.json").read_text())
    obs_date, value = latest_observation(data)
    assert obs_date == "2026-05-28"
    assert value == 0.0510  # percent -> decimal


def test_build_curve_sorts_and_converts():
    raw = {"DGS1MO": ("2026-05-28", 0.0500), "DGS1": ("2026-05-28", 0.0460)}
    curve = build_curve(raw)
    assert curve.curve_date == "2026-05-28"
    assert curve.points[0][0] < curve.points[1][0]
    assert curve.points[0] == (1 / 12, 0.05)
