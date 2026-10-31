"""Live PIB RSS, cached for fifteen minutes per language."""
import asyncio
import time
from urllib.parse import urlsplit

import feedparser
import httpx

from ..schemas import FeedItem

# Verified 2026-10-30. Without `reg=3`, PIB redirects even Lang=1 to Lang=2&reg=48.
# The RSS links are published on https://www.pib.gov.in/ViewRss.aspx?lang=1&reg=3.
RSS_URLS = {lang: f"https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang={code}&Regid=3&reg=3"
            for lang, code in (("en", 1), ("hi", 2))}
_cache: dict[str, tuple[float, list[FeedItem]]] = {}
_locks = {lang: asyncio.Lock() for lang in RSS_URLS}


def parse_feed(data: bytes) -> list[FeedItem]:
    parsed = feedparser.parse(data)
    if not parsed.entries:
        raise ValueError("PIB did not return a populated RSS feed")
    result, seen = [], set()
    for entry in parsed.entries:
        url = entry.get("link", "")
        host = urlsplit(url).hostname or ""
        if urlsplit(url).scheme not in ("http", "https") or not (host == "pib.gov.in" or host.endswith(".pib.gov.in")):
            continue
        if url in seen or not entry.get("title"):
            continue
        seen.add(url)
        result.append(FeedItem(title=entry.title, url=url, published=entry.get("published"),
            ministry=entry.get("author") or entry.get("category"), source="PIB"))
    if not result:
        raise ValueError("PIB RSS has no valid official entries")
    return result


async def get_feed(lang: str = "en", limit: int = 20) -> list[FeedItem]:
    if lang not in RSS_URLS or not 1 <= limit <= 100:
        raise ValueError("Use lang=en or hi and limit=1–100")
    async with _locks[lang]:
        cached = _cache.get(lang)
        if cached and time.monotonic() - cached[0] < 900:
            return cached[1][:limit]
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0"}) as client:
            response = await client.get(RSS_URLS[lang])
            response.raise_for_status()
        items = await asyncio.to_thread(parse_feed, response.content)
        _cache[lang] = (time.monotonic(), items)
        return items[:limit]
