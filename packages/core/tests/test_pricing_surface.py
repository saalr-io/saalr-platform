from datetime import date

from saalr_core.pricing.surface import build_surface
from saalr_core.pricing.types import ContractGreeks, Greeks, OptionKind


def _cg(expiry, strike, kind, iv):
    g = Greeks(price=1.0, delta=0.5, gamma=0.0, theta=0.0, vega=0.0, rho=0.0, iv=iv)
    return ContractGreeks(
        expiry=expiry, strike=strike, kind=kind, bid=1.0, ask=1.1, last=1.05,
        volume=10, open_interest=20, ours=g, vendor_iv=iv, vendor_delta=None,
        vendor_gamma=None, vendor_theta=None, vendor_vega=None,
    )


def test_build_surface_groups_and_sorts():
    contracts = [
        _cg("2026-06-21", 190, OptionKind.CALL, 0.24),
        _cg("2026-06-21", 180, OptionKind.CALL, 0.26),
        _cg("2026-06-21", 180, OptionKind.PUT, 0.27),
        _cg("2026-07-19", 185, OptionKind.CALL, 0.22),
    ]
    out = build_surface(contracts, as_of=date(2026, 5, 30))
    assert [e["expiry"] for e in out] == ["2026-06-21", "2026-07-19"]
    june = out[0]
    assert june["days_to_expiry"] == 22
    assert [s["strike"] for s in june["strikes"]] == [180, 190]
    assert june["strikes"][0]["iv_call"] == 0.26
    assert june["strikes"][0]["iv_put"] == 0.27
    assert june["strikes"][1]["iv_put"] is None
