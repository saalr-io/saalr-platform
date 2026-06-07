from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

from .news import RawHeadline
from .provider import ProviderError

_YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
_GOOGLE = "https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
_UA = "Mozilla/5.0 (compatible; SaalrBot/1.0; +https://saalr.com)"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})
_TAG = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG.sub("", s or "").strip()


def _parse_pubdate(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_rss(xml_bytes: bytes, *, source: str, ticker: str) -> list[RawHeadline]:
    """Pure: map RSS 2.0 <item>s into RawHeadline. Skips items missing a title or parseable date."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    out: list[RawHeadline] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        published = _parse_pubdate(item.findtext("pubDate"))
        if not title or published is None:
            continue
        out.append(
            RawHeadline(
                title=title,
                description=_strip_html(item.findtext("description") or ""),
                published_at=published,
                source=source,
                url=(item.findtext("link") or "").strip(),
                tickers=[ticker.upper()],
            )
        )
    return out


class RssNewsProvider:
    """No-key news via public RSS: Yahoo Finance primary, Google News fallback."""

    def __init__(self, *, timeout: float = 15.0, transport: httpx.BaseTransport | None = None) -> None:
        self._timeout = timeout
        self._transport = transport

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> bytes:
        for attempt in range(3):
            try:
                r = await client.get(url, headers={"User-Agent": _UA})
                if r.status_code in _RETRYABLE:
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    raise ProviderError(f"rss returned {r.status_code} after retries")
                r.raise_for_status()
                return r.content
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
        feeds = [("yahoo", _YAHOO.format(ticker=ticker)), ("google", _GOOGLE.format(ticker=ticker))]
        last_err: ProviderError | None = None
        reachable = False
        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport, follow_redirects=True
        ) as client:
            for source, url in feeds:
                try:
                    raw = await self._fetch(client, url)
                except ProviderError as exc:
                    last_err = exc
                    continue
                reachable = True
                items = parse_rss(raw, source=source, ticker=ticker)
                if published_after is not None:
                    items = [h for h in items if h.published_at >= published_after]
                if items:
                    return items[:limit]
        if not reachable and last_err is not None:
            raise last_err
        return []
