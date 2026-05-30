from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from .provider import ProviderError

_BASE = "https://api.massive.com"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class BarRow:
    ts: datetime
    symbol: str
    market: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: int


def parse_aggregates(results: list[dict], symbol: str, market: str) -> list[BarRow]:
    """Pure: map Massive daily-aggregate rows into BarRow (vendor JSON stops here)."""
    out: list[BarRow] = []
    for r in results:
        out.append(
            BarRow(
                ts=datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc),
                symbol=symbol,
                market=market,
                interval="1d",
                open=float(r["o"]),
                high=float(r["h"]),
                low=float(r["l"]),
                close=float(r["c"]),
                volume=int(r.get("v", 0)),
            )
        )
    return out


class MassiveAggregatesProvider:
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
                raise ProviderError(str(exc)) from exc
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise ProviderError(str(exc)) from exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise ProviderError("exhausted retries")

    async def get_daily_bars(self, symbol: str, start: date, end: date, market: str = "US") -> list[BarRow]:
        if not self._api_key:
            raise ProviderError("no massive api key configured")
        rows: list[BarRow] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self._base}/v2/aggs/ticker/{symbol}/range/1/day/{start.isoformat()}/{end.isoformat()}"
            params: dict = {"apiKey": self._api_key, "adjusted": "true", "limit": 50000}
            seen: set[str] = set()
            while url and url not in seen:  # guard against a cyclic/echoed next_url
                seen.add(url)
                data = await self._get(client, url, params)
                rows.extend(parse_aggregates(data.get("results", []) or [], symbol, market))
                url = data.get("next_url")
                params = {"apiKey": self._api_key}
        return rows
