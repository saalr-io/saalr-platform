from datetime import date

from saalr_core.discovery.generate import enumerate_candidates, atm_strike, OPTION_ONLY_TEMPLATES
from saalr_core.discovery.types import CleanChain, CleanContract
from saalr_core.strategies.types import OptionType, OptionLeg


def _chain(strikes, expiry="2026-07-10", spot=100.0):
    contracts = []
    for k in strikes:
        for kind in (OptionType.CALL, OptionType.PUT):
            contracts.append(CleanContract(expiry, float(k), kind, mid=2.0, iv=0.3,
                                            volume=10, open_interest=100))
    return CleanChain("AAPL", "2026-06-10T20:00:00Z", spot, 0.0, tuple(contracts))


def test_atm_strike_picks_nearest_listed():
    assert atm_strike([90, 95, 100, 105, 110], 101.0) == 100.0
    assert atm_strike([90, 95, 100, 105, 110], 103.0) == 105.0


def test_bull_put_spread_candidates_use_only_listed_strikes():
    chain = _chain(range(80, 121, 5))  # 80,85,...,120
    cands = enumerate_candidates(
        chain, families=["bull_put_spread"], dte_min=0, dte_max=60,
        strike_window=5, as_of_date=date(2026, 6, 10),
    )
    assert cands, "expected at least one bull put spread"
    listed = set(chain.strikes_for_expiry("2026-07-10"))
    for cand in cands:
        assert cand.template_key == "bull_put_spread"
        for leg in cand.config.legs:
            assert isinstance(leg, OptionLeg)
            assert leg.strike in listed            # STRUCT-1: no synthetic strikes
            assert leg.entry_price == 2.0          # mid overlaid from the chain


def test_degenerate_zero_width_rejected():
    # width 0 would create a zero-width spread (STRUCT-4) -> never emitted
    chain = _chain(range(80, 121, 5))
    cands = enumerate_candidates(
        chain, families=["bull_put_spread"], dte_min=0, dte_max=60,
        strike_window=5, as_of_date=date(2026, 6, 10),
    )
    for cand in cands:
        ks = sorted({leg.strike for leg in cand.config.legs})
        assert len(ks) >= 2                        # distinct strikes only


def test_equity_templates_skipped():
    assert "covered_call" not in OPTION_ONLY_TEMPLATES
    assert "bull_put_spread" in OPTION_ONLY_TEMPLATES
