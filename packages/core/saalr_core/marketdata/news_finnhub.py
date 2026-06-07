from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from .news import RawHeadline
from .provider import ProviderError

_BASE = "https://finnhub.io/api/v1/company-news"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


def parse_finnhub(rows: list[dict], *, ticker: str) -> list[RawHeadline]:
    """Pure: map Finnhub /company-news rows into RawHeadline; skip rows missing title or datetime."""
    out: list[RawHeadline] = []
    for r in rows:
        title = (r.get("headline") or "").strip()
        ts = r.get("datetime")
        if not title or not ts:
            continue
        try:
            published = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, OSError, TypeError):
            continue
        out.append(
            RawHeadline(
                title=title,
                description=(r.get("summary") or "").strip(),
                published_at=published,
                source=(r.get("source") or "finnhub").strip(),
                url=(r.get("url") or "").strip(),
                tickers=[ticker.upper()],
            )
        )
    return out


class FinnhubNewsProvider:
    def __init__(
        self, api_key: str | None, *, base_url: str = _BASE, timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base = base_url
        self._timeout = timeout
        self._transport = transport

    async def get_news(
        self, ticker: str, limit: int = 50, published_after: datetime | None = None
    ) -> list[RawHeadline]:
        if not self._api_key:
            raise ProviderError("no finnhub api key configured")
        end = datetime.now(timezone.utc)
        start = published_after or (end - timedelta(days=7))
        params = {
            "symbol": ticker.upper(),
            "from": start.date().isoformat(),
            "to": end.date().isoformat(),
            "token": self._api_key,
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            rows: object = []
            for attempt in range(3):
                try:
                    r = await client.get(self._base, params=params)
                    if r.status_code in _RETRYABLE:
                        if attempt < 2:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        raise ProviderError(f"finnhub returned {r.status_code} after retries")
                    r.raise_for_status()
                    rows = r.json()
                    break
                except httpx.HTTPStatusError as exc:
                    raise ProviderError(str(exc)) from exc
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        raise ProviderError(str(exc)) from exc
                    await asyncio.sleep(0.5 * (attempt + 1))
            else:
                raise ProviderError("exhausted retries")
        if not isinstance(rows, list):
            return []
        items = parse_finnhub(rows, ticker=ticker)
        if published_after is not None:
            items = [h for h in items if h.published_at >= published_after]
        return items[:limit]
