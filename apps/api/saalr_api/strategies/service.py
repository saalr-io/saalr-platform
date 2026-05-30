from __future__ import annotations

from dataclasses import replace
from datetime import date

from saalr_core.pricing.model import BSMModel
from saalr_core.pricing.types import OptionKind, OptionParams
from saalr_core.strategies import payoff, pop
from saalr_core.strategies.aggregate import net_greeks
from saalr_core.strategies.types import OptionLeg

_MODEL = BSMModel()


def analyze_pure(config) -> dict:
    """Expiration payoff analytics from caller-supplied entry prices (no live data)."""
    legs = config.legs
    spot_anchor = _anchor_spot(legs)
    grid = payoff.spot_grid(legs, spot_anchor)
    curve = payoff.expiration_curve(legs, grid)
    m = payoff.max_pl(curve)
    return {
        "expiration_curve": [{"spot": s, "pnl": p} for s, p in curve],
        "breakevens": payoff.breakevens(curve),
        "max_profit": m["max_profit"],
        "max_loss": m["max_loss"],
        "unbounded_profit": m["unbounded_profit"],
        "unbounded_loss": m["unbounded_loss"],
        "net_premium": payoff.net_premium(legs),
        "risk_reward": payoff.risk_reward(m["max_profit"], m["max_loss"]),
    }


def _anchor_spot(legs) -> float:
    strikes = [leg.strike for leg in legs if isinstance(leg, OptionLeg)]
    return sum(strikes) / len(strikes) if strikes else 100.0


def _match_contract(chain_contracts: list[dict], leg: OptionLeg) -> dict | None:
    for c in chain_contracts:
        if c["expiry"] == leg.expiry and abs(c["strike"] - leg.strike) < 1e-6 \
                and c["type"] == leg.option_type.value:
            return c
    return None


def _atm_iv(filled_legs: list, iv_by_leg: dict[int, float], spot: float) -> float:
    """IV of the option leg whose strike is nearest spot (true ATM), else 0.0."""
    best_iv, best_dist = 0.0, None
    for i, leg in enumerate(filled_legs):
        if i in iv_by_leg:
            dist = abs(leg.strike - spot)
            if best_dist is None or dist < best_dist:
                best_dist, best_iv = dist, iv_by_leg[i]
    return best_iv


def _years_to(expiry: str) -> float:
    return max((date.fromisoformat(expiry) - date.today()).days, 0) / 365.0


async def analyze_live(config, market_service, rate_provider, session, ticker, market,
                       target_date: str | None) -> dict:
    """Pure payoff enriched with live prices, net Greeks, target-date curve, and POP."""
    chain = await market_service.chain(session, ticker, market, expiry=None)
    spot = chain["spot"]
    contracts = chain["contracts"]
    yield_curve = await rate_provider.get_curve()
    legs = config.legs

    iv_by_leg: dict[int, float] = {}
    priced: list[tuple[object, object]] = []
    filled_legs = []
    for i, leg in enumerate(legs):
        if isinstance(leg, OptionLeg):
            match = _match_contract(contracts, leg)
            iv = (match or {}).get("ours", {}).get("iv")
            mid = (match or {}).get("ours", {}).get("price")
            entry = leg.entry_price if leg.entry_price is not None else (mid or 0.0)
            leg = replace(leg, entry_price=entry)
            if iv:
                iv_by_leg[i] = iv
                t = _years_to(leg.expiry)
                rate = yield_curve.rate_for(t) if t > 0 else 0.0
                kind = OptionKind.CALL if leg.option_type.value == "CALL" else OptionKind.PUT
                g = _MODEL.greeks(OptionParams(spot, leg.strike, t, rate, iv, 0.0, kind)) if t > 0 else None
                priced.append((leg, g))
            else:
                priced.append((leg, None))
        else:
            priced.append((leg, None))
        filled_legs.append(leg)

    grid = payoff.spot_grid(filled_legs, spot)
    curve = payoff.expiration_curve(filled_legs, grid)
    m = payoff.max_pl(curve)
    intervals = payoff.profit_intervals(curve)
    atm_iv = _atm_iv(filled_legs, iv_by_leg, spot)
    t_exp = min((_years_to(leg.expiry) for leg in filled_legs if isinstance(leg, OptionLeg)), default=0.0)
    rate_exp = yield_curve.rate_for(t_exp) if t_exp > 0 else 0.0
    pop_out = pop.probability_of_profit(spot, atm_iv, t_exp, rate_exp, 0.0, intervals)

    result = {
        "expiration_curve": [{"spot": s, "pnl": p} for s, p in curve],
        "breakevens": payoff.breakevens(curve),
        "max_profit": m["max_profit"], "max_loss": m["max_loss"],
        "unbounded_profit": m["unbounded_profit"], "unbounded_loss": m["unbounded_loss"],
        "net_premium": payoff.net_premium(filled_legs),
        "risk_reward": payoff.risk_reward(m["max_profit"], m["max_loss"]),
        "net_greeks": net_greeks(priced),
        "probability_of_profit": pop_out,
        "spot": spot, "data_provider": "massive", "model": "bsm",
        "risk_free_source": getattr(rate_provider, "source_name", "fred"),
    }
    if target_date:
        result["target_date_curve"] = [
            {"spot": s, "pnl": p}
            for s, p in payoff.target_date_curve(
                filled_legs, grid, date.fromisoformat(target_date), rate_exp, 0.0, iv_by_leg
            )
        ]
    return result
