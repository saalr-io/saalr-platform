from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PromotionDecision:
    ok: bool
    code: str | None = None
    message: str | None = None
    details: dict | None = None


def evaluate_promotion(
    state: str,
    brokers_entitlement: int,
    first_paper_order_at: datetime | None,
    now: datetime,
    step_up_ok: bool,
    min_paper_days: int = 14,
) -> PromotionDecision:
    """Pure paper->live promotion gate. Returns the first failing gate, else ok=True.

    Order: in-paper-state -> live-trading entitlement -> 14-day paper track record -> step-up (MFA).
    `now` and `first_paper_order_at` are injected so this is deterministic and DB/Redis-free.

    The datetimes must be timezone-aware; a naive value is rejected loudly rather than silently
    miscounting days (this gate guards real-money promotion).
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if first_paper_order_at is not None and first_paper_order_at.tzinfo is None:
        raise ValueError("first_paper_order_at must be timezone-aware")
    if state != "paper":
        return PromotionDecision(
            False,
            "STRATEGY_NOT_IN_PAPER",
            "only a paper strategy can be promoted to live",
        )
    if brokers_entitlement <= 0:
        return PromotionDecision(
            False,
            "ENTITLEMENT_LIVE_TRADING_REQUIRES_PRO",
            "live trading requires a Pro or Premium plan",
        )
    days_traded = (now - first_paper_order_at).days if first_paper_order_at is not None else 0
    if first_paper_order_at is None or days_traded < min_paper_days:
        return PromotionDecision(
            False,
            "STRATEGY_INSUFFICIENT_PAPER_HISTORY",
            f"needs {min_paper_days} days of paper trading before going live",
            {"days_traded": days_traded, "days_required": min_paper_days},
        )
    if not step_up_ok:
        return PromotionDecision(
            False,
            "AUTH_MFA_REQUIRED",
            "step-up verification required to go live",
        )
    return PromotionDecision(True)
