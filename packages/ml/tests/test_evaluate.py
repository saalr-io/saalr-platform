# packages/ml/tests/test_evaluate.py
import numpy as np

from saalr_ml.baseline import hv21
from saalr_ml.evaluate import WalkForward, walk_forward


def test_hv21_matches_hand_calc():
    rng = np.random.default_rng(1)
    returns = rng.standard_normal(100) * 1.0  # scaled returns
    expected = float(np.std(returns[-21:]) * np.sqrt(252))
    assert abs(hv21(returns) - expected) < 1e-9


def test_walk_forward_prefers_garch_on_volatility_clustering():
    # strong GARCH clustering -> GARCH should beat a flat 21-day window
    from saalr_ml.tests_helpers import simulate_garch  # see note below
    r = simulate_garch(2000, omega=0.05, alpha=0.12, beta=0.86, seed=21)
    wf = walk_forward(r, holdout_days=60)
    assert isinstance(wf, WalkForward)
    assert wf.primary == "garch"
    assert wf.garch_mae < wf.hv21_mae


def test_walk_forward_ties_or_baseline_on_iid():
    rng = np.random.default_rng(2)
    r = rng.standard_normal(1500) * 1.0   # near-constant vol, no clustering
    wf = walk_forward(r, holdout_days=60)
    # GARCH has no clustering to exploit; it must NOT spuriously dominate
    assert wf.primary in ("hv21", "garch", "har")
    assert wf.hv21_mae <= wf.garch_mae * 1.5   # baseline is competitive on IID data


def test_walk_forward_reports_har_and_can_pick_it():
    from saalr_ml.evaluate import walk_forward
    rng = np.random.default_rng(7)
    r = rng.standard_normal(1500) * 1.0
    wf = walk_forward(r, holdout_days=60)
    assert hasattr(wf, "har_mae") and np.isfinite(wf.har_mae)
    assert wf.primary in ("garch", "hv21", "har")
    # primary is the lowest-MAE of the three
    best = min(("garch", wf.garch_mae), ("hv21", wf.hv21_mae), ("har", wf.har_mae), key=lambda t: t[1])
    assert wf.primary == best[0]
