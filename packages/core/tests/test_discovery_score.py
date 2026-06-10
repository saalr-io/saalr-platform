from saalr_core.discovery.score import SCORE_PROFILES, score_for


def _m(ev, max_loss, pop):
    return {"ev": ev, "max_loss": max_loss, "ev_to_risk": (ev / max_loss if max_loss else None), "pop": pop}


def test_profiles_registered():
    assert set(SCORE_PROFILES) == {"ev_to_risk", "pop", "ev_absolute"}


def test_ev_to_risk_prefers_more_reward_per_risk():
    a = score_for("ev_to_risk", _m(ev=40, max_loss=400, pop=0.7))   # 0.10
    b = score_for("ev_to_risk", _m(ev=31, max_loss=400, pop=0.7))   # 0.0775
    assert a > b


def test_pop_profile_is_risk_guarded_against_tiny_credit_huge_risk():
    # high PoP but terrible ev/risk must not beat a balanced trade (keeps RANK-1)
    risky = score_for("pop", _m(ev=1, max_loss=900, pop=0.95))
    balanced = score_for("pop", _m(ev=31, max_loss=400, pop=0.74))
    assert balanced > risky


def test_unbounded_loss_scores_worst():
    assert score_for("ev_to_risk", _m(ev=50, max_loss=None, pop=0.6)) == float("-inf")
