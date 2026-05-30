from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from saalr_core.marketdata.provider import MarketDataProvider, RiskFreeRateProvider
from saalr_core.marketdata.types import RawChain
from saalr_core.pricing.model import BSMModel
from saalr_core.pricing.surface import build_surface
from saalr_core.pricing.types import ContractGreeks, Greeks, OptionKind, OptionParams

from .snapshots import persist_chain

_MODEL = BSMModel()


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _mid(c) -> float | None:
    if c.bid is not None and c.ask is not None and c.bid > 0 and c.ask > 0:
        return (c.bid + c.ask) / 2.0
    return c.last if (c.last and c.last > 0) else None


def _compute(chain: RawChain, rate_for, as_of_date: date) -> list[ContractGreeks]:
    out: list[ContractGreeks] = []
    for c in chain.contracts:
        dte = (date.fromisoformat(c.expiry) - as_of_date).days
        t_years = max(dte, 0) / 365.0
        if t_years <= 0:
            continue
        rate = rate_for(t_years)
        base = OptionParams(
            spot=chain.spot, strike=c.strike, t_years=t_years, rate=rate,
            sigma=0.0, div_yield=chain.div_yield, kind=c.kind,
        )
        mkt = _mid(c)
        iv = _MODEL.implied_vol(mkt, base) if mkt is not None else None
        g = _MODEL.greeks(OptionParams(**{**base.__dict__, "sigma": iv})) if iv is not None else None
        ours = (
            Greeks(price=g.price, delta=g.delta, gamma=g.gamma, theta=g.theta,
                   vega=g.vega, rho=g.rho, iv=iv)
            if g else Greeks(price=mkt or 0.0, delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0, iv=None)
        )
        out.append(
            ContractGreeks(
                expiry=c.expiry, strike=c.strike, kind=c.kind, bid=c.bid, ask=c.ask,
                last=c.last, volume=c.volume, open_interest=c.open_interest, ours=ours,
                vendor_iv=c.vendor_iv, vendor_delta=c.vendor_delta, vendor_gamma=c.vendor_gamma,
                vendor_theta=c.vendor_theta, vendor_vega=c.vendor_vega,
            )
        )
    return out


class MarketService:
    def __init__(self, provider: MarketDataProvider, rates: RiskFreeRateProvider, redis, ttl: int):
        self._provider = provider
        self._rates = rates
        self._redis = redis
        self._ttl = ttl

    async def _computed_chain(self, session: AsyncSession, ticker: str, market: str) -> dict:
        key = f"mdq:chain:v1:{market}:{ticker.upper()}"  # bump v on payload-schema change
        cached = await self._redis.get(key)
        if cached:
            return json.loads(cached)

        chain = await self._provider.get_option_chain(ticker, market)
        curve = await self._rates.get_curve()
        as_of_date = datetime.fromisoformat(chain.as_of).date()
        contracts = _compute(chain, curve.rate_for, as_of_date)
        await persist_chain(session, ticker.upper(), market, chain.as_of, contracts)

        payload = {
            "ticker": ticker.upper(),
            "market": market,
            "as_of": chain.as_of,
            "spot": chain.spot,
            "risk_free_source": getattr(self._rates, "source_name", "fred"),
            "contracts": [_contract_json(c) for c in contracts],
            "computed_at_ms": _now_ms(),
        }
        await self._redis.set(key, json.dumps(payload), ex=self._ttl)
        return payload

    async def iv_surface(self, session, ticker, market) -> dict:
        payload = await self._computed_chain(session, ticker, market)
        contracts = [_contract_from_json(c) for c in payload["contracts"]]
        as_of_date = datetime.fromisoformat(payload["as_of"]).date()
        return {
            "ticker": payload["ticker"],
            "market": payload["market"],
            "as_of": payload["as_of"],
            "spot": payload["spot"],
            "expiries": build_surface(contracts, as_of_date),
            "data_provider": "massive",
            "model": "bsm",
            "risk_free_source": payload["risk_free_source"],
            "freshness_ms": max(0, _now_ms() - payload["computed_at_ms"]),
        }

    async def chain(self, session, ticker, market, expiry: str | None) -> dict:
        payload = await self._computed_chain(session, ticker, market)
        rows = payload["contracts"]
        if expiry:
            rows = [r for r in rows if r["expiry"] == expiry]
        return {
            "ticker": payload["ticker"],
            "market": payload["market"],
            "as_of": payload["as_of"],
            "spot": payload["spot"],
            "model": "bsm",
            "risk_free_source": payload["risk_free_source"],
            "contracts": rows,
        }


def _contract_json(c: ContractGreeks) -> dict:
    return {
        "expiry": c.expiry, "strike": c.strike, "type": c.kind.value,
        "bid": c.bid, "ask": c.ask, "last": c.last,
        "volume": c.volume, "open_interest": c.open_interest,
        "ours": {
            "price": c.ours.price, "delta": c.ours.delta, "gamma": c.ours.gamma,
            "theta": c.ours.theta, "vega": c.ours.vega, "rho": c.ours.rho, "iv": c.ours.iv,
        },
        "vendor": {
            "iv": c.vendor_iv, "delta": c.vendor_delta, "gamma": c.vendor_gamma,
            "theta": c.vendor_theta, "vega": c.vendor_vega,
        },
    }


def _contract_from_json(d: dict) -> ContractGreeks:
    o = d["ours"]
    return ContractGreeks(
        expiry=d["expiry"], strike=d["strike"], kind=OptionKind(d["type"]),
        bid=d["bid"], ask=d["ask"], last=d["last"], volume=d["volume"],
        open_interest=d["open_interest"],
        ours=Greeks(price=o["price"], delta=o["delta"], gamma=o["gamma"], theta=o["theta"],
                    vega=o["vega"], rho=o["rho"], iv=o["iv"]),
        vendor_iv=d["vendor"]["iv"], vendor_delta=d["vendor"]["delta"],
        vendor_gamma=d["vendor"]["gamma"], vendor_theta=d["vendor"]["theta"],
        vendor_vega=d["vendor"]["vega"],
    )
