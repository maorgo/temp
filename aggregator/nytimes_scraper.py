import os
from datetime import datetime, timezone

import feedparser
import requests

from aggregator.models import Article

_FEED_URL = "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"
_API_URL = "https://api.nytimes.com/svc/search/v2/articlesearch.json"


def fetch(api_key: str = "") -> list[Article]:
    if not api_key:
        api_key = os.getenv("NYT_API_KEY", "")

    feed = feedparser.parse(_FEED_URL)

    if feed.bozo and not feed.entries:
        raise RuntimeError(f"NYTimes feed error: {feed.bozo_exception}")

    articles: list[Article] = []
    for entry in feed.entries:
        if not entry.get("title") or not entry.get("link"):
            continue

        published = _parse_date(entry)
        full_article = (
            _fetch_via_api(entry.link, api_key) if api_key else ""
        ) or entry.get("summary", "")

        articles.append(Article(
            title=entry.title,
            url=entry.link,
            source="NYTimes",
            published=published,
            full_article=full_article,
        ))

    return articles


def _fetch_via_api(url: str, api_key: str) -> str:
    resp = requests.get(
        _API_URL,
        params={
            "fq": f'web_url:("{url}")',
            "fl": "abstract,lead_paragraph",
            "api-key": api_key,
        },
        timeout=10,
    )
    resp.raise_for_status()
    docs = resp.json().get("response", {}).get("docs", [])
    if not docs:
        return ""
    doc = docs[0]
    parts = [doc.get("abstract", ""), doc.get("lead_paragraph", "")]
    return "\n\n".join(p for p in parts if p)


def _parse_date(entry: feedparser.FeedParserDict) -> datetime:
    if entry.get("published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc)
