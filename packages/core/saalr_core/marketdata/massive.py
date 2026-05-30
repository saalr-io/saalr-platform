from __future__ import annotations

import asyncio

import httpx

from saalr_core.pricing.types import OptionKind

from .provider import ProviderError
from .types import RawChain, RawContract

_BASE = "https://api.massive.com"
_KIND = {"call": OptionKind.CALL, "put": OptionKind.PUT}


def _num(d: dict | None, key: str):
    return None if d is None else d.get(key)


def parse_results(results: list[dict]) -> list[RawContract]:
    """Pure: map Massive option snapshot rows into RawContract (vendor JSON stops here)."""
    out: list[RawContract] = []
    for row in results:
        det = row.get("details", {})
        kind = _KIND.get(det.get("contract_type"))
        if kind is None:
            continue
        quote = row.get("last_quote", {})
        day = row.get("day") or row.get("session") or {}  # legacy "day" / unified "session"
        g = row.get("greeks", {})
        out.append(
            RawContract(
                expiry=det["expiration_date"],
                strike=float(det["strike_price"]),
                kind=kind,
                bid=_num(quote, "bid"),
                ask=_num(quote, "ask"),
                last=_num(day, "close"),
                volume=_num(day, "volume"),
                open_interest=row.get("open_interest"),
                vendor_iv=row.get("implied_volatility"),
                vendor_delta=_num(g, "delta"),
                vendor_gamma=_num(g, "gamma"),
                vendor_theta=_num(g, "theta"),
                vendor_vega=_num(g, "vega"),
            )
        )
    return out


class MassiveProvider:
    def __init__(self, api_key: str | None, *, base_url: str = _BASE) -> None:
        self._api_key = api_key
        self._base = base_url

    async def _get(self, client: httpx.AsyncClient, url: str, params: dict) -> dict:
        for attempt in range(3):
            try:
                r = await client.get(url, params=params)
                if r.status_code in (429, 500, 502, 503):
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ProviderError(str(exc)) from exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ProviderError("exhausted retries")

    async def _spot_and_div(self, client: httpx.AsyncClient, ticker: str) -> tuple[float, float]:
        data = await self._get(
            client, f"{self._base}/v3/reference/tickers/{ticker}",
            {"apiKey": self._api_key},
        )
        res = data.get("results", {})
        snap = await self._get(
            client, f"{self._base}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
            {"apiKey": self._api_key},
        )
        spot = float(snap.get("ticker", {}).get("lastTrade", {}).get("p", 0.0))
        div_yield = float(res.get("dividend_yield") or 0.0)
        return spot, div_yield

    async def get_option_chain(self, ticker: str, market: str) -> RawChain:
        if not self._api_key:
            raise ProviderError("no massive api key configured")
        from datetime import datetime, timezone

        contracts: list[RawContract] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            url = f"{self._base}/v3/snapshot/options/{ticker}"
            params = {"apiKey": self._api_key, "limit": 250}
            while url:
                data = await self._get(client, url, params)
                contracts.extend(parse_results(data.get("results", [])))
                url = data.get("next_url")
                params = {"apiKey": self._api_key}  # next_url already carries cursor
            spot, div_yield = await self._spot_and_div(client, ticker)

        as_of = datetime.now(timezone.utc).isoformat()
        return RawChain(
            underlying=ticker, market=market, as_of=as_of,
            spot=spot, div_yield=div_yield, contracts=contracts,
        )
