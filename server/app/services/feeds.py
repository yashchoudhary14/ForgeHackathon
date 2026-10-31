"""Latest releases from the official PIB RSS feed; no local seed items."""
import html
from urllib.parse import urlparse

import feedparser
import httpx

from ..schemas import FeedItem

PIB_RSS = "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=2&Regid=3"


async def latest_pib() -> list[FeedItem]:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        response = await client.get(PIB_RSS)
        response.raise_for_status()
    feed = feedparser.parse(response.content)
    if feed.bozo and not feed.entries:
        raise ValueError("PIB did not return a readable RSS feed")
    items = []
    for entry in feed.entries[:20]:
        url, title = entry.get("link", ""), entry.get("title", "")
        if urlparse(url).hostname not in {"pib.gov.in", "www.pib.gov.in"} or not title.strip():
            continue
        items.append(FeedItem(
            title=html.unescape(title).strip(), url=url, source="PIB",
            published=entry.get("published"),
        ))
    return items
