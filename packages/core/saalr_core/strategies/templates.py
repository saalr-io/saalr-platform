from __future__ import annotations

from .types import CashLeg, EquityLeg, OptionLeg, OptionType, Side, StrategyConfig

_C, _P, _B, _S = OptionType.CALL, OptionType.PUT, Side.BUY, Side.SELL


def _opt(otype, side, strike, expiry, qty=1):
    return OptionLeg(otype, side, float(strike), expiry, qty)


# --- existing 9 (build logic unchanged) ---
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


# --- new 12 (all single-expiry; fit the existing build signature) ---
def _bull_put_spread(u, e, k, w):
    # bullish credit: sell put @k, buy put @k-w
    return StrategyConfig(u, [_opt(_P, _S, k, e), _opt(_P, _B, k - w, e)])


def _bear_call_spread(u, e, k, w):
    # bearish credit: sell call @k, buy call @k+w
    return StrategyConfig(u, [_opt(_C, _S, k, e), _opt(_C, _B, k + w, e)])


def _short_straddle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _S, k, e), _opt(_P, _S, k, e)])


def _short_strangle(u, e, k, w):
    return StrategyConfig(u, [_opt(_C, _S, k + w, e), _opt(_P, _S, k - w, e)])


def _protective_put(u, e, k, w):
    return StrategyConfig(u, [EquityLeg(_B, 100), _opt(_P, _B, k - w, e)])


def _collar(u, e, k, w):
    return StrategyConfig(u, [EquityLeg(_B, 100), _opt(_P, _B, k - w, e), _opt(_C, _S, k + w, e)])


def _call_ratio_spread(u, e, k, w):
    # buy 1 call @k, sell 2 calls @k+w
    return StrategyConfig(u, [_opt(_C, _B, k, e, 1), _opt(_C, _S, k + w, e, 2)])


def _put_ratio_spread(u, e, k, w):
    # buy 1 put @k, sell 2 puts @k-w
    return StrategyConfig(u, [_opt(_P, _B, k, e, 1), _opt(_P, _S, k - w, e, 2)])


def _jade_lizard(u, e, k, w):
    # short put @k-w + short call spread (short @k+w, long @k+2w)
    return StrategyConfig(u, [
        _opt(_P, _S, k - w, e), _opt(_C, _S, k + w, e), _opt(_C, _B, k + 2 * w, e),
    ])


def _call_butterfly(u, e, k, w):
    # buy call @k-w, sell 2 calls @k, buy call @k+w
    return StrategyConfig(u, [_opt(_C, _B, k - w, e), _opt(_C, _S, k, e, 2), _opt(_C, _B, k + w, e)])


def _put_butterfly(u, e, k, w):
    # buy put @k+w, sell 2 puts @k, buy put @k-w
    return StrategyConfig(u, [_opt(_P, _B, k + w, e), _opt(_P, _S, k, e, 2), _opt(_P, _B, k - w, e)])


def _broken_wing_butterfly(u, e, k, w):
    # buy call @k-w, sell 2 calls @k, buy call @k+2w (asymmetric upper wing)
    return StrategyConfig(u, [_opt(_C, _B, k - w, e), _opt(_C, _S, k, e, 2), _opt(_C, _B, k + 2 * w, e)])


# metadata: market_view, vol_view, net, risk, reward, legs, complexity (see spec)
_REGISTRY: dict[str, dict] = {
    "bull_call_spread": {"name": "Bull Call Spread", "market_view": "bullish", "vol_view": "neutral",
        "net": "debit", "risk": "defined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Long lower call, short higher call.", "build": _bull_call_spread},
    "bear_put_spread": {"name": "Bear Put Spread", "market_view": "bearish", "vol_view": "neutral",
        "net": "debit", "risk": "defined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Long higher put, short lower put.", "build": _bear_put_spread},
    "long_straddle": {"name": "Long Straddle", "market_view": "volatile", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "undefined", "legs": 2, "complexity": "intermediate",
        "description": "Long ATM call + put; profits on a big move either way.", "build": _long_straddle},
    "long_strangle": {"name": "Long Strangle", "market_view": "volatile", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "undefined", "legs": 2, "complexity": "intermediate",
        "description": "Long OTM call + put; cheaper, wider move needed.", "build": _long_strangle},
    "iron_condor": {"name": "Iron Condor", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 4, "complexity": "intermediate",
        "description": "Sell a put spread and a call spread; range-bound income.", "build": _iron_condor},
    "iron_butterfly": {"name": "Iron Butterfly", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 4, "complexity": "intermediate",
        "description": "ATM short straddle wrapped in long wings.", "build": _iron_butterfly},
    "covered_call": {"name": "Covered Call", "market_view": "bullish", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Long 100 shares, short an OTM call for income.", "build": _covered_call},
    "cash_secured_put": {"name": "Cash-Secured Put", "market_view": "bullish", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Short a put backed by cash collateral.", "build": _cash_secured_put},
    "long_calendar": {"name": "Long Calendar", "market_view": "neutral", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "undefined", "legs": 2, "complexity": "advanced",
        "description": "Short near-dated, long longer-dated same strike.", "build": _long_calendar},
    "bull_put_spread": {"name": "Bull Put Spread", "market_view": "bullish", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Sell a put, buy a lower put; bullish credit spread.", "build": _bull_put_spread},
    "bear_call_spread": {"name": "Bear Call Spread", "market_view": "bearish", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 2, "complexity": "beginner",
        "description": "Sell a call, buy a higher call; bearish credit spread.", "build": _bear_call_spread},
    "short_straddle": {"name": "Short Straddle", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "advanced",
        "description": "Sell ATM call + put; collect premium, undefined risk.", "build": _short_straddle},
    "short_strangle": {"name": "Short Strangle", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "advanced",
        "description": "Sell OTM call + put; wider range, undefined risk.", "build": _short_strangle},
    "protective_put": {"name": "Protective Put", "market_view": "bullish", "vol_view": "long_vol",
        "net": "debit", "risk": "defined", "reward": "undefined", "legs": 2, "complexity": "beginner",
        "description": "Long 100 shares hedged with a long put.", "build": _protective_put},
    "collar": {"name": "Collar", "market_view": "bullish", "vol_view": "neutral",
        "net": "mixed", "risk": "defined", "reward": "defined", "legs": 3, "complexity": "intermediate",
        "description": "Long stock, long protective put, short covered call.", "build": _collar},
    "call_ratio_spread": {"name": "Call Ratio Spread", "market_view": "bullish", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "advanced",
        "description": "Buy 1 call, sell 2 higher calls; undefined upside risk.", "build": _call_ratio_spread},
    "put_ratio_spread": {"name": "Put Ratio Spread", "market_view": "bearish", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 2, "complexity": "advanced",
        "description": "Buy 1 put, sell 2 lower puts; undefined downside risk.", "build": _put_ratio_spread},
    "jade_lizard": {"name": "Jade Lizard", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "undefined", "reward": "defined", "legs": 3, "complexity": "advanced",
        "description": "Short put + short call spread; no upside risk if credit > spread.", "build": _jade_lizard},
    "call_butterfly": {"name": "Call Butterfly", "market_view": "neutral", "vol_view": "short_vol",
        "net": "debit", "risk": "defined", "reward": "defined", "legs": 3, "complexity": "intermediate",
        "description": "1-2-1 call butterfly; profits if price pins the body.", "build": _call_butterfly},
    "put_butterfly": {"name": "Put Butterfly", "market_view": "neutral", "vol_view": "short_vol",
        "net": "debit", "risk": "defined", "reward": "defined", "legs": 3, "complexity": "intermediate",
        "description": "1-2-1 put butterfly; profits if price pins the body.", "build": _put_butterfly},
    "broken_wing_butterfly": {"name": "Broken-Wing Butterfly", "market_view": "neutral", "vol_view": "short_vol",
        "net": "credit", "risk": "defined", "reward": "defined", "legs": 3, "complexity": "advanced",
        "description": "Call butterfly with a wider upper wing; often a credit, no downside risk.", "build": _broken_wing_butterfly},
}

_META_FIELDS = ("name", "market_view", "vol_view", "net", "risk", "reward", "legs", "complexity", "description")


def list_templates() -> list[dict]:
    return [{"key": k, **{f: v[f] for f in _META_FIELDS}} for k, v in _REGISTRY.items()]


def build(key: str, underlying: str, expiry: str, atm_strike: float, width: float = 5.0) -> StrategyConfig:
    if key not in _REGISTRY:
        raise KeyError(key)
    return _REGISTRY[key]["build"](underlying, expiry, float(atm_strike), float(width))
