import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from aggregator.models import Article
from aggregator.ynet_scraper import fetch, _strip_html

_ARTICLE_HTML = """
<html><body>
<div class="ArticleBodyComponent">
  <div class="text_editor_paragraph">פסקה ראשונה של הכתבה.</div>
  <div class="text_editor_paragraph">פסקה שנייה עם פרטים נוספים.</div>
  <div class="text_editor_paragraph">סיכום הכתבה בפסקה האחרונה.</div>
</div>
</body></html>
"""

_EMPTY_HTML = "<html><body><p>no article body here</p></body></html>"


def _make_entry(
    title="כותרת חדשות",
    link="https://www.ynet.co.il/news/article/abc123",
    summary="<p>תוכן <b>חשוב</b> כאן</p>",
    published_parsed=(2026, 5, 3, 9, 15, 0, 5, 123, 0),
):
    entry = MagicMock()
    data = {
        "title": title,
        "link": link,
        "summary": summary,
        "published_parsed": published_parsed,
    }
    entry.get.side_effect = lambda k, default="": data.get(k, default)
    entry.title = title
    entry.link = link
    entry.summary = summary
    entry.published_parsed = published_parsed
    return entry


def _make_feed(entries=None, bozo=False):
    feed = MagicMock()
    feed.entries = entries if entries is not None else []
    feed.bozo = bozo
    feed.bozo_exception = Exception("feed parse error")
    return feed


def _mock_requests_get(html: str = _ARTICLE_HTML, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    resp.raise_for_status = MagicMock()
    return resp


class TestStripHtml(unittest.TestCase):

    def test_removes_paragraph_tags(self):
        self.assertNotIn("<p>", _strip_html("<p>hello</p>"))

    def test_removes_bold_tags_preserves_text(self):
        result = _strip_html("<b>important</b>")
        self.assertIn("important", result)
        self.assertNotIn("<b>", result)

    def test_removes_image_tags(self):
        result = _strip_html('<img src="photo.jpg"/> Some text')
        self.assertNotIn("<img", result)
        self.assertIn("Some text", result)

    def test_preserves_hebrew_text(self):
        result = _strip_html("<p>טקסט בעברית</p>")
        self.assertIn("טקסט בעברית", result)

    def test_plain_text_returned_unchanged(self):
        self.assertEqual(_strip_html("No HTML here"), "No HTML here")

    def test_empty_string_returns_empty_string(self):
        self.assertEqual(_strip_html(""), "")

    def test_nested_tags_fully_stripped(self):
        result = _strip_html("<div><p><span>deep text</span></p></div>")
        self.assertNotIn("<", result)
        self.assertIn("deep text", result)


class TestYnetFetch(unittest.TestCase):

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_returns_list_of_articles(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry()])
        mock_get.return_value = _mock_requests_get()
        result = fetch()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Article)

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_source_is_always_ynet(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(), _make_entry(title="אחר", link="https://ynet.co.il/2")])
        mock_get.return_value = _mock_requests_get()
        for article in fetch():
            self.assertEqual(article.source, "Ynet")

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_full_text_used_when_article_body_found(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(summary="<p>RSS תקציר</p>")])
        mock_get.return_value = _mock_requests_get(_ARTICLE_HTML)
        article = fetch()[0]
        self.assertIn("פסקה ראשונה של הכתבה", article.full_article)
        self.assertIn("פסקה שנייה עם פרטים נוספים", article.full_article)
        self.assertIn("סיכום הכתבה בפסקה האחרונה", article.full_article)

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_paragraphs_joined_by_double_newline(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry()])
        mock_get.return_value = _mock_requests_get(_ARTICLE_HTML)
        article = fetch()[0]
        self.assertIn("\n\n", article.full_article)

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_falls_back_to_rss_summary_when_no_article_body(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(summary="<p>תוכן <b>חשוב</b> כאן</p>")])
        mock_get.return_value = _mock_requests_get(_EMPTY_HTML)
        article = fetch()[0]
        self.assertIn("חשוב", article.full_article)
        self.assertNotIn("<", article.full_article)

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_falls_back_to_rss_summary_on_request_error(self, mock_parse, mock_get):
        import requests as req_module
        mock_parse.return_value = _make_feed([_make_entry(summary="Plain RSS text")])
        mock_get.side_effect = req_module.RequestException("timeout")
        article = fetch()[0]
        self.assertEqual(article.full_article, "Plain RSS text")

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_html_stripped_from_rss_fallback(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(summary="<p>Some <b>bold</b> text</p>")])
        mock_get.return_value = _mock_requests_get(_EMPTY_HTML)
        article = fetch()[0]
        self.assertNotIn("<", article.full_article)
        self.assertIn("bold", article.full_article)

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_maps_title_and_url_correctly(self, mock_parse, mock_get):
        entry = _make_entry(title="כותרת ראשית", link="https://www.ynet.co.il/news/article/xyz")
        mock_parse.return_value = _make_feed([entry])
        mock_get.return_value = _mock_requests_get()
        article = fetch()[0]
        self.assertEqual(article.title, "כותרת ראשית")
        self.assertEqual(article.url, "https://www.ynet.co.il/news/article/xyz")

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_skips_entry_with_missing_title(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(title=""), _make_entry(title="Valid")])
        mock_get.return_value = _mock_requests_get()
        result = fetch()
        self.assertEqual(len(result), 1)

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_skips_entry_with_missing_link(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed([_make_entry(link=""), _make_entry()])
        mock_get.return_value = _mock_requests_get()
        self.assertEqual(len(fetch()), 1)

    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_raises_runtime_error_on_bozo_feed_with_no_entries(self, mock_parse):
        mock_parse.return_value = _make_feed(entries=[], bozo=True)
        with self.assertRaises(RuntimeError):
            fetch()

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_bozo_feed_with_entries_does_not_raise(self, mock_parse, mock_get):
        mock_parse.return_value = _make_feed(entries=[_make_entry()], bozo=True)
        mock_get.return_value = _mock_requests_get()
        self.assertEqual(len(fetch()), 1)

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_parses_published_date_correctly(self, mock_parse, mock_get):
        entry = _make_entry(published_parsed=(2026, 5, 3, 9, 15, 0, 5, 123, 0))
        mock_parse.return_value = _make_feed([entry])
        mock_get.return_value = _mock_requests_get()
        self.assertEqual(fetch()[0].published, datetime(2026, 5, 3, 9, 15, 0, tzinfo=timezone.utc))

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_fallback_date_when_published_parsed_is_none(self, mock_parse, mock_get):
        entry = _make_entry(published_parsed=None)
        mock_parse.return_value = _make_feed([entry])
        mock_get.return_value = _mock_requests_get()
        before = datetime.now(tz=timezone.utc)
        article = fetch()[0]
        self.assertGreaterEqual(article.published, before)

    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_empty_feed_returns_empty_list(self, mock_parse):
        mock_parse.return_value = _make_feed(entries=[])
        self.assertEqual(fetch(), [])

    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_calls_ynet_rss_url(self, mock_parse):
        mock_parse.return_value = _make_feed([])
        fetch()
        self.assertIn("ynet.co.il", mock_parse.call_args[0][0])

    @patch("aggregator.ynet_scraper.requests.get")
    @patch("aggregator.ynet_scraper.feedparser.parse")
    def test_fetches_each_entry_link(self, mock_parse, mock_get):
        entries = [_make_entry(link=f"https://ynet.co.il/{i}") for i in range(3)]
        mock_parse.return_value = _make_feed(entries)
        mock_get.return_value = _mock_requests_get()
        fetch()
        self.assertEqual(mock_get.call_count, 3)
        fetched_urls = [call[0][0] for call in mock_get.call_args_list]
        self.assertIn("https://ynet.co.il/0", fetched_urls)
        self.assertIn("https://ynet.co.il/2", fetched_urls)


if __name__ == "__main__":
    unittest.main()
