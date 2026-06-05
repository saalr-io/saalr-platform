from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx

from saalr_core.pricing.types import OptionKind

from .provider import ProviderError
from .types import RawChain, RawContract

_BASE = "https://api.massive.com"
_KIND = {"call": OptionKind.CALL, "put": OptionKind.PUT}
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


def _num(d: dict | None, key: str):
    return None if d is None else d.get(key)


def _chain_query_params(
    api_key: str | None, spot: float, atm_band: float, expiry_horizon_days: int, today: date
) -> dict:
    """Build the /v3/snapshot/options query so the vendor returns only the relevant slice:
    strikes within +-atm_band of spot and expiries within the horizon. A full SPY chain is
    tens of thousands of contracts (daily 0DTE x hundreds of strikes) and never returns in
    time; this windows it to a few hundred. Strike bounds are skipped when spot is unknown
    (e.g. market closed with no last trade), leaving the expiry bound to do the cutting."""
    # sort by expiry ascending so the page budget walks the NEAREST expiries first
    # (a useful surface), not an arbitrary slice.
    params: dict = {"apiKey": api_key, "limit": 250, "sort": "expiration_date", "order": "asc"}
    if spot > 0 and atm_band:
        params["strike_price.gte"] = round(spot * (1 - atm_band), 2)
        params["strike_price.lte"] = round(spot * (1 + atm_band), 2)
    # Floor at tomorrow: BSM can't price 0DTE (t=0), so the chain pipeline drops them anyway.
    # Excluding them server-side keeps the page budget on priceable expiries (SPY has hundreds
    # of 0DTE strikes that would otherwise fill every page and yield an empty computed chain).
    params["expiration_date.gte"] = (today + timedelta(days=1)).isoformat()
    if expiry_horizon_days:
        params["expiration_date.lte"] = (today + timedelta(days=expiry_horizon_days)).isoformat()
    return params


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
                if r.status_code in _RETRYABLE:
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    raise ProviderError(f"massive returned {r.status_code} after retries")
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as exc:
                raise ProviderError(str(exc)) from exc  # non-retryable 4xx — fail fast
            except httpx.HTTPError as exc:  # transport error (timeout/connect) — retry
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
        tk = snap.get("ticker", {})
        # fall back to the prior session close when there is no last trade (market closed),
        # so the ATM strike window can still be computed after hours.
        spot = float(tk.get("lastTrade", {}).get("p", 0.0)) or float(tk.get("prevDay", {}).get("c", 0.0))
        div_yield = float(res.get("dividend_yield") or 0.0)
        return spot, div_yield

    async def get_option_chain(
        self, ticker: str, market: str, *,
        atm_band: float = 0.15, expiry_horizon_days: int = 90, max_pages: int = 12,
    ) -> RawChain:
        if not self._api_key:
            raise ProviderError("no massive api key configured")

        contracts: list[RawContract] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            # spot first: it bounds the strike window so a huge chain (SPY) stays small.
            spot, div_yield = await self._spot_and_div(client, ticker)
            url = f"{self._base}/v3/snapshot/options/{ticker}"
            base = _chain_query_params(self._api_key, spot, atm_band, expiry_horizon_days, date.today())
            params = dict(base)
            for _ in range(max_pages):
                data = await self._get(client, url, params)
                contracts.extend(parse_results(data.get("results", [])))
                cursor = parse_qs(urlparse(data.get("next_url") or "").query).get("cursor", [None])[0]
                if not cursor:
                    break
                # Re-apply our filters + the cursor every page: the vendor's next_url drops
                # the strike/expiry bounds, so following it blindly leaks the full chain back in.
                params = {**base, "cursor": cursor}

        as_of = datetime.now(timezone.utc).isoformat()
        return RawChain(
            underlying=ticker, market=market, as_of=as_of,
            spot=spot, div_yield=div_yield, contracts=contracts,
        )
