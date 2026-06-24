from __future__ import annotations

from collections.abc import Callable

from saalr_core.pricing.greeks import greeks as bsm_greeks
from saalr_core.pricing.types import OptionKind, OptionParams
from saalr_core.strategies import aggregate, payoff, pop
from saalr_core.strategies.types import OptionLeg, OptionType

from .types import Candidate

# mc_pop(legs, spot, t_years, sigma, rate, div_yield, seed) -> {"pop","ev","percentiles",...}
McPop = Callable[..., dict]


def _kind(ot: OptionType) -> OptionKind:
    return OptionKind.CALL if ot is OptionType.CALL else OptionKind.PUT


def candidate_metrics(
    cand: Candidate,
    spot: float,
    atm_iv: float,
    rate: float,
    div_yield: float,
    mc_pop: McPop,
    seed: int,
) -> dict:
    legs = cand.config.legs
    t_years = max(cand.dte, 0) / 365.0
    grid = payoff.spot_grid(legs, spot)
    curve = payoff.expiration_curve(legs, grid)
    np_ = payoff.net_premium(legs)               # +debit / -credit (STRUCT-0)
    ext = payoff.max_pl(curve)
    bes = payoff.breakevens(curve)

    # closed-form PoP (PROB-1 cross-check) over the profit intervals
    cf = pop.probability_of_profit(
        spot, atm_iv, t_years, rate, div_yield,
        payoff.profit_intervals(curve),
    )

    # MC PoP/EV (the reported figure) — vol = ATM IV from the same snapshot (PROB-5)
    mc = mc_pop(legs, spot, t_years, atm_iv, rate, div_yield, seed)

    # net Greeks via per-leg BSM (GREEK-1)
    priced = []
    for leg in legs:
        if isinstance(leg, OptionLeg):
            g = bsm_greeks(
                OptionParams(
                    spot=spot,
                    strike=leg.strike,
                    t_years=t_years,
                    rate=rate,
                    sigma=atm_iv,
                    div_yield=div_yield,
                    kind=_kind(leg.option_type),
                )
            )
            priced.append((leg, g))
        else:
            priced.append((leg, None))
    net_g = aggregate.net_greeks(priced)

    max_loss_mag = None if ext["max_loss"] is None else abs(ext["max_loss"])
    return {
        "net_premium": np_,
        "net_credit": -np_ if np_ < 0 else 0.0,
        "max_profit": ext["max_profit"],
        "max_loss": max_loss_mag,
        "unbounded_loss": ext["unbounded_loss"],
        "defined_risk": not ext["unbounded_loss"],     # STRUCT-3
        "risk_reward": payoff.risk_reward(ext["max_profit"], max_loss_mag),
        "breakevens": bes,
        "pop": mc["pop"],
        "pop_method": "monte_carlo",
        "pop_closed_form": cf["pop"],
        "ev": mc["ev"],
        "ev_to_risk": (mc["ev"] / max_loss_mag) if (max_loss_mag and max_loss_mag > 0) else None,
        "percentiles": mc.get("percentiles", {}),
        "greeks": {k: round(v, 6) for k, v in net_g.items()},
        "_curve": curve,         # internal: free-lunch check + dominance test; stripped on serialize
    }
