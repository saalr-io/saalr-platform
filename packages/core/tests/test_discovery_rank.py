from saalr_core.discovery.filters import apply_filters, Filters
from saalr_core.discovery.rank import rank_and_truncate


def _sc(key, ev, max_loss, pop, min_oi=100):
    return {
        "template_key": key,
        "metrics": {"ev": ev, "max_loss": max_loss, "ev_to_risk": (ev / max_loss if max_loss else None),
                    "pop": pop, "min_open_interest": min_oi, "max_bid_ask_pct": 0.05},
    }


def test_filters_apply_to_full_set_before_truncation():
    cands = [_sc("a", 40, 400, 0.7), _sc("b", 5, 400, 0.4), _sc("c", 31, 400, 0.74)]
    f = Filters(min_pop=0.5, max_loss=1000, min_open_interest=10, max_bid_ask_pct=0.10)
    kept = apply_filters(cands, f)
    assert {c["template_key"] for c in kept} == {"a", "c"}   # b fails min_pop


def test_rank_is_deterministic_and_orders_by_score():
    cands = [_sc("a", 40, 400, 0.7), _sc("c", 31, 400, 0.74)]
    r1 = rank_and_truncate(cands, profile="ev_to_risk", top_n=10)
    r2 = rank_and_truncate(cands, profile="ev_to_risk", top_n=10)
    assert [c["template_key"] for c in r1] == ["a", "c"]      # 0.10 > 0.0775
    assert r1 == r2                                            # RANK-4 determinism


def test_stability_under_irrelevant_alternative():
    base = [_sc("a", 40, 400, 0.7), _sc("c", 31, 400, 0.74)]
    f = Filters(min_pop=0.5, max_loss=1000, min_open_interest=10, max_bid_ask_pct=0.10)
    irrelevant = _sc("z", 5, 400, 0.4)   # fails min_pop
    r_without = rank_and_truncate(apply_filters(base, f), "ev_to_risk", 10)
    r_with = rank_and_truncate(apply_filters([*base, irrelevant], f), "ev_to_risk", 10)
    assert [c["template_key"] for c in r_without] == [c["template_key"] for c in r_with]  # RANK-5
