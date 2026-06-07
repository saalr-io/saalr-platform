from __future__ import annotations

from .types import CashLeg, EquityLeg, Leg, OptionLeg, OptionType, Side, StrategyConfig


def _leg_from_dict(d: dict) -> Leg:
    kind = d.get("kind", "option")
    if kind == "option":
        return OptionLeg(
            option_type=OptionType(d["option_type"]),
            side=Side(d["side"]),
            strike=float(d["strike"]),
            expiry=d["expiry"],
            qty=int(d["qty"]),
            entry_price=d.get("entry_price"),
        )
    if kind == "equity":
        return EquityLeg(side=Side(d["side"]), qty=int(d["qty"]), entry_price=d.get("entry_price"))
    if kind == "cash":
        return CashLeg(amount=float(d["amount"]))
    raise ValueError(f"unknown leg kind: {kind!r}")


def config_from_json(data: dict) -> StrategyConfig:
    return StrategyConfig(
        underlying=data["underlying"],
        legs=[_leg_from_dict(d) for d in data.get("legs", [])],
    )
