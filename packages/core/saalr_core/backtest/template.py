from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from saalr_core.strategies.types import (
    CashLeg,
    EquityLeg,
    Leg,
    OptionLeg,
    OptionType,
    Side,
    StrategyConfig,
)


@dataclass(frozen=True)
class RelativeLeg:
    kind: str  # "option" | "equity" | "cash"
    side: Side | None = None
    qty: int = 0
    option_type: OptionType | None = None
    moneyness: float | None = None  # strike / ref_spot
    dte: int | None = None  # (expiry - ref_date).days
    amount: float | None = None  # cash collateral


@dataclass(frozen=True)
class RelativeTemplate:
    legs: list[RelativeLeg]
    cycle_dte: int  # the front (minimum) option-leg DTE

    @staticmethod
    def from_config(config: StrategyConfig, ref_spot: float, ref_date: date) -> "RelativeTemplate":
        if ref_spot <= 0:
            raise ValueError("ref_spot must be positive")
        rel: list[RelativeLeg] = []
        option_dtes: list[int] = []
        for leg in config.legs:
            if isinstance(leg, OptionLeg):
                expiry = date.fromisoformat(leg.expiry)
                dte = (expiry - ref_date).days
                if dte <= 0:
                    raise ValueError(
                        f"option leg expiry {leg.expiry} is not after {ref_date.isoformat()}"
                    )
                option_dtes.append(dte)
                rel.append(
                    RelativeLeg(
                        kind="option",
                        side=leg.side,
                        qty=leg.qty,
                        option_type=leg.option_type,
                        moneyness=leg.strike / ref_spot,
                        dte=dte,
                    )
                )
            elif isinstance(leg, EquityLeg):
                rel.append(RelativeLeg(kind="equity", side=leg.side, qty=leg.qty))
            elif isinstance(leg, CashLeg):
                rel.append(RelativeLeg(kind="cash", amount=leg.amount))
            else:  # pragma: no cover - defensive
                raise TypeError(f"unknown leg type: {type(leg)!r}")
        if not option_dtes:
            raise ValueError("strategy has no option legs to backtest")
        return RelativeTemplate(legs=rel, cycle_dte=min(option_dtes))

    def instantiate(
        self, roll_date: date, spot: float, strike_increment: float = 1.0
    ) -> list[Leg]:
        out: list[Leg] = []
        for rl in self.legs:
            if rl.kind == "option":
                strike = round(spot * rl.moneyness / strike_increment) * strike_increment
                expiry = (roll_date + timedelta(days=rl.dte)).isoformat()
                out.append(
                    OptionLeg(
                        option_type=rl.option_type,
                        side=rl.side,
                        strike=strike,
                        expiry=expiry,
                        qty=rl.qty,
                    )
                )
            elif rl.kind == "equity":
                out.append(EquityLeg(side=rl.side, qty=rl.qty))
            else:
                out.append(CashLeg(amount=rl.amount))
        return out
