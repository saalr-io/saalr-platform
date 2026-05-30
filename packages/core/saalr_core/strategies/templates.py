from __future__ import annotations

from .types import CashLeg, EquityLeg, OptionLeg, OptionType, Side, StrategyConfig

_C, _P, _B, _S = OptionType.CALL, OptionType.PUT, Side.BUY, Side.SELL


def _opt(otype, side, strike, expiry, qty=1):
    return OptionLeg(otype, side, float(strike), expiry, qty)


def _bull_call_spread(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _B, k, e), _opt(_C, _S, k + w, e)])


def _bear_put_spread(u, e, k, w):
    return StrategyConfig(u, [_opt(_P, _B, k, e), _opt(_P, _S, k - w, e)])


def _long_straddle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _B, k, e), _opt(_P, _B, k, e)])


def _long_strangle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _B, k + w, e), _opt(_P, _B, k - w, e)])


def _iron_condor(u, e, k, w):
    return StrategyConfig(u, [
        _opt(_P, _B, k - 2 * w, e), _opt(_P, _S, k - w, e),
        _opt(_C, _S, k + w, e), _opt(_C, _B, k + 2 * w, e),
    ])


def _iron_butterfly(u, e, k, w):
    return StrategyConfig(u, [
        _opt(_P, _B, k - w, e), _opt(_P, _S, k, e),
        _opt(_C, _S, k, e), _opt(_C, _B, k + w, e),
    ])


def _covered_call(u, e, k, w):
    return StrategyConfig(u, [EquityLeg(_B, 100), _opt(_C, _S, k + w, e)])


def _cash_secured_put(u, e, k, w):
    return StrategyConfig(u, [_opt(_P, _S, k, e), CashLeg(amount=k * 100)])


def _long_calendar(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _S, k, e), _opt(_C, _B, k, e)])


_REGISTRY: dict[str, dict] = {
    "bull_call_spread": {"name": "Bull Call Spread", "category": "bullish",
                         "description": "Long lower call, short higher call.", "build": _bull_call_spread},
    "bear_put_spread": {"name": "Bear Put Spread", "category": "bearish",
                        "description": "Long higher put, short lower put.", "build": _bear_put_spread},
    "long_straddle": {"name": "Long Straddle", "category": "neutral",
                      "description": "Long ATM call + put; profits on a big move.", "build": _long_straddle},
    "long_strangle": {"name": "Long Strangle", "category": "neutral",
                      "description": "Long OTM call + put; cheaper, wider move needed.", "build": _long_strangle},
    "iron_condor": {"name": "Iron Condor", "category": "neutral",
                    "description": "Sell a put spread and a call spread; range-bound income.", "build": _iron_condor},
    "iron_butterfly": {"name": "Iron Butterfly", "category": "neutral",
                       "description": "ATM short straddle wrapped in long wings.", "build": _iron_butterfly},
    "covered_call": {"name": "Covered Call", "category": "bullish",
                     "description": "Long 100 shares, short an OTM call.", "build": _covered_call},
    "cash_secured_put": {"name": "Cash-Secured Put", "category": "bullish",
                         "description": "Short a put backed by cash collateral.", "build": _cash_secured_put},
    "long_calendar": {"name": "Long Calendar", "category": "neutral",
                      "description": "Short near-dated, long longer-dated same strike.", "build": _long_calendar},
}


def list_templates() -> list[dict]:
    return [
        {"key": k, "name": v["name"], "category": v["category"], "description": v["description"]}
        for k, v in _REGISTRY.items()
    ]


def build(key: str, underlying: str, expiry: str, atm_strike: float, width: float = 5.0) -> StrategyConfig:
    if key not in _REGISTRY:
        raise KeyError(key)
    return _REGISTRY[key]["build"](underlying, expiry, float(atm_strike), float(width))
