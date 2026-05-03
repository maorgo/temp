import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import feedparser
import requests
from rich.console import Console

from aggregator.models import Article

_FEED_URL = "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"
_JINA_BASE = "https://r.jina.ai/"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ContentAggregator/1.0)",
    "Accept": "text/plain",
}
_MAX_WORKERS = 8
_console = Console(stderr=True)


def fetch() -> list[Article]:
    feed = feedparser.parse(_FEED_URL)

    if feed.bozo and not feed.entries:
        raise RuntimeError(f"NYTimes feed error: {feed.bozo_exception}")

    entries = [e for e in feed.entries if e.get("title") and e.get("link")]

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        bodies = list(pool.map(_fetch_full_text, [e.link for e in entries]))

    articles: list[Article] = []
    for entry, body in zip(entries, bodies):
        articles.append(Article(
            title=entry.title,
            url=entry.link,
            source="NYTimes",
            published=_parse_date(entry),
            full_article=body or entry.get("summary", ""),
        ))

    return articles


def _fetch_full_text(url: str) -> str:
    try:
        resp = requests.get(_JINA_BASE + url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        return _clean_reader_output(resp.text)
    except (requests.RequestException, OSError) as exc:
        _console.print(f"[yellow]NYTimes body fetch failed for {url}: {exc}[/yellow]")
        return ""


def _clean_reader_output(text: str) -> str:
    marker = "Markdown Content:"
    idx = text.find(marker)
    if idx != -1:
        text = text[idx + len(marker):]

    text = re.sub(r'\[SKIP ADVERTISEMENT\]\([^)]*\)', "", text)

    lines = text.splitlines()
    while lines and lines[0].strip() in ("Advertisement", ""):
        lines.pop(0)

    return "\n".join(lines).strip()


def _parse_date(entry: feedparser.FeedParserDict) -> datetime:
    if entry.get("published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc)
