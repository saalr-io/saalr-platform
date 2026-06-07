from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from .provider import ProviderError

_BASE = "https://api.massive.com"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RawHeadline:
    title: str
    description: str
    published_at: datetime
    source: str
    url: str
    tickers: list[str] = field(default_factory=list)


def _parse_dt(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def parse_news(results: list[dict]) -> list[RawHeadline]:
    """Pure: map Massive /v2/reference/news rows into RawHeadline; skip malformed rows."""
    out: list[RawHeadline] = []
    for r in results:
        title = r.get("title")
        published = _parse_dt(r.get("published_utc", ""))
        if not title or published is None:
            continue
        publisher = r.get("publisher") or {}
        source = publisher.get("name", "") if isinstance(publisher, dict) else ""
        out.append(
            RawHeadline(
                title=title,
                description=r.get("description") or "",
                published_at=published,
                source=source,
                url=r.get("article_url", "") or "",
                tickers=list(r.get("tickers") or []),
            )
        )
    return out


class MassiveNewsProvider:
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

    async def get_news(
        self, ticker: str, limit: int = 50, published_after: datetime | None = None
    ) -> list[RawHeadline]:
        if not self._api_key:
            raise ProviderError("no massive api key configured")
        out: list[RawHeadline] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{self._base}/v2/reference/news"
            params: dict = {
                "ticker": ticker,
                "limit": limit,
                "order": "desc",
                "sort": "published_utc",
                "apiKey": self._api_key,
            }
            if published_after is not None:
                params["published_utc.gte"] = published_after.isoformat()
            seen: set[str] = set()
            while url and url not in seen:
                seen.add(url)
                data = await self._get(client, url, params)
                out.extend(parse_news(data.get("results", []) or []))
                url = data.get("next_url")
                params = {"apiKey": self._api_key}
        return out
