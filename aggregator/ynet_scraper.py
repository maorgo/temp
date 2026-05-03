from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

from aggregator.models import Article

_FEED_URL = "https://www.ynet.co.il/Integration/StoryRss2.xml"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch() -> list[Article]:
    feed = feedparser.parse(_FEED_URL)

    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Ynet feed error: {feed.bozo_exception}")

    articles: list[Article] = []
    for entry in feed.entries:
        if not entry.get("title") or not entry.get("link"):
            continue

        published = _parse_date(entry)
        full_article = (
            _fetch_full_text(entry.link)
            or _strip_html(entry.get("summary", ""))
        )

        articles.append(Article(
            title=entry.title,
            url=entry.link,
            source="Ynet",
            published=published,
            full_article=full_article,
        ))

    return articles


def _fetch_full_text(url: str) -> str:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    body = soup.find("div", class_="ArticleBodyComponent")
    if not body:
        return ""

    paragraphs = [
        d.get_text(separator=" ", strip=True)
        for d in body.find_all("div", class_="text_editor_paragraph")
    ]
    return "\n\n".join(p for p in paragraphs if p)


def _strip_html(text: str) -> str:
    return BeautifulSoup(text, "html.parser").get_text(separator=" ").strip()


def _parse_date(entry: feedparser.FeedParserDict) -> datetime:
    if entry.get("published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc)
