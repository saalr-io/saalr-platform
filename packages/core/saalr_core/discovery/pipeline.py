from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from saalr_core.strategies import recommend as recommend_mod
from saalr_core.strategies import templates
from saalr_ml.regime import classify_regime

from . import baseline as baseline_mod
from . import generate
from . import metrics as metrics_mod
from . import serialize
from .filters import Filters, apply_filters
from .gates import is_free_lunch
from .generate import OPTION_ONLY_TEMPLATES, atm_strike
from .rank import rank_and_truncate
from .types import CleanChain, DiscoveryResult

DEFAULT_FAMILIES = 3
DEFAULT_SEED = 7


@dataclass(frozen=True)
class DiscoveryRequest:
    dte_min: int
    dte_max: int
    strike_window: int = 5
    profile: str = "ev_to_risk"
    top_n: int = 10
    families: list[str] | None = None       # override; None -> regime-selected
    min_pop: float | None = None
    max_loss: float | None = None
    min_open_interest: int | None = None
    max_bid_ask_pct: float | None = None
    seed: int = DEFAULT_SEED


def _atm_iv(chain: CleanChain, expiry: str) -> float:
    from saalr_core.strategies.types import OptionType  # noqa: PLC0415
    k = atm_strike(chain.strikes_for_expiry(expiry), chain.spot)
    for kind in (OptionType.PUT, OptionType.CALL):
        c = chain.contract(expiry, k, kind)
        if c and c.iv:
            return c.iv
    return 0.3


def _select_families(regime: dict, override: list[str] | None) -> list[str]:
    if override:
        return [k for k in override if k in OPTION_ONLY_TEMPLATES]
    ranked = recommend_mod.recommend(regime, templates.list_templates())
    picked = [r["template_key"] for r in ranked if r["template_key"] in OPTION_ONLY_TEMPLATES]
    return picked[:DEFAULT_FAMILIES]


def _min_oi(chain: CleanChain, cand) -> int:
    from saalr_core.strategies.types import OptionLeg  # noqa: PLC0415
    ois = []
    for leg in cand.config.legs:
        if isinstance(leg, OptionLeg):
            c = chain.contract(cand.expiry, leg.strike, leg.option_type)
            ois.append(c.open_interest or 0 if c else 0)
    return min(ois) if ois else 0


def run_discovery(
    chain: CleanChain,
    closes: list[float],
    rate_for: Callable[[float], float],
    mc_pop: Callable[..., dict],
    req: DiscoveryRequest,
    as_of_date: date,
) -> DiscoveryResult:
    regime = classify_regime(closes)                                   # stage 0
    families = _select_families(regime, req.families)

    candidates = generate.enumerate_candidates(                        # stages 1-2
        chain, families, req.dte_min, req.dte_max, req.strike_window, as_of_date
    )

    scored: list[dict] = []
    dq: list[dict] = []
    for cand in candidates:
        atm_iv = _atm_iv(chain, cand.expiry)
        rate = rate_for(max(cand.dte, 0) / 365.0)
        m = metrics_mod.candidate_metrics(                             # stages 4 + 6
            cand, chain.spot, atm_iv, rate, chain.div_yield, mc_pop, req.seed
        )
        if is_free_lunch(m["net_premium"], m["_curve"]):               # stage 5 (RANK-2)
            dq.append({
                "template_key": cand.template_key,
                "expiry": cand.expiry,
                "reason": "free_lunch",
                "net_credit": m["net_credit"],
            })
            continue
        m["_strikes"] = tuple(sorted(leg.strike for leg in cand.config.legs))
        m["min_open_interest"] = _min_oi(chain, cand)
        m["max_bid_ask_pct"] = 0.0
        scored.append({
            "template_key": cand.template_key,
            "expiry": cand.expiry,
            "candidate": cand,
            "metrics": m,
        })

    f = Filters(req.min_pop, req.max_loss, req.min_open_interest, req.max_bid_ask_pct)
    filtered = apply_filters(scored, f)                                # stage 7 (RANK-3)
    ranked = rank_and_truncate(filtered, req.profile, req.top_n)       # stage 8 (RANK-1/4/5)

    results = [                                                        # stage 9 (COMPLY)
        serialize.serialize_candidate(c["candidate"], c["metrics"], rank=i + 1, profile=req.profile)
        for i, c in enumerate(ranked)
    ]

    # DATA-4: honest baseline on the nearest in-range expiry
    base_expiry = ranked[0]["expiry"] if ranked else (candidates[0].expiry if candidates else None)
    if base_expiry is not None:
        base_dte = (date.fromisoformat(base_expiry) - as_of_date).days
        base = baseline_mod.naive_atm_short_put(
            chain, base_expiry, base_dte,
            rate_for(max(base_dte, 0) / 365.0),
            mc_pop, req.seed,
        )
    else:
        base = {"naive": "atm_short_put", "pop": None, "ev": None}

    return DiscoveryResult(
        underlying=chain.underlying,
        as_of=chain.as_of,
        scoring_profile=req.profile,
        regime=regime,
        results=results,
        baseline=base,
        data_quality_report=dq,
        disclosure_block_id=serialize.DISCLOSURE_BLOCK_ID,
    )
